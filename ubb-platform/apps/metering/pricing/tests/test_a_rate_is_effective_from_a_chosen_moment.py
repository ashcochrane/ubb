"""A rate is effective from the moment the tenant chooses, and then it is fixed (#325).

The column resolution reads was `auto_now_add=True`, which does not merely
default — it **overwrites whatever the caller supplied, on every insert**. So a
tenant could only ever say *"effective from the instant I clicked save"*, and the
remediation loop this slice exists to close could not close: an event replayed
from January resolves against the rules effective in January, there were none,
and the correction returned a plausible-looking number that was not the answer.

**Resolution was already right, which is why nothing found this.**
`PricingService._matching_rules_across` has filtered `valid_from__lte=as_of`
since it was written, and `UsageService.record_usage` has threaded
`as_of=effective_at` just as long. Every part of reading a historical rate
worked. Only *declaring* one was impossible, and no assertion in the tree
recorded a rate's effective moment as something a caller had **chosen** — the
one test that came closest reached around the defect with a `QuerySet.update()`
after the insert, which is now itself refused.
:class:`AReplayedEventResolvesAgainstTheRateEffectiveThenTest` is the assertion
whose absence let this survive.

**Dropping the flag is half the ticket and the smaller half.** A column that
simply stopped being auto-stamped would be an *unconstrained* column, which
ADR-0007 §2 refuses in the same breath: mutability is declared per field **and**
enforced by the database. Both columns are therefore declared, and the
declarations are the interesting part:

* `valid_from` — **FROZEN**. When a rate took effect is a fact *about* the rate.
  Moving it retroactively re-costs work that has already reported, silently and
  in whichever direction the mover preferred.
* `valid_to` — **SET_ONCE**. Closing a rate is a one-way act. Reopening one over
  a period that has already reported is a rewrite of history rather than an
  edit, and it is indistinguishable from one at the row.

**One table carries both halves and the rule does not get to know which.** Cost
and price rules share a table, so a rule that held only one of them would be a
rule that held neither in any way a reader could rely on. Every refusal below is
driven over both halves, and every one is driven through the three doors
ADR-0007 §2 names — `save()`, `QuerySet.update()` and raw SQL.

**Every refusal asserts the MESSAGE, not merely that something refused.** This
table already carries a partial unique index over `valid_to`, so "the write was
rejected" stops being evidence about the trigger the moment a second mechanism
can produce it. Each case names the transition class it expects to be told
about.

**What this ticket deliberately does not do.** It publishes nothing. A tenant
choosing the moment through the tenant-facing surface needs that surface
rebuilt, which is slice 4's, and this module asserts only that slice 4 inherits
two constrained columns rather than a flag to delete —
:class:`SliceFourInheritsConstrainedColumnsRatherThanAFlagTest`.
"""
import re
from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError, connection, migrations, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.utils import timezone

import core.transitions
from apps.metering.pricing.models import CostBook, Rate
from apps.metering.pricing.services.book_service import BookService
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject, cost_rate_in_default_book, database_rules_guarding,
    rate_in_default_book, the_pricing_tables_as_this_migration_saw_them)
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.transitions import (
    FROZEN, SET_ONCE, columns_declared_into_defended_classes)

VALID_FROM = "valid_from"
VALID_TO = "valid_to"

TABLE = Rate._meta.db_table

#: The rule this module is about, by the name `0018` gave it. Spelled since
#: #326, which installed a SECOND trigger on this table — one holding what may
#: happen to a rate's two moments, the other what may be born at all — so
#: "the trigger on this table" stopped being a description of anything.
TRANSITION_TRIGGER = "trg_rate_declared_transitions"
#: The other one, named here only so the count below says which two it found.
DECLARATION_TRIGGER = "trg_rate_names_a_declaration"

#: The two halves of the one table, reached through the helpers that know which
#: book a rate belongs in. The word that separates them is retired and slice 4
#: owns re-spelling it, so neither this module nor its assertions ever say it —
#: `rate_in_default_book`'s own default is the price half, and
#: `cost_rate_in_default_book` is the cost half by name.
HALVES = (("the cost half", cost_rate_in_default_book),
          ("the price half", rate_in_default_book))


def _tenant():
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 default_currency="usd")


def _customer(tenant):
    return Customer.objects.create(tenant=tenant, external_id="c1")


# --- The three doors ADR-0007 §2 names, each writing the same columns --------
#
# A rule only one of them respects is the defect the declaration exists to
# prevent, so every prohibited move below is driven through all three.

def _through_the_queryset(rate, **columns):
    Rate.objects.filter(pk=rate.pk).update(**columns)


def _through_raw_sql(rate, **columns):
    assignments = ", ".join(f"{name} = %s" for name in columns)
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {TABLE} SET {assignments} WHERE id = %s",
                       [*columns.values(), str(rate.pk)])


def _through_save(rate, **columns):
    """`save()`, through the base implementation.

    `Rate` carries no `save()` override to reach around — unlike the posting,
    which refuses every update in Python — so this door is what an ordinary
    caller writes. It is driven through `models.Model.save` rather than
    `rate.save()` so that the day someone adds such an override, this door goes
    on testing the database rather than quietly starting to test the override.
    """
    for name, value in columns.items():
        setattr(rate, name, value)
    models.Model.save(rate)


DOORS = (("QuerySet.update()", _through_the_queryset),
         ("raw SQL", _through_raw_sql),
         ("save()", _through_save))


def _refusal_body():
    """The trigger function's EXECUTABLE text — its comments stripped out.

    Stripping is not fussiness, and it was measured rather than supposed. Every
    branch in that function carries an SQL comment naming the column it is
    about, so "the column is named in the body" is satisfied by the comment
    EXPLAINING a branch that has been deleted: removing the whole `valid_to`
    refusal left the assertion below green until the comments came out. A
    prose-satisfiable assertion about whether a rule exists is the exact shape
    this repository keeps paying for.
    """
    return "\n".join(re.sub(r"--.*$", "", line)
                     for line in _transition_trigger()[2].splitlines())


def _transition_trigger():
    """The row `0018` installed, addressed BY NAME.

    It was `_trigger_rows()[0]` while this table had one trigger. #326 installed
    a second — a `BEFORE INSERT` rule refusing a rate that references no
    declaration — and `pg_trigger` promises no order, so an index would have
    made every assertion below a coin toss between two rules that hold
    completely different things.
    """
    for row in _trigger_rows():
        if row[0] == TRANSITION_TRIGGER:
            return row
    raise AssertionError(f"{TRANSITION_TRIGGER} is not installed on {TABLE}")


def _trigger_rows():
    """What the catalogue holds about the rules guarding this table, now.

    One join, read by both classes that ask the database anything: a migration
    that ran is evidence that a file executed, not that a rule is installed.
    Returns `(name, type_bits, function_body)` per non-internal trigger, which
    is every fact the callers between them need.

    The query itself moved to `_helpers` when #367 gave a second module the
    same question to ask, under the rule that a shared setup helper lives
    there rather than in whichever module needed it first.
    """
    return database_rules_guarding(TABLE)


class TransitionRefusalMixin:

    def _refusal(self, door, rate, **columns):
        """The message Postgres refused with, or `None` if it did not refuse."""
        try:
            with transaction.atomic():
                door(rate, **columns)
        except IntegrityError as refusal:
            return str(refusal)
        return None

    def _refused_on_both_halves(self, transition_class, make, **columns):
        """Every door, on both halves of the table, asserting the message.

        `make` builds the row under test from a rate factory, so a case can set
        up a row that has already been closed without either half being spelled
        at the call site.
        """
        for half, rate_in_book in HALVES:
            for name, door in DOORS:
                with self.subTest(half=half, door=name):
                    message = self._refusal(door, make(rate_in_book), **columns)
                    self.assertIsNotNone(message, "the write was admitted")
                    self.assertIn(transition_class, message)


class TheDeclaredMomentSurvivesTheInsertTest(TestCase):
    """AC 1 — the caller's value is kept, which `auto_now_add` made impossible.

    Read against what the defect looked like: passing `valid_from` to
    `create()` was never an error. It was accepted, discarded and replaced with
    `now()` before the row reached the database, so a caller who supplied one
    got a successful write and the wrong fact, with nothing anywhere to read as
    a complaint.
    """

    def test_a_moment_in_the_past_survives(self):
        moment = timezone.now() - timedelta(days=30)
        for half, rate_in_book in HALVES:
            with self.subTest(half=half):
                rate = rate_in_book(_tenant(), **{VALID_FROM: moment})
                self.assertEqual(getattr(Rate.objects.get(id=rate.id), VALID_FROM),
                                 moment)

    def test_a_moment_in_the_future_survives(self):
        """Forward dating, which is the same mechanism read the other way.

        A row whose moment has not arrived resolves for nobody until it does:
        resolution already asks which rule was effective at the event's own
        instant, so nothing has to schedule anything.

        ⚠ THAT IS THE COLUMN'S HALF AND IT IS NOT THE WHOLE FEATURE, which is
        worth saying here because the shortest reading of this test is "a
        tenant can now schedule next month's rise" and they cannot. Two things
        stand in the way and neither is this ticket's. A book's active-rule
        key (`uq_rate_active_in_pricing_book`, and its cost-side twin since
        #368) is unique on the selectors WHERE `valid_to IS NULL`, so a future-dated
        row cannot be written beside the open row it is meant to replace — the
        pair has to be created by one act that closes the outgoing rule, which
        is the Pricing Book Publish record (2026-07-31 decision, §6.3).

        ⚠ **THE SECOND OBSTACLE IS GONE AND THIS PARAGRAPH USED TO SAY IT WAS
        NOT (#356).** It read that `CardCache.resolve` hardcodes
        `timezone.now()`, so resolution behind the cache is not time-aware at
        all, and that §8.3 of that decision assigns making it so to later work.
        That work is the price resolver: the instant is a parameter of
        `resolve_price` and of `CardCache.resolve`, and it is part of the cache
        key, so a cached resolution answers for the moment it was computed for
        and no other. What is left in the way is the constraint above.

        What this test pins is the column: a supplied future moment is kept
        rather than overwritten, which is the thing that had to be true first.
        """
        moment = timezone.now() + timedelta(days=7)
        for half, rate_in_book in HALVES:
            with self.subTest(half=half):
                rate = rate_in_book(_tenant(), **{VALID_FROM: moment})
                self.assertEqual(getattr(Rate.objects.get(id=rate.id), VALID_FROM),
                                 moment)

    def test_a_rate_that_names_no_moment_is_effective_from_now(self):
        """The default, which is the whole of what `auto_now_add` was for.

        Every existing caller supplies nothing, so the behaviour they rely on
        has to survive the flag being removed — and a `default` is where that
        behaviour belongs, because a default is what a caller may override.
        """
        before = timezone.now()
        rate = cost_rate_in_default_book(_tenant())
        after = timezone.now()
        self.assertGreaterEqual(getattr(rate, VALID_FROM), before)
        self.assertLessEqual(getattr(rate, VALID_FROM), after)


class APastRateResolvesOnlyAfterItsMomentTest(TestCase):
    """AC 2 — a declared moment is a boundary, and it holds on both sides.

    Asserting only that a back-dated rate resolves *something* would pass on a
    column that was ignored altogether, since a rate stamped `now()` also
    resolves an event happening now. The case that separates the two is the
    event BEFORE the declared moment, which must resolve against nothing.
    """

    RATE = {"measurement_key": "tok", "rate_per_unit_micros": 10,
            "unit_quantity": 1}

    def setUp(self):
        self.tenant = _tenant()
        self.customer = _customer(self.tenant)
        self.moment = timezone.now() - timedelta(days=20)
        cost_rate_in_default_book(self.tenant, **{VALID_FROM: self.moment},
                                  **self.RATE)

    def _cost_at(self, as_of):
        return PricingService.price(
            subject=a_usage_event_subject(),
            tenant=self.tenant, customer=self.customer, selectors={},
            measurements={"tok": 100}, currency="usd",
            caller_provider_cost=None,
            as_of=as_of).provider_cost_micros

    def test_an_event_after_the_declared_moment_resolves_against_it(self):
        self.assertEqual(self._cost_at(self.moment + timedelta(days=1)), 1_000)

    def test_an_event_at_the_declared_moment_itself_resolves_against_it(self):
        """The boundary instant belongs to the rule that opens on it.

        The range is half-open — `valid_from <= as_of < valid_to` — and both
        ends of that agreement are load-bearing together: it is what lets a
        closing rule and its replacement share one instant with neither a gap
        nor an overlap, which `NoInstantFallsBetweenTwoVersionsTest` relies on.
        """
        self.assertEqual(self._cost_at(self.moment), 1_000)

    def test_an_event_before_the_declared_moment_resolves_against_nothing(self):
        self.assertIsNone(self._cost_at(self.moment - timedelta(seconds=1)))


class AReplayedEventResolvesAgainstTheRateEffectiveThenTest(TestCase):
    """AC 3 — THE ASSERTION WHOSE ABSENCE LET THE DEFECT SURVIVE.

    This is the remediation loop the slice exists to close, end to end and
    through the real recording path rather than the resolver alone: a supplier
    charge is discovered late, the event is replayed from the moment it actually
    happened, and it must cost what it cost **then**.

    Under the defect this could not be set up at all. Both rules would have been
    stamped at insert, the older one would have been effective from a moment
    after the event it is supposed to price, and the replay would have resolved
    against whichever rule was written last — today's. The number that came back
    would have looked entirely ordinary.
    """

    RATE = {"measurement_key": "tok", "unit_quantity": 1}

    def setUp(self):
        self.tenant = _tenant()
        self.customer = _customer(self.tenant)
        self.now = timezone.now()
        self.then = self.now - timedelta(days=20)
        # The rule that was effective when the event happened, and the one that
        # replaced it ten days later. Both are declared, which is the whole of
        # what this ticket adds — before it, neither statement was sayable.
        cost_rate_in_default_book(
            self.tenant, rate_per_unit_micros=10,
            **{VALID_FROM: self.then - timedelta(days=10),
               VALID_TO: self.then + timedelta(days=10)},
            **self.RATE)
        cost_rate_in_default_book(
            self.tenant, rate_per_unit_micros=50,
            **{VALID_FROM: self.then + timedelta(days=10)}, **self.RATE)

    def _record(self, **kwargs):
        return UsageService.record_usage(
            self.tenant, self.customer, "r1", "k1",
            measurements={"tok": 100}, **kwargs)

    def test_a_replayed_event_costs_what_it_cost_then(self):
        recorded = self._record(effective_at=self.then)
        self.assertEqual(recorded["provider_cost_micros"], 1_000)

    def test_the_same_event_recorded_now_costs_todays_rate(self):
        """The control, and this class is worth nothing without it.

        Every assertion above is "the old number came back", which a system that
        had simply stopped resolving the newer rule would satisfy just as well.
        """
        recorded = self._record()
        self.assertEqual(recorded["provider_cost_micros"], 5_000)


class TheEffectiveMomentIsFrozenTest(TransitionRefusalMixin, TestCase):
    """AC 4 and AC 6 — `valid_from` takes no second value, on either half.

    ADR-0007 §2's `FROZEN` is *none after insert*, and here that is not a
    bookkeeping nicety. Moving when a rule took effect re-costs every event
    already priced under it. The rows are not rewritten, so nothing in the
    system disagrees with itself — the totals simply become different totals
    than the ones the tenant was shown, and no record anywhere says they moved.
    """

    def test_the_moment_cannot_be_moved_earlier(self):
        self._refused_on_both_halves(
            FROZEN, lambda rate_in_book: rate_in_book(_tenant()),
            **{VALID_FROM: timezone.now() - timedelta(days=1)})

    def test_the_moment_cannot_be_moved_later(self):
        self._refused_on_both_halves(
            FROZEN, lambda rate_in_book: rate_in_book(_tenant()),
            **{VALID_FROM: timezone.now() + timedelta(days=1)})

    def test_a_moment_declared_in_the_past_cannot_be_moved_either(self):
        """The row this ticket newly made writable is not a special case.

        A back-dated rate is exactly the row whose moment somebody would want to
        adjust after the fact — "that should have started a week earlier" — and
        it is the row where doing so is worst, because the work it re-costs has
        already been reported.
        """
        declared = timezone.now() - timedelta(days=30)
        self._refused_on_both_halves(
            FROZEN,
            lambda rate_in_book: rate_in_book(_tenant(), **{VALID_FROM: declared}),
            **{VALID_FROM: declared - timedelta(days=1)})


class TheClosingMomentIsSetOnceTest(TransitionRefusalMixin, TestCase):
    """AC 5 and AC 6 — `valid_to` goes from nothing to something, once.

    `SET_ONCE` rather than `FROZEN` because closing a rule is a legitimate late
    arrival: a rate is written open-ended and stays that way until the tenant
    replaces or retires it, which is how both live writers use the column. What
    is refused is the second write — moving the close, or taking it back.
    """

    @staticmethod
    def _closed(rate_in_book, when=None):
        """A rate that arrives already closed, declared at INSERT.

        Which is a different statement from a rate closed by an `UPDATE`, and
        the AC is about the second one — so
        `test_a_rate_closed_through_a_door_cannot_be_closed_again` drives that
        sequence literally rather than leaning on the two being equivalent.
        They are equivalent here (the trigger reads `OLD`, and `OLD.valid_to`
        is non-null either way), but "equivalent" is an argument and the AC
        asked for a sequence.
        """
        return rate_in_book(_tenant(),
                            **{VALID_TO: when or timezone.now() - timedelta(days=1)})

    def test_an_open_rate_can_be_closed_through_every_door(self):
        """The control, and the class is worthless without it.

        Every other case here asserts a refusal, which a rule that refused all
        writes to this column would satisfy completely — and a table where no
        rate could ever be retired or repriced would be a worse defect than the
        one this ticket fixes. Both live writers do exactly this statement.
        """
        closing = timezone.now()
        for half, rate_in_book in HALVES:
            for name, door in DOORS:
                with self.subTest(half=half, door=name):
                    rate = rate_in_book(_tenant())
                    door(rate, **{VALID_TO: closing})
                    rate.refresh_from_db()
                    self.assertEqual(getattr(rate, VALID_TO), closing)

    def test_a_closed_rate_cannot_be_closed_at_a_different_moment(self):
        self._refused_on_both_halves(
            SET_ONCE, self._closed, **{VALID_TO: timezone.now()})

    def test_a_rate_closed_through_a_door_cannot_be_closed_again(self):
        """"Set twice" as the literal sequence, not as an equivalent one.

        Every other refusal here starts from a rate that arrived closed. This
        one performs the first close as a real `UPDATE` — the statement both
        live writers actually issue — and then attempts a second through each
        door in turn. It is the AC read word for word: null to a value, and
        then the value refusing to move.
        """
        for half, rate_in_book in HALVES:
            for name, door in DOORS:
                with self.subTest(half=half, door=name):
                    rate = rate_in_book(_tenant())
                    _through_the_queryset(rate, **{VALID_TO: timezone.now()})
                    rate.refresh_from_db()
                    message = self._refusal(
                        door, rate,
                        **{VALID_TO: timezone.now() + timedelta(days=1)})
                    self.assertIsNotNone(message, "the write was admitted")
                    self.assertIn(SET_ONCE, message)

    def test_a_closed_rate_cannot_be_reopened(self):
        """The move the declaration is really about.

        Clearing the close puts a rule back over a period that has already
        reported, which is not an edit to a row — it is a different answer to a
        question somebody has already been given.
        """
        self._refused_on_both_halves(SET_ONCE, self._closed, **{VALID_TO: None})


class TheRuleIsHeldByATriggerOnThisTableTest(TestCase):
    """The mechanism, read off the live database rather than off the migration.

    A migration that ran is evidence that a file executed, not that a rule is
    installed. What matters is what `pg_trigger` holds now, on the table the
    model actually uses.
    """

    MIGRATION = "0018_a_rate_takes_effect_from_the_moment_the_tenant_chooses"

    def test_exactly_these_two_rules_guard_this_table(self):
        """This asserted ONE trigger until #326 installed the second.

        Kept as an exact set rather than relaxed to a count or to "at least
        mine": what it is really holding is that nobody adds a rule to the
        hottest priced table in the system without a reader of this file finding
        out. A third arrival is a decision somebody made, and it goes red here
        first.
        """
        self.assertEqual({name for name, _, _ in _trigger_rows()},
                         {TRANSITION_TRIGGER, DECLARATION_TRIGGER})

    def test_it_fires_before_each_updated_row(self):
        """`BEFORE UPDATE ... FOR EACH ROW`, read out of `tgtype`'s bits.

        Row-level and before the write: an `AFTER` trigger would refuse by
        rolling back work already done, and a statement-level one cannot see the
        old row at all, which is the only thing these two rules are about. It
        must not fire on `INSERT` either — that statement is where a caller
        declares the moment, which is the thing this ticket exists to permit.
        """
        _, tgtype, _ = _transition_trigger()
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 4), "does not fire on UPDATE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")
        self.assertFalse(tgtype & (1 << 3), "fires on DELETE")

    def test_the_reverse_is_exercised_rather_than_merely_declared(self):
        """Forward and back, against a real database, with a real refusal.

        `docs/conventions/django-patterns.md` asks for a reverse *"that a test
        actually runs"*, and this migration is the shape the rule is about: a
        `RunPython` whose two halves are DDL strings, where a typo in the
        reverse is invisible until the day somebody needs it and no other test
        will ever execute that branch.

        Asserted by BEHAVIOUR at both ends rather than by counting catalogue
        rows: with the rule reversed out, a write it refuses is admitted; with
        it re-applied, the same write is refused again. Postgres runs DDL inside
        the transaction this `TestCase` rolls back, so all of it leaves with the
        test and no other test sees this table without its rule.
        """
        migration = MigrationLoader(connection).get_migration(
            "pricing", self.MIGRATION)
        run_python = next(op for op in migration.operations
                          if isinstance(op, migrations.RunPython))
        rate = cost_rate_in_default_book(_tenant())
        moved = timezone.now() - timedelta(days=5)

        # ⚠ BOTH HALVES SPELL THE TABLE, AND THE TABLE WAS RENAMED IN #367. A
        # migration's DDL is history and must not be edited to follow a later
        # rename, so what the replay reconstructs is the NAME — the same repair
        # this suite already makes to the columns and rules that arrived after
        # the migration being replayed. Held only around the two DDL calls: the
        # writes between them go through the live model.
        with the_pricing_tables_as_this_migration_saw_them(migration):
            with connection.schema_editor() as editor:
                run_python.reverse_code(None, editor)
        # This rule gone, and only this one: the table carries a second trigger
        # since #326, and asserting an empty catalogue would have meant
        # asserting that reversing one migration removed another's rule.
        self.assertNotIn(TRANSITION_TRIGGER,
                         {name for name, _, _ in _trigger_rows()})
        _through_the_queryset(rate, **{VALID_FROM: moved})
        rate.refresh_from_db()
        self.assertEqual(getattr(rate, VALID_FROM), moved)

        with the_pricing_tables_as_this_migration_saw_them(migration):
            with connection.schema_editor() as editor:
                run_python.code(None, editor)
        self.assertIn(TRANSITION_TRIGGER,
                      {name for name, _, _ in _trigger_rows()})
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(
                    rate, **{VALID_FROM: moved - timedelta(days=1)})

    def test_a_column_the_rule_says_nothing_about_still_writes(self):
        """The rule guards two columns, not the table.

        A rate's amount is repriced by a path that has nothing to do with
        effective dating, and a rule that quietly froze the whole row would
        break it somewhere far from here.
        """
        rate = cost_rate_in_default_book(_tenant())
        _through_the_queryset(rate, rate_per_unit_micros=17)
        rate.refresh_from_db()
        self.assertEqual(rate.rate_per_unit_micros, 17)


class TheGateSawTheseColumnsWithoutBeingToldTest(TestCase):
    """AC 7 — THE LIVE PROOF THAT TICKET 3'S GATE WALK IS NOT A LIST.

    `apps/platform/tests/test_transition_class_declarations.py` asserts that
    every column declared into a database-defended class is defended by the
    database. It was written against one model's three columns, and the whole
    question it was built to answer is whether it would still be true of columns
    it had never seen. These two are the first such columns, and the property
    being relied on is that **nothing had to be re-pointed or added to
    anywhere** for the gate to cover them.

    So this records the property rather than the outcome. That the gate passes
    is the gate's own business and it runs in the same suite; what is asserted
    here is that it passes *for the right reason* — the walk found these columns
    because they are declared, and neither the walk nor the check contains their
    names. A gate that had to be edited to see them would have been a list
    wearing a walk's clothes, and that would have been the finding rather than a
    chore.
    """

    #: The two files that make up ticket 3's check: the walk that collects the
    #: declarations and the gate that asks the database about each one.
    WALK = Path(core.transitions.__file__)
    CHECK = (WALK.parents[1] / "apps" / "platform" / "tests"
             / "test_transition_class_declarations.py")

    def test_the_walk_reports_both_columns_by_declaration_alone(self):
        self.assertEqual(
            columns_declared_into_defended_classes([Rate]),
            [("Rate", VALID_FROM, FROZEN), ("Rate", VALID_TO, SET_ONCE)])

    def test_neither_column_is_named_anywhere_in_the_gate(self):
        """The claim that makes the coverage above mean something.

        Read as text rather than by importing: what would break this property is
        somebody adding a name to a list to make a failing gate pass, and that
        edit is a string appearing in one of these two files whether or not it
        is reachable code, a docstring or a comment.
        """
        for path in (self.WALK, self.CHECK):
            source = path.read_text(encoding="utf-8")
            for column in (VALID_FROM, VALID_TO):
                with self.subTest(file=path.name, column=column):
                    self.assertNotIn(column, source)

    def test_each_declared_column_is_named_inside_the_refusal_itself(self):
        """One notch stronger than the gate, and STILL WEAKER THAN IT LOOKS.

        The gate asks whether a declared column is named anywhere in the rules
        guarding its table — the trigger definition and the function body,
        joined. This table's `WHEN` clause names both columns, so a trigger
        whose two refusals had been deleted outright would satisfy the gate
        completely. This asserts the narrower thing: each declared column is
        named in the function's EXECUTABLE body — comments stripped, for the
        reason `_refusal_body` gives, which is that the first version of this
        test was itself satisfied by a comment.

        NEITHER CHECK PROVES THE RULE HOLDS, and that is worth writing down
        rather than leaving the next reader to find it the hard way. A branch
        can name a column and refuse nothing — `IF FALSE AND ...` satisfies
        both, which is how this was measured rather than assumed. What holds
        these two columns is the six refusal cases above, each driven over both
        halves and all three doors; this is the static half, and its whole job
        is to go red if a later edit drops a column from the rule while leaving
        its declaration behind.

        It walks `Rate` alone and says so. The whole-tree question — is EVERY
        declared column defended — is the gate's, it runs in this same suite,
        and restating it here would be a second copy that could disagree.
        """
        body = _refusal_body()
        for _, column, _ in columns_declared_into_defended_classes([Rate]):
            with self.subTest(column=column):
                self.assertIn(column, body)


class SliceFourInheritsConstrainedColumnsRatherThanAFlagTest(TestCase):
    """AC 8 — WHAT THE NEXT SLICE INHERITS, WRITTEN DOWN BESIDE A TEST.

    Slice 4 rebuilds this entity's published surface. Before this ticket it
    would have inherited a column carrying an `auto_now_add` flag and a decision
    still to make about it; after it, there is no flag left to delete and the
    decision is made. That difference is the whole point of declaring rather
    than deleting, and it is the thing a rebuild is most likely to undo by
    accident — a model rewritten around a new published shape drops a mapping
    nobody was reading.

    These carry the declarations forward. If slice 4 re-decides them it will
    have to delete assertions that say what was decided and why, which is the
    difference between a re-decision and an omission.

    ⚠ ONE OF THEM FORECLOSED A DESIGN THAT WAS ALREADY WRITTEN DOWN, AND SLICE
    4 PAID IT RATHER THAN RE-DECIDING IT (#360). The last case here used to
    hand that choice to the next author; it now states the ruling they made —
    a cancellation is a further publish. Carrying a declaration forward means
    inheriting what it costs, and this is what it cost.
    """

    def test_the_effective_moment_carries_no_flag_left_to_delete(self):
        field = Rate._meta.get_field(VALID_FROM)
        self.assertFalse(field.auto_now_add)
        self.assertIs(field.default, timezone.now)

    def test_both_declarations_are_exactly_what_this_ticket_settled(self):
        """Exact equality, so an added column is a decision rather than a drift.

        A subset assertion would let slice 4 add a column to this mapping
        without anyone choosing its class. Equality makes that a deliberate edit
        here — and the gate then makes it a rule in the database.

        ⚠ **SLICE 4 SCHEDULED THIS AS A TRIPWIRE FOR #367 AND IT CORRECTLY DID
        NOT FIRE — RECORDED RATHER THAN LEFT SILENT.** That ticket renames the
        table and deletes a column; it adds none, so the mapping is untouched
        and there was no triple-set to move. The set is keyed on the MODEL name
        rather than the table, so a rename cannot move it either. A tripwire
        that does not fire is a prediction that was wrong about WHICH commit,
        not a check that was skipped, and the next commit to add a term to this
        table still meets it.
        """
        self.assertEqual(Rate.transition_classes,
                         {VALID_FROM: FROZEN, VALID_TO: SET_ONCE})

    def test_the_cancellation_that_decision_wrote_is_a_further_publish_instead(self):
        """WHAT THIS DECLARATION COST, AND HOW IT WAS PAID — settled by #360.

        The 2026-07-31 pricing-versions decision (§6.5) cancels a pending
        publish by deleting the rows whose moment is still in the future and
        *"reopens their predecessors' `valid_to`"*. That reopen is a
        value-to-null write and `SET_ONCE` refuses it unconditionally, so the
        mechanism that document describes was never available as written. This
        case used to say so and hand the choice forward. **The choice has been
        made, and this is now the claim rather than the question.**

        **THE RULING: A CANCELLATION IS EXPRESSED AS A FURTHER PUBLISH.** The
        publish that reverses a scheduled change closes the rule the first one
        opened — a second null-to-value write, which is legal — and opens a new
        version of what that rule superseded, at the same instant. The reversed
        rule's window is `[T, T)`, empty, and resolves for no instant, which is
        correct because it never took effect. Every write is an INSERT or a
        once-only close; nothing is deleted and nothing is reopened.
        `pricing/tests/test_a_scheduled_publish_is_reversed_by_a_further_publish.py`
        is where that is built and measured.

        **THE TWO ALTERNATIVES WERE REJECTED WITH ARGUMENT, AND THE ARGUMENTS
        LIVE HERE BECAUSE THIS IS THE COLUMN THEY ARE ABOUT.** Re-deciding the
        class — making a close rewritable while the boundary is in the future —
        fails because a column's class cannot be conditional on whether anybody
        happened to read the row: the trigger cannot ask, and a class that
        holds only when a service remembers to check is enforcement already
        found not binding. Deriving the close from the successor's opening
        moment fails for two reasons that look like implementation detail and
        are not: the one-open-rule uniqueness rule is a database constraint
        over a stored null and *"the latest version"* is not expressible as a
        unique index, so deriving would move a money-shaped rule into a service
        check; and resolution is on the hot pricing path, where a stored
        half-open range is an index range scan and a derived end is a window
        function per resolution.

        The refusal below is the move the rejected mechanism would have made,
        driven through raw SQL — the door no service sits in front of, so the
        claim is that reopening is impossible rather than that the book service
        declines to do it.
        """
        closed = cost_rate_in_default_book(
            _tenant(), **{VALID_TO: timezone.now() + timedelta(days=7)})
        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                _through_raw_sql(closed, **{VALID_TO: None})
        self.assertIn(SET_ONCE, str(refusal.exception))

    def test_the_rule_lives_where_a_rebuilt_surface_cannot_reach_it(self):
        """Why the inheritance is safe rather than merely intended.

        Slice 4 rewrites schemas, endpoints and serializers. None of them is
        what holds these two columns: the refusals above arrive through
        `QuerySet.update()` and raw SQL, neither of which any published surface
        sits in front of. A rebuild can change every caller and still not reach
        the rule.
        """
        rate = cost_rate_in_default_book(_tenant())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_raw_sql(rate, **{VALID_FROM: timezone.now()})


class NoInstantFallsBetweenTwoVersionsTest(TestCase):
    """The gap the same flag was hiding (`docs/plans/`, 2026-07-31, §6.4).

    A reprice closed the outgoing rule at `T` and opened its replacement at the
    instant of insert, `T + ε`. Resolution asks for `valid_from <= as_of` and
    `valid_to > as_of`, so **no rule at all covered `[T, T + ε)`** — an event
    landing in that window matched nothing and fell through to markup pricing,
    which produces a plausible number and no error anywhere. Microseconds wide,
    real, and invisible.

    The same change fixes it, because the replacement can now be opened at the
    exact instant the outgoing rule closes. One clock closes the boundary and
    opens it, which is what the half-open range was always for: no gap and no
    overlap.
    """

    RATE = {"measurement_key": "tok", "rate_per_unit_micros": 10,
            "unit_quantity": 1}

    def test_the_boundary_instant_resolves_to_exactly_one_rule(self):
        tenant = _tenant()
        customer = _customer(tenant)
        opened = cost_rate_in_default_book(tenant, **self.RATE)
        # Fetched rather than read off the rule, so this asserts the fixture
        # put it where a cost rule belongs: this tenant has exactly one cost
        # book, and it is a different table from the Pricing Book (#368).
        book = CostBook.objects.get(tenant=tenant)

        # THE ONE MUTATION SURFACE A BOOK HAS (#368). The atomic reprice this
        # used to call is deleted with the audit action it wrote, so the
        # boundary is written by the act that writes every boundary now.
        BookService.publish_declared(BookService.declare(
            book, [{"kind": "reprice", "measurement_key": "tok",
                    "rate_per_unit_micros": 90}]))

        opened.refresh_from_db()
        boundary = getattr(opened, VALID_TO)
        replacement = Rate.objects.exclude(id=opened.id).get()
        self.assertEqual(getattr(replacement, VALID_FROM), boundary)

        cost = PricingService.price(
            subject=a_usage_event_subject(),
            tenant=tenant, customer=customer, selectors={},
            measurements={"tok": 100}, currency="usd",
            caller_provider_cost=None,
            as_of=boundary).provider_cost_micros
        self.assertEqual(cost, 9_000)
