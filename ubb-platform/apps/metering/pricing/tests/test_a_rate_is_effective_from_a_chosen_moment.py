"""A rate is effective from the moment the tenant chooses, and then it is fixed (#325).

The column resolution reads was `auto_now_add=True`, which does not merely
default — it **overwrites whatever the caller supplied, on every insert**. So a
tenant could only ever say *"effective from the instant I clicked save"*, and the
remediation loop this slice exists to close could not close: an event replayed
from January resolves against the rules effective in January, there were none,
and the correction returned a plausible-looking number that was not the answer.

**Resolution was already right, which is why nothing found this.**
`PricingService._resolve_rate_within` has filtered `valid_from__lte=as_of` since
it was written, and `UsageService.record_usage` has threaded
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
from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError, connection, migrations, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.utils import timezone

import core.transitions
from apps.metering.pricing.models import Rate, RateCard
from apps.metering.pricing.services.book_service import BookService
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, rate_in_default_book)
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.transitions import (
    FROZEN, SET_ONCE, columns_declared_into_defended_classes)

FROM = "valid_from"
TO = "valid_to"

TABLE = Rate._meta.db_table

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
                rate = rate_in_book(_tenant(), **{FROM: moment})
                self.assertEqual(getattr(Rate.objects.get(id=rate.id), FROM),
                                 moment)

    def test_a_moment_in_the_future_survives(self):
        """Forward dating, which is the same mechanism read the other way.

        A tenant announcing a rise from the first of next month writes the row
        now and the rule starts then. Nothing schedules it and nothing needs to:
        resolution already asks which rule was effective at the event's own
        moment, so a row whose moment has not arrived resolves for nobody until
        it does.
        """
        moment = timezone.now() + timedelta(days=7)
        for half, rate_in_book in HALVES:
            with self.subTest(half=half):
                rate = rate_in_book(_tenant(), **{FROM: moment})
                self.assertEqual(getattr(Rate.objects.get(id=rate.id), FROM),
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
        self.assertGreaterEqual(getattr(rate, FROM), before)
        self.assertLessEqual(getattr(rate, FROM), after)


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
        cost_rate_in_default_book(self.tenant, **{FROM: self.moment},
                                  **self.RATE)

    def _cost_at(self, as_of):
        return PricingService.price(
            tenant=self.tenant, customer=self.customer, selectors={},
            measurements={"tok": 100}, currency="usd",
            caller_provider_cost=None, caller_billed=None,
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
            **{FROM: self.then - timedelta(days=10),
               TO: self.then + timedelta(days=10)},
            **self.RATE)
        cost_rate_in_default_book(
            self.tenant, rate_per_unit_micros=50,
            **{FROM: self.then + timedelta(days=10)}, **self.RATE)

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
            **{FROM: timezone.now() - timedelta(days=1)})

    def test_the_moment_cannot_be_moved_later(self):
        self._refused_on_both_halves(
            FROZEN, lambda rate_in_book: rate_in_book(_tenant()),
            **{FROM: timezone.now() + timedelta(days=1)})

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
            lambda rate_in_book: rate_in_book(_tenant(), **{FROM: declared}),
            **{FROM: declared - timedelta(days=1)})


class TheClosingMomentIsSetOnceTest(TransitionRefusalMixin, TestCase):
    """AC 5 and AC 6 — `valid_to` goes from nothing to something, once.

    `SET_ONCE` rather than `FROZEN` because closing a rule is a legitimate late
    arrival: a rate is written open-ended and stays that way until the tenant
    replaces or retires it, which is how both live writers use the column. What
    is refused is the second write — moving the close, or taking it back.
    """

    @staticmethod
    def _closed(rate_in_book, when=None):
        return rate_in_book(_tenant(),
                            **{TO: when or timezone.now() - timedelta(days=1)})

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
                    door(rate, **{TO: closing})
                    rate.refresh_from_db()
                    self.assertEqual(getattr(rate, TO), closing)

    def test_a_closed_rate_cannot_be_closed_at_a_different_moment(self):
        self._refused_on_both_halves(
            SET_ONCE, self._closed, **{TO: timezone.now()})

    def test_a_closed_rate_cannot_be_reopened(self):
        """The move the declaration is really about.

        Clearing the close puts a rule back over a period that has already
        reported, which is not an edit to a row — it is a different answer to a
        question somebody has already been given.
        """
        self._refused_on_both_halves(SET_ONCE, self._closed, **{TO: None})


class TheRuleIsHeldByATriggerOnThisTableTest(TestCase):
    """The mechanism, read off the live database rather than off the migration.

    A migration that ran is evidence that a file executed, not that a rule is
    installed. What matters is what `pg_trigger` holds now, on the table the
    model actually uses.
    """

    MIGRATION = "0018_a_rate_takes_effect_from_the_moment_the_tenant_chooses"

    def _trigger_row(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT t.tgname, t.tgtype, p.prosrc "
                "FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_proc p ON p.oid = t.tgfoid "
                "WHERE c.relname = %s AND NOT t.tgisinternal", [TABLE])
            return cursor.fetchall()

    def test_exactly_one_trigger_guards_this_table(self):
        self.assertEqual(len(self._trigger_row()), 1)

    def test_it_fires_before_each_updated_row(self):
        """`BEFORE UPDATE ... FOR EACH ROW`, read out of `tgtype`'s bits.

        Row-level and before the write: an `AFTER` trigger would refuse by
        rolling back work already done, and a statement-level one cannot see the
        old row at all, which is the only thing these two rules are about. It
        must not fire on `INSERT` either — that statement is where a caller
        declares the moment, which is the thing this ticket exists to permit.
        """
        _, tgtype, _ = self._trigger_row()[0]
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

        with connection.schema_editor() as editor:
            run_python.reverse_code(None, editor)
        self.assertEqual(self._trigger_row(), [])
        _through_the_queryset(rate, **{FROM: moved})
        rate.refresh_from_db()
        self.assertEqual(getattr(rate, FROM), moved)

        with connection.schema_editor() as editor:
            run_python.code(None, editor)
        self.assertEqual(len(self._trigger_row()), 1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(
                    rate, **{FROM: moved - timedelta(days=1)})

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
            [("Rate", FROM, FROZEN), ("Rate", TO, SET_ONCE)])

    def test_neither_column_is_named_anywhere_in_the_gate(self):
        """The claim that makes the coverage above mean something.

        Read as text rather than by importing: what would break this property is
        somebody adding a name to a list to make a failing gate pass, and that
        edit is a string appearing in one of these two files whether or not it
        is reachable code, a docstring or a comment.
        """
        for path in (self.WALK, self.CHECK):
            source = path.read_text(encoding="utf-8")
            for column in (FROM, TO):
                with self.subTest(file=path.name, column=column):
                    self.assertNotIn(column, source)

    def test_the_check_itself_still_finds_nothing_undefended(self):
        """The gate's verdict, taken here over the whole tree.

        Not a duplicate of the gate: this is what fails if a later change
        declares a column and forgets the rule, and it is in *this* module so
        that the failure lands beside the declarations it is about rather than
        in a kernel test whose author never heard of a rate.
        """
        rules = self._rules_on(TABLE)
        for _, column, _ in columns_declared_into_defended_classes([Rate]):
            with self.subTest(column=column):
                self.assertIn(column, rules)

    @staticmethod
    def _rules_on(table):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_triggerdef(t.oid), p.prosrc "
                "FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_proc p ON p.oid = t.tgfoid "
                "WHERE c.relname = %s AND NOT t.tgisinternal", [table])
            return "\n".join(part for row in cursor.fetchall() for part in row)


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
    """

    def test_the_effective_moment_carries_no_flag_left_to_delete(self):
        field = Rate._meta.get_field(FROM)
        self.assertFalse(field.auto_now_add)
        self.assertIs(field.default, timezone.now)

    def test_both_declarations_are_exactly_what_this_ticket_settled(self):
        """Exact equality, so an added column is a decision rather than a drift.

        A subset assertion would let slice 4 add a column to this mapping
        without anyone choosing its class. Equality makes that a deliberate edit
        here — and the gate then makes it a rule in the database.
        """
        self.assertEqual(Rate.transition_classes,
                         {FROM: FROZEN, TO: SET_ONCE})

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
                _through_raw_sql(rate, **{FROM: timezone.now()})


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
        # The book is fetched rather than read off the rate: the property that
        # points at it is a retired word slice 4 owns, and a count recorded
        # there is a ceiling as much as a floor. This tenant has exactly one.
        book = RateCard.objects.get(tenant=tenant)

        BookService.publish(book, [{"measurement_key": "tok",
                                    "rate_per_unit_micros": 90}])

        opened.refresh_from_db()
        boundary = getattr(opened, TO)
        replacement = Rate.objects.exclude(id=opened.id).get()
        self.assertEqual(getattr(replacement, FROM), boundary)

        cost = PricingService.price(
            tenant=tenant, customer=customer, selectors={},
            measurements={"tok": 100}, currency="usd",
            caller_provider_cost=None, caller_billed=None,
            as_of=boundary).provider_cost_micros
        self.assertEqual(cost, 9_000)
