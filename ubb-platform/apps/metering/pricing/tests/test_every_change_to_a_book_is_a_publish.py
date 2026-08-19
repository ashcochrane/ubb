"""Every change to a Pricing Book is a publish, and a draft is not one (#358).

Adding a rule, repricing one and retiring one used to be three unrelated
mutation surfaces. They are one act here — declared, read as a diff, then
published — recorded once on a record that says who decided it, when, from when
it takes effect and which rule versions it opened and closed.

**WHAT EACH CLASS BELOW IS FOR.**

* *A draft closes nothing* — the property the whole two-state design rests on.
  A draft writes no rule, and discarding one leaves the book byte-identical,
  asserted as a full snapshot of every column of every rule rather than as a
  row count: a discard that quietly reopened a close, or moved a version, would
  pass a count.
* *One clock* — the outgoing rule's close and the incoming rule's open are one
  value, so with a half-open range there is exactly no gap and exactly no
  overlap. The boundary case then asks the only question a tenant would: resolve
  at the boundary and at the microsecond either side and get exactly one answer
  each time, **never a fallthrough to markup**. That fallthrough is the shape
  the live defect took — a plausible number, no error anywhere — so the markup
  rung is declared in that fixture and the assertion is that it did not run.
* *The record is immutable once published* — through `save()`,
  `QuerySet.update()` and raw SQL, plus the one ADMITTED move through the same
  three doors, because a rule that refused every write would satisfy the
  refusals alone.
* *The diff* — computed against the book **as it will stand at the effective
  instant**, with a case where that and "as of now" give different answers.
* *The three kinds* — add, reprice and retire, each expressible as a publish.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The container's pointer, the
cost/price discriminator and the arithmetic-shape column all carry ledger
entries that are ceilings as well as floors. Every book and rule here is built
through `_helpers`, which carries the first two for its callers; a book's own
rules are read through its reverse relation rather than by filtering on the
column that points at it; and the third never comes up, because a publish
cannot move a rule's arithmetic shape and no fixture here has one to state.
"""

import re
from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import (
    CHANGE_ADD, CHANGE_REPRICE, CHANGE_RETIRE, PricingBookPublish, Rate)
from apps.metering.pricing.services.book_service import BookService
from apps.metering.pricing.services.pricing_service import (
    PricingSubject, resolve_price)
from apps.metering.pricing.tests._helpers import (
    DOORS,
    RefusalThroughEveryDoorMixin,
    a_usage_event_subject,
    cost_rate_in_default_book,
    declares_a_markup,
    rate_in_default_book,
    the_book_holding,
)
from apps.platform.audit.actors import Actor
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant
from core.transitions import (
    columns_declared_into_defended_classes)
from core.vocabulary import (
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
)

QUANTITY = "prompt_tokens"
ANOTHER_QUANTITY = "completion_tokens"
ONE_DENOMINATOR = 1_000_000
PROVIDER = "openai"
EVENT_TYPE = "chat"

#: Distinct powers of ten, so an assertion reading the wrong version names it in
#: its own failure message.
BEFORE = 1_000_000
AFTER = 7_000_000

#: The markup rung, declared wherever a fallthrough would be the wrong answer.
#: 20% over a supplier cost of 500_000 is 600_000 — a figure no rule in this
#: module produces, so "the markup ran" is distinguishable from "a rule did"
#: by the amount alone as well as by the method.
SUPPLIER_COST = 500_000
MARKUP_PERCENTAGE = 20_000_000

#: The one column of a rule this module changes. Named once: every case is about
#: WHICH version answered, not about the arithmetic, so one moving term keeps
#: the expected figures readable.
THE_TERM = "rate_per_unit_micros"

#: Every column of a rule, so "the book is byte-identical" is a claim about the
#: whole row rather than about the two columns somebody remembered.
RULE_COLUMNS = [field.attname for field in Rate._meta.concrete_fields]


def _snapshot(book):
    """Every column of every rule in a book, in a stable order.

    `updated_at` rides along deliberately: a write that touched a row and
    changed nothing else would still move it, and "the book is unchanged" has
    to mean the rows were not written to at all.
    """
    return [
        {column: getattr(rule, column) for column in RULE_COLUMNS}
        for rule in book.rates.order_by("id")
    ]


def _selectors(**overrides):
    base = {name: "" for name in Rate.SELECTORS}
    base.update(provider=PROVIDER, event_type=EVENT_TYPE)
    base.update(overrides)
    return base


class _ABookMixin:

    def setUp(self):
        super().setUp()
        self.tenant = Tenant.objects.create(name="T", default_currency="usd")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.rule = rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY, rate_per_unit_micros=BEFORE)
        self.book = the_book_holding(self.rule)

    def a_change(self, kind=CHANGE_REPRICE, measurement_key=QUANTITY, **terms):
        return {"kind": kind, "measurement_key": measurement_key,
                "provider": PROVIDER, "event_type": EVENT_TYPE, **terms}

    def a_draft(self, changes=None, effective_at=None):
        return BookService.declare(
            self.book, changes or [self.a_change(**{THE_TERM: AFTER})],
            effective_at=effective_at)

    def resolved(self, as_of, measurement_key=QUANTITY):
        return resolve_price(
            PricingSubject(
                receipt_subject=a_usage_event_subject(),
                tenant=self.tenant, customer=self.customer,
                selectors=_selectors(),
                measurements={measurement_key: ONE_DENOMINATOR},
                currency="usd"),
            as_of)


class ADraftClosesNothingTest(_ABookMixin, TestCase):
    """A draft holds the intended changes and writes no rule.

    This is the property everything else rests on: if a draft wrote anything,
    "freely editable and freely discardable" would be a claim about a book that
    had already moved.
    """

    def test_a_draft_writes_no_rule(self):
        before = _snapshot(self.book)
        version_before = self.book.version

        record = self.a_draft()

        self.assertEqual(record.declaration_status, DECLARATION_STATUS_DRAFT)
        self.assertEqual(_snapshot(self.book), before)
        self.book.refresh_from_db()
        self.assertEqual(self.book.version, version_before)
        self.assertEqual(record.opened_rule_ids, [])
        self.assertEqual(record.closed_rule_ids, [])
        self.assertIsNone(record.published_at)

    def test_discarding_a_draft_leaves_the_book_byte_identical(self):
        before = _snapshot(self.book)
        record = self.a_draft()

        BookService.discard(record)

        self.assertEqual(_snapshot(self.book), before)
        self.assertFalse(
            PricingBookPublish.objects.filter(pk=record.pk).exists())

    def test_a_draft_is_freely_editable_because_nothing_reads_it_yet(self):
        """Re-stating the intended changes is a correction, not a second act.

        The record is a draft, so every column of it may move — which is what
        the database rule below permits by never firing on one, and what makes
        one action name cover declaring and re-declaring.
        """
        record = self.a_draft()
        before = _snapshot(self.book)

        record.changes = [self.a_change(kind=CHANGE_RETIRE)]
        record.save()

        record.refresh_from_db()
        self.assertEqual(record.changes[0]["kind"], CHANGE_RETIRE)
        self.assertEqual(_snapshot(self.book), before)


class OneClockClosesTheBoundaryAndOpensItTest(_ABookMixin, TestCase):

    def test_the_outgoing_close_and_the_incoming_open_are_one_value(self):
        effective_at = timezone.now()
        record = self.a_draft(effective_at=effective_at)

        BookService.publish_declared(record)

        outgoing = Rate.objects.get(pk=self.rule.pk)
        incoming = Rate.objects.get(pk=record.opened_rule_ids[0])
        self.assertEqual(outgoing.valid_to, effective_at)
        self.assertEqual(incoming.valid_from, effective_at)
        self.assertEqual(outgoing.valid_to, incoming.valid_from)
        self.assertEqual([str(self.rule.pk)], record.closed_rule_ids)

    def test_no_instant_falls_between_two_versions_of_a_rule(self):
        """The boundary, and the microsecond either side.

        ⚠ **THE FIXTURE DECLARES A MARKUP RUNG ON PURPOSE.** The defect this act
        exists to close was not an exception: an event landing in the uncovered
        interval matched no rule, fell through to markup and came back a
        plausible number with nothing raised anywhere. So the assertion is not
        merely that an amount came back — it is that the method is the rule's
        and the amount is a rule's, at every one of the three instants.
        """
        cost_rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY, rate_per_unit_micros=SUPPLIER_COST)
        declares_a_markup(self.tenant, percentage_micros=MARKUP_PERCENTAGE)
        boundary = timezone.now()
        BookService.publish_declared(self.a_draft(effective_at=boundary))

        one_microsecond = timedelta(microseconds=1)
        for name, as_of, expected in (
                ("the microsecond before", boundary - one_microsecond, BEFORE),
                ("the boundary instant", boundary, AFTER),
                ("the microsecond after", boundary + one_microsecond, AFTER)):
            with self.subTest(instant=name):
                receipt = self.resolved(as_of)
                self.assertEqual(receipt["pricing"]["method"],
                                 PRICING_METHOD_DIRECT_EVENT_PRICE)
                self.assertEqual(receipt["totals"]["billed_cost_micros"],
                                 expected)


class APublishedRecordIsNotEditableTest(_ABookMixin,
                                        RefusalThroughEveryDoorMixin,
                                        TestCase):
    """Immutable once published, through every door.

    ⚠ `REFUSAL_NAME` names the COLUMN as well as the transition class. Two
    mechanisms guard this table — the trigger and the value-set `CHECK` — and
    "something refused this" stopped being evidence of anything the moment the
    second one landed.
    """

    REFUSAL_NAME = r"declaration_status is declared resolve_once"

    def _published(self):
        record = self.a_draft()
        BookService.publish_declared(record, actor=Actor(
            kind="member", id="m1", display="ada@example.com"))
        return record

    def test_no_column_of_a_published_record_moves(self):
        for column, value in (
                ("effective_at", timezone.now() + timedelta(days=1)),
                ("changes", []),
                ("published_at", timezone.now()),
                ("actor_display", "somebody-else@example.com"),
                ("opened_rule_ids", []),
                ("closed_rule_ids", [])):
            with self.subTest(column=column):
                self.assert_every_door_refuses(self._published(),
                                               **{column: value})

    def test_a_published_record_cannot_return_to_draft(self):
        self.assert_every_door_refuses(
            self._published(), declaration_status=DECLARATION_STATUS_DRAFT)

    def test_publishing_twice_is_refused_before_it_reaches_the_database(self):
        record = self._published()
        with self.assertRaisesRegex(ValueError, "already published"):
            BookService.publish_declared(record)

    def test_a_published_record_cannot_be_discarded(self):
        record = self._published()
        with self.assertRaisesRegex(ValueError, "already closed and opened"):
            BookService.discard(record)
        self.assertTrue(
            PricingBookPublish.objects.filter(pk=record.pk).exists())


class TheOneAdmittedMoveIsAdmittedTest(_ABookMixin, TestCase):
    """A rule that refused every write would satisfy the refusals alone.

    A fresh draft per door, because the move is one-way: the record the previous
    door published can never be returned to draft, which is the refusal above.
    """

    def test_a_draft_publishes_through_every_door(self):
        for name, door in DOORS:
            with self.subTest(door=name):
                record = self.a_draft()
                door(record, declaration_status=DECLARATION_STATUS_PUBLISHED)
                record.refresh_from_db()
                self.assertEqual(record.declaration_status,
                                 DECLARATION_STATUS_PUBLISHED)


class AGreenDeclarationCheckDoesNotProveTheRuleHoldsTest(_ABookMixin, TestCase):
    """The declaration walk proves the column is NAMED by a rule, never held.

    Slice 3's gate is a word-boundary search over the trigger bodies on a table,
    so a rule that spells the column and refuses nothing passes it. That is
    worth having — it judges a new declaration on the day it is made — and it is
    not evidence, which is why the behavioural classes above exist. Measured
    here rather than argued, through the gate's own entry point.
    """

    BODY_THAT_REFUSES_NOTHING = """
    CREATE OR REPLACE FUNCTION ubb_book_publish_declared_transitions()
    RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE ignored text;
    BEGIN
        ignored := OLD.declaration_status;
        RETURN NEW;
    END;
    $$;
    """

    def test_a_rule_that_refuses_nothing_still_passes_the_declaration_check(self):
        from django.apps import apps as django_apps
        from django.db import connection

        from apps.platform.tests.test_transition_class_declarations import (
            columns_the_database_does_not_defend, declaring_models_by_table)

        record = self.a_draft()
        BookService.publish_declared(record)
        with connection.cursor() as cursor:
            cursor.execute(self.BODY_THAT_REFUSES_NOTHING)

        # The gate reports a clean board...
        self.assertEqual(
            columns_the_database_does_not_defend(
                columns_declared_into_defended_classes(
                    django_apps.get_models()),
                declaring_models_by_table()),
            [])
        # ...over a database that now admits the write the rule forbids.
        PricingBookPublish.objects.filter(pk=record.pk).update(
            declaration_status=DECLARATION_STATUS_DRAFT)
        record.refresh_from_db()
        self.assertEqual(record.declaration_status, DECLARATION_STATUS_DRAFT)


class TheRuleIsHeldByOneTriggerOnThisTableTest(TestCase):
    """The mechanism, read off the live database rather than off the migration.

    A migration that ran is evidence that a file executed, not that a rule is
    installed.
    """

    TRIGGER = "trg_book_publish_declared_transitions"
    TABLE = "ubb_pricing_book_publish"

    def _rules_on_the_table(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT t.tgname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname = %s AND NOT t.tgisinternal", [self.TABLE])
            return {name for (name,) in cursor.fetchall()}

    def _this_rule(self):
        """This rule's `(tgtype, definition, body)`, asked for BY NAME.

        By name and never by index: `pg_trigger` promises no order, so anything
        reading "the first row" starts reading whichever rule Postgres happened
        to hand back the day a second one lands.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT t.tgtype, pg_get_triggerdef(t.oid), p.prosrc "
                "FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_proc p ON p.oid = t.tgfoid "
                "WHERE c.relname = %s AND t.tgname = %s",
                [self.TABLE, self.TRIGGER])
            return cursor.fetchone()

    def test_the_table_carries_exactly_this_one_rule(self):
        """An exact SET, so a second rule arriving here is something a reader of
        this module has to agree to rather than something a count absorbs."""
        self.assertEqual(self._rules_on_the_table(), {self.TRIGGER})

    def test_it_fires_before_each_updated_row_and_on_nothing_else(self):
        """`BEFORE UPDATE ... FOR EACH ROW`, read out of `tgtype`'s bits.

        **The two `assertFalse`s are ADR-0007's Consequences discharged.** That
        clause requires a database-enforced transition's per-write cost to be
        measured rather than assumed, and a trigger that cannot fire on a
        statement pays zero on it — a stronger claim than a benchmark reporting
        a small number, and one that cannot drift. Declaring a draft is an
        `INSERT` and discarding one is a `DELETE`; neither reaches this rule.
        Nothing on the metering path writes this table at all.

        `BEFORE` and row-level: an `AFTER` trigger would refuse by rolling back
        a row already written, and a statement-level one cannot see `OLD`, which
        is the only thing this rule reads.
        """
        tgtype, _, _ = self._this_rule()
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 4), "does not fire on UPDATE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")
        self.assertFalse(tgtype & (1 << 3), "fires on DELETE")

    def test_an_update_to_a_draft_never_enters_the_function(self):
        """The `WHEN` clause, which is what keeps a draft freely editable.

        The rule's whole subject is a row that is already published, so every
        write to a draft — the editing, and the publish itself — is filtered out
        before the function is called.
        """
        _, definition, _ = self._this_rule()
        self.assertIn("WHEN", definition)
        self.assertIn("old.declaration_status", definition.lower())
        self.assertIn(f"'{DECLARATION_STATUS_PUBLISHED}'", definition)

    def test_the_refusal_names_the_column_and_not_only_the_class(self):
        """⚠ Read with `--` comments stripped, on #325's evidence.

        An SQL comment inside `prosrc` satisfies "the column is named in the
        trigger body" completely: a fix once passed with the whole branch
        deleted because the comment explaining that branch still spelled the
        column. Two mechanisms guard this table's status — this rule and the
        value-set `CHECK` — so a refusal naming only its transition class would
        not say which one spoke.
        """
        _, _, source = self._this_rule()
        body = re.sub(r"--[^\n]*", "", source)
        self.assertIn("declaration_status is declared resolve_once", body)
        self.assertIn(f"'{DECLARATION_STATUS_PUBLISHED}'", body)


class ThePublishRecordSaysWhoDecidedItTest(_ABookMixin, TestCase):

    def test_a_past_price_is_traceable_to_the_publish_that_set_it(self):
        """From a price in force at a moment, back to somebody's decision.

        The chain is the one a tenant answering their own customer would walk:
        the receipt names the rule that priced the event, the publish record
        names the rule versions it opened, and the record says who published it
        and when. Nothing here is read out of a local — every hop goes back to
        the database.
        """
        actor = Actor(kind="member", id="m1", display="ada@example.com")
        effective_at = timezone.now()
        record = self.a_draft(effective_at=effective_at)
        BookService.publish_declared(record, actor=actor)

        receipt = self.resolved(effective_at)
        priced_by = receipt["provenance"]["price_rate_ids"][QUANTITY]

        publish = PricingBookPublish.objects.get(
            opened_rule_ids__contains=[priced_by])
        self.assertEqual(publish.pk, record.pk)
        self.assertEqual(publish.actor_kind, actor.kind)
        self.assertEqual(publish.actor_id, actor.id)
        self.assertEqual(publish.actor_display, actor.display)
        self.assertEqual(publish.effective_at, effective_at)
        self.assertIsNotNone(publish.published_at)
        self.assertEqual(publish.closed_rule_ids, [str(self.rule.pk)])


class TheThreeChangesAreAllPublishesTest(_ABookMixin, TestCase):
    """Adding a rule, repricing one and retiring one, each as a publish."""

    def test_adding_a_rule_is_a_publish(self):
        declares_a_quantity(self.tenant, ANOTHER_QUANTITY)
        record = self.a_draft([self.a_change(
            kind=CHANGE_ADD, measurement_key=ANOTHER_QUANTITY,
            **{THE_TERM: AFTER})])

        BookService.publish_declared(record)

        added = Rate.objects.get(pk=record.opened_rule_ids[0])
        self.assertEqual(added.measurement_key, ANOTHER_QUANTITY)
        self.assertEqual(getattr(added, THE_TERM), AFTER)
        self.assertIsNone(added.valid_to)
        self.assertEqual(record.closed_rule_ids, [])
        self.assertNotEqual(added.lineage_id, self.rule.lineage_id)

    def test_repricing_a_rule_is_a_publish(self):
        record = self.a_draft()

        BookService.publish_declared(record)

        replacement = Rate.objects.get(pk=record.opened_rule_ids[0])
        self.rule.refresh_from_db()
        self.assertEqual(getattr(replacement, THE_TERM), AFTER)
        self.assertEqual(getattr(self.rule, THE_TERM), BEFORE)
        self.assertIsNotNone(self.rule.valid_to)
        # A reprice continues the rule's history rather than starting one.
        self.assertEqual(replacement.lineage_id, self.rule.lineage_id)

    def test_retiring_a_rule_is_a_publish(self):
        record = self.a_draft([self.a_change(kind=CHANGE_RETIRE)])

        BookService.publish_declared(record)

        self.rule.refresh_from_db()
        self.assertEqual(self.rule.valid_to, record.effective_at)
        self.assertEqual(record.opened_rule_ids, [])
        self.assertEqual(record.closed_rule_ids, [str(self.rule.pk)])

    def test_a_retirement_states_no_terms(self):
        with self.assertRaisesRegex(ValueError, "opens no rule"):
            self.a_draft([self.a_change(kind=CHANGE_RETIRE,
                                        **{THE_TERM: AFTER})])


class TheDiffIsReadableBeforeCommittingToItTest(_ABookMixin, TestCase):

    def test_the_diff_names_what_changes_and_from_what(self):
        record = self.a_draft()

        row, = BookService.diff(record)
        self.assertEqual(row["kind"], CHANGE_REPRICE)
        self.assertEqual(row["measurement_key"], QUANTITY)
        self.assertEqual(row["selectors"],
                         {"provider": PROVIDER, "event_type": EVENT_TYPE})
        self.assertEqual(row["before"][THE_TERM], BEFORE)
        self.assertEqual(row["after"][THE_TERM], AFTER)

    def test_reading_the_diff_writes_nothing(self):
        before = _snapshot(self.book)
        BookService.diff(self.a_draft())
        self.assertEqual(_snapshot(self.book), before)

    def test_the_diff_is_computed_at_the_effective_instant_not_as_of_now(self):
        """⚠ The two answers differ, and only one of them is the truth.

        The book here already carries a scheduled change — a rule closing at
        `switchover` and its replacement opening there, which is exactly what a
        previous forward-dated publish leaves behind. A publish effective AFTER
        that switchover supersedes the replacement, not the rule in force today.
        A diff computed as of now would show the tenant the wrong `before`, and
        then the publish would write something else.
        """
        switchover = timezone.now() + timedelta(days=1)
        after_the_switchover = switchover + timedelta(days=1)
        scheduled = self.rule
        Rate.objects.filter(pk=scheduled.pk).update(valid_to=switchover)
        replacement = rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY, rate_per_unit_micros=AFTER,
            valid_from=switchover)

        record = self.a_draft(effective_at=after_the_switchover)
        row, = BookService.diff(record)

        self.assertEqual(row["before"][THE_TERM], AFTER)
        self.assertNotEqual(row["before"][THE_TERM], BEFORE)

        # And the publish acts on the same rule the diff named.
        BookService.publish_declared(record)
        self.assertEqual(record.closed_rule_ids, [str(replacement.pk)])
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.valid_to, switchover)


class TheBookAtAnInstantIsTheHalfOpenWindowTest(_ABookMixin, TestCase):
    """Both edges of `[valid_from, valid_to)`, asked of the PLANNER.

    ⚠ **THIS CLASS EXISTS BECAUSE A MUTATION FOUND ITS ABSENCE.** Replacing
    "the rules in force at the effective instant" with "the book's open rules"
    left every other case in this module green — including the diff case above,
    whose fixture happens to give both readings the same answer, since the rule
    it means is the open one. "As of the effective instant" and "whichever rules
    are open" are two different wrong implementations away from each other, and
    only these two edges tell them apart.
    """

    def test_a_rule_that_has_not_opened_yet_is_not_there_to_reprice(self):
        """The lower edge. An open rule dated forward is in the book LATER, and
        a publish landing before it is not repricing anything.

        Built with its moment rather than moved into it: `Rate.valid_from` is
        declared frozen and a trigger refuses the `UPDATE`, which is the rule
        working — a rate takes effect when its writer said, once.
        """
        rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=ANOTHER_QUANTITY, rate_per_unit_micros=BEFORE,
            valid_from=timezone.now() + timedelta(days=2))

        with self.assertRaisesRegex(ValueError, "nothing to reprice"):
            self.a_draft([self.a_change(measurement_key=ANOTHER_QUANTITY,
                                        **{THE_TERM: AFTER})],
                         effective_at=timezone.now())

    def test_a_rule_closing_exactly_at_the_instant_is_already_gone(self):
        """The upper edge, and the half-open range's whole point: a rule covers
        `[valid_from, valid_to)`, so the instant it closes at is the first one
        it does not cover — which is exactly what makes one publish's close and
        the next one's open the same value with no gap and no overlap."""
        boundary = timezone.now() + timedelta(days=1)
        Rate.objects.filter(pk=self.rule.pk).update(valid_to=boundary)

        record = self.a_draft(
            [self.a_change(kind=CHANGE_ADD, **{THE_TERM: AFTER})],
            effective_at=boundary)

        row, = BookService.diff(record)
        self.assertEqual(row["kind"], CHANGE_ADD)
        self.assertIsNone(row["before"])


class AChangeThatCannotBeCarriedOutIsRefusedWhileDecidingTest(
        _ABookMixin, TestCase):
    """Refused at declaration, so a tenant finds out while still deciding."""

    def test_an_undeclared_quantity_cannot_be_priced(self):
        with self.assertRaisesRegex(ValueError, "no declared quantity"):
            self.a_draft([self.a_change(kind=CHANGE_ADD,
                                        measurement_key="nobody_declared_this",
                                        **{THE_TERM: AFTER})])

    def test_a_rule_that_is_not_there_cannot_be_repriced(self):
        declares_a_quantity(self.tenant, ANOTHER_QUANTITY)
        with self.assertRaisesRegex(ValueError, "nothing to reprice"):
            self.a_draft([self.a_change(measurement_key=ANOTHER_QUANTITY,
                                        **{THE_TERM: AFTER})])

    def test_a_rule_already_there_cannot_be_added_again(self):
        with self.assertRaisesRegex(ValueError, "already prices"):
            self.a_draft([self.a_change(kind=CHANGE_ADD, **{THE_TERM: AFTER})])

    def test_one_publish_states_one_outcome_per_rule(self):
        with self.assertRaisesRegex(ValueError, "already changes the rule"):
            self.a_draft([self.a_change(**{THE_TERM: AFTER}),
                          self.a_change(kind=CHANGE_RETIRE)])

    def test_a_rule_already_scheduled_to_close_cannot_be_repriced(self):
        """`Rate.valid_to` is declared set_once, so a close cannot be moved.

        Refusing it here is the readable half of a rule the database holds
        anyway: without this the publish would reach the trigger mid-transaction
        and answer an `IntegrityError` about a column the caller never named.
        """
        Rate.objects.filter(pk=self.rule.pk).update(
            valid_to=timezone.now() + timedelta(days=1))
        with self.assertRaisesRegex(ValueError, "already scheduled to close"):
            self.a_draft()

    def test_an_unknown_kind_of_change_is_refused(self):
        with self.assertRaisesRegex(ValueError, "kind must be one of"):
            self.a_draft([self.a_change(kind="repriced")])

    def test_nothing_is_written_when_one_change_of_a_set_is_refused(self):
        before = _snapshot(self.book)
        with self.assertRaises(ValueError):
            self.a_draft([self.a_change(**{THE_TERM: AFTER}),
                          self.a_change(measurement_key="nobody_declared_this")])
        self.assertEqual(_snapshot(self.book), before)
        self.assertEqual(PricingBookPublish.objects.count(), 0)
