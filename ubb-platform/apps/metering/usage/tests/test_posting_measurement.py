"""The measured quantities became a child record with a lifecycle of their own (#270).

Two things are worth proving here and they are not the same thing.

1. **The child exists and is shaped as ruled** — singular, one-to-one by a
   unique posting reference, its table tracking its model name, carrying the
   quantities, when they were recorded, and a nullable retention horizon.
2. **Absence is expressed by absence.** Where a posting is a synthetic charge —
   a Task sold at one agreed price — the child does not exist. Not an empty
   record, not a record of zeroes. The discriminator column that will *name*
   that kind arrives in a later slice, so what is pinned today is the mechanism
   underneath it: nothing manufactures a child, and a posting that was never
   measured has none. `AbsenceIsExpressedByAbsenceTest` carries its own control
   — a measured posting recorded through the real path, whose child IS there —
   so that "no child" is a fact about this posting rather than about a table
   that happens to be empty.

Before the cutover (#190) a third thing was proved here: **the move carried its
data, in both directions** — `usage/0031`'s fold, its operation order and its
forward and reverse callables, run against real rows. That chain is gone and
those cases retired with it; the child's shape is what the classes below hold.

**The retention horizon has exactly one clock, started on purpose (W5).**
`prunable_at` was a column with no clock behind it until #190 ruled the number
(400 days) and the job (a daily prune). It is now the release fact that prune
writes, SET_ONCE (`pruning.py`, `trg_posting_measurement_released_once`);
recording still leaves it
NULL, and nothing else writes it. `TheHorizonHasExactlyOneClockTest` holds
that: one scheduled prune, and no deadline stamped at recording.

**And #271 makes the difference sayable.** Point 2 above pins that a pruned
payload and a never-measured one are two different facts in the table; on their
own they are still one empty bag to anybody reading the response.
`TheDerivedMeasurementsStatusTest` is the rule that separates them, over the two
inputs the registry declares for `measurements_status` and covering all four of
their combinations. It lives here rather than in a module of its own because its
subject is this child record's presence, and because a new file naming the
retired quantity token would owe a sixty-sixth entry on a debt this slice is
paying down rather than adding to.
"""
from django.db import IntegrityError, transaction
from django.db.models import NOT_PROVIDED
from django.test import TestCase

from apps.metering.pricing.tests._helpers import declares_a_markup
from apps.metering.usage.measurements import (
    measurements_status,
    measurements_status_for,
    posting_kind,
)
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.tests._helpers import (
    release_and_prune, settle_the_supplier_cost)
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.transitions import DATABASE_DEFENDED, RECORD_RULE, SET_ONCE
from core.vocabulary import (
    MEASUREMENTS_STATUS_AVAILABLE,
    MEASUREMENTS_STATUS_NOT_APPLICABLE,
    MEASUREMENTS_STATUS_PRUNED,
    MEASUREMENTS_STATUS_VALUES,
    USAGE_EVENT_KIND_METERED_USAGE,
    USAGE_EVENT_KIND_TASK_CHARGE,
    USAGE_EVENT_KIND_VALUES,
)
from apps.metering.usage.tests._helpers import a_posting

#: The columns the child was ruled to carry, over and above the ones every
#: record in this repository inherits.
DECLARED_COLUMNS = ("posting", "measurements", "recorded_at", "prunable_at")


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    # ⚠ **THE CHILD'S RULE READS THE PRICE STATUS AS WELL AS THE COST STATUS**
    # (`trg_posting_measurement_pruning`), so a tenant that has declared no markup rung can
    # prune nothing at all: every posting it records resolves to `unknown`
    # (#356), which is one of the two states the rule refuses to let a
    # measurement leave. A rung of nothing settles the price at the supplier's
    # figure, which is what these fixtures always meant, and keeps the pruning
    # cases about the COST condition they name.
    declares_a_markup(tenant)
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


class TheChildRecordTest(TestCase):
    """Singular, one-to-one, and named for what it is."""

    def test_its_table_tracks_its_model_name(self):
        self.assertEqual(PostingMeasurement._meta.db_table,
                         "ubb_posting_measurement")

    def test_it_is_one_to_one_with_its_posting_by_a_unique_reference(self):
        field = PostingMeasurement._meta.get_field("posting")
        self.assertTrue(field.one_to_one)
        self.assertTrue(field.unique)
        self.assertEqual(field.related_model, Posting)
        # Singular both ways: a posting has *a* measurement.
        self.assertEqual(field.remote_field.get_accessor_name(), "measurement")

    def test_it_carries_the_quantities_the_time_and_the_horizon(self):
        self.assertEqual(
            [f.name for f in PostingMeasurement._meta.fields
             if f.name in DECLARED_COLUMNS],
            list(DECLARED_COLUMNS))

    def test_a_second_child_for_one_posting_is_refused(self):
        tenant, customer = _tenant_and_customer()
        posting = a_posting(
            tenant=tenant, customer=customer, idempotency_key="i")
        PostingMeasurement.objects.create(
            posting=posting, measurements={"input_tokens": "12"},
            recorded_at=posting.created_at)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PostingMeasurement.objects.create(
                    posting=posting, measurements={},
                    recorded_at=posting.created_at)

    def test_recorded_at_is_when_the_quantities_were_recorded(self):
        """Not when this row was written — the two are different facts.

        A row written after its posting — as `usage/0031` once folded every
        bag out of its posting, long after each arrived, before the cutover
        squash (#190) — still carries the
        moment its posting arrived. Only a column of its own can say that,
        which is why `created_at` does not stand in for it.
        """
        tenant, customer = _tenant_and_customer()
        result = UsageService.record_usage(
            tenant, customer, "i1", measurements={"input_tokens": "900"})
        measurement = PostingMeasurement.objects.get(
            posting_id=result["event_id"])
        posting = Posting.objects.get(id=result["event_id"])
        self.assertEqual(measurement.recorded_at, posting.created_at)

    def test_the_quantities_are_read_through_the_posting_and_never_written(self):
        """The move cost no reader anything, and it cost every writer.

        `Posting.measurements` is a read-through onto the child now. Every
        reader that used to read the column reads this and sees what it saw
        before; a writer that tries to set it fails, which is the half that
        makes "there is one encoding of the quantities" true rather than
        merely intended (ADR-0006 §4).
        """
        tenant, customer = _tenant_and_customer()
        result = UsageService.record_usage(
            tenant, customer, "i1", measurements={"input_tokens": "1200"})
        posting = Posting.objects.get(id=result["event_id"])

        self.assertEqual(posting.measurements, {"input_tokens": "1200"})
        with self.assertRaises(AttributeError):
            posting.measurements = {"input_tokens": "0"}
        self.assertNotIn("measurements",
                         {f.name for f in Posting._meta.fields})

    # A third assertion here pinned the strict cost-coverage flag's default,
    # carried in from `test_measurements_field.py` when this module replaced
    # it. #321 deleted the column, so the default no longer exists to pin;
    # what replaces it is an absence, asserted in
    # `api/v1/tests/test_onboarding_is_not_a_wall.py` beside the behaviour.


class AbsenceIsExpressedByAbsenceTest(TestCase):
    """A posting that was never measured has no child. Not an empty one."""

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        # The control: an ordinary metered posting, recorded through the real
        # path. Without it, every assertion below would pass just as well
        # against a table nothing ever writes to.
        self.measured = Posting.objects.get(
            id=UsageService.record_usage(
                self.tenant, self.customer, "i1",
                measurements={"input_tokens": "1200"})["event_id"])
        # The subject: a posting standing in for the synthetic charge — a Task
        # sold at one agreed price, projected as a posting with revenue and no
        # provider operation behind it. The `kind` column that will name it
        # lands in a later slice; what makes the charge's child absent is that
        # nothing outside the metered recording path creates one, and that is
        # what this pins.
        self.charge = a_posting(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="chg_1",
            billed_cost_micros=250_000)

    def test_the_control_has_a_child(self):
        self.assertEqual(self.measured.measurement.measurements,
                         {"input_tokens": "1200"})

    def test_the_synthetic_charge_posting_has_none(self):
        self.assertFalse(
            PostingMeasurement.objects.filter(posting=self.charge).exists())
        with self.assertRaises(PostingMeasurement.DoesNotExist):
            self.charge.measurement

    def test_the_absence_is_absence_and_not_an_empty_record(self):
        """One child in the table, and it belongs to the measured posting.

        An empty record would satisfy "no quantities" perfectly and would be
        exactly the thing the split exists to stop — a row that cannot say
        whether it was pruned, never applied, or measured as nothing.
        """
        self.assertEqual(
            list(PostingMeasurement.objects.values_list("posting_id", flat=True)),
            [self.measured.id])

    def test_nothing_creates_the_child_on_read(self):
        for _ in range(2):
            with self.assertRaises(PostingMeasurement.DoesNotExist):
                self.charge.measurement
            # The read-through answers the empty bag every reader saw before
            # the split, and creates nothing to do it.
            self.assertEqual(self.charge.measurements, {})
        self.assertEqual(PostingMeasurement.objects.count(), 1)


class TheDerivedMeasurementsStatusTest(TestCase):
    """The three answers, and the rule that produces them (#271).

    `measurements_status` is DERIVED and never stored: every value here is
    computed from facts the row already carries, which is why no column holds
    it and why G10 is the gate that proves so. What is asserted below is the
    behaviour — a posting with its record, one whose record was removed, and a
    synthetic charge — plus the rule being total over its two declared inputs,
    because three examples cannot show that the fourth combination has an
    answer at all.

    No mock anywhere: the measured posting is recorded through the real path,
    and `pruned` is produced by deleting the real child rather than by
    arranging for a reader to return nothing.
    """

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        self.posting = Posting.objects.get(
            id=UsageService.record_usage(
                self.tenant, self.customer, "i1",
                measurements={"input_tokens": "1200"})["event_id"])

    def _fresh(self):
        """Re-read, so a cached reverse relation cannot answer for the table."""
        return Posting.objects.get(pk=self.posting.pk)

    def test_a_posting_with_its_record_is_available(self):
        self.assertEqual(measurements_status_for(self._fresh()),
                         MEASUREMENTS_STATUS_AVAILABLE)

    def test_a_posting_whose_record_was_removed_is_pruned(self):
        """The whole point of the concept: removal is not emptiness.

        Note what is NOT asserted — that the quantities read as `{}`. They do,
        and that is exactly the reading this status exists to qualify.

        The removal goes through the two steps the database now requires
        (#354): a metered call with no cost rate behind it records
        `unresolved`, and the child's whole-record rule refuses a `DELETE`
        while its posting is waiting AND before the record's horizon. Settling
        the cost is what a recovery run does; releasing the horizon is what a
        retention clock would do. Only then is there a prune to observe.
        """
        settle_the_supplier_cost(self.posting, 240_000)
        release_and_prune(self.posting)

        posting = self._fresh()
        self.assertEqual(posting.measurements, {})
        self.assertEqual(measurements_status_for(posting),
                         MEASUREMENTS_STATUS_PRUNED)

    def test_a_synthetic_charge_posting_is_not_applicable(self):
        """A Task sold at one agreed price was never measured.

        A REAL row shaped exactly as the projection writes one, and the rule is
        driven with that row's own record state rather than with a hand-typed
        `False`, so what is asserted is a fact about a posting rather than about
        two literals. The projection's own end-to-end assertions live in
        `api/v1/tests/test_the_charge_reaches_the_rails_as_one_marked_posting
        .py`; what this module owns is the reading.

        **⚠ THIS IS THE ASSERTION THE SEAM WAS STATED AT, AND #417 IS WHERE IT
        MOVED.** Until the discriminator landed, the kind had to be PASSED
        because there was no column to read it from — `usage_event_kind`'s
        backend consumer was a G2 debt owned by the slice that builds the
        Charge such a posting is projected from — so the second assertion below
        recorded what an unmarked charge-shaped row read as instead:
        `pruned`, the metered reading of a missing record. The column arrived
        with the projection, the row below carries it, and the second assertion
        now records the answer the rule was always declared to give. It was
        UPDATED rather than deleted: it is the one that announces the change,
        and deleting it would have removed the only place the change is
        visible as a change.
        """
        charge = a_posting(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="chg_1",
            kind=USAGE_EVENT_KIND_TASK_CHARGE,
            billed_cost_micros=250_000)
        measured = PostingMeasurement.objects.filter(posting=charge).exists()
        self.assertFalse(measured, "§E4: absent by construction")

        self.assertEqual(
            measurements_status(USAGE_EVENT_KIND_TASK_CHARGE,
                                measured=measured),
            MEASUREMENTS_STATUS_NOT_APPLICABLE)

        # And the same answer through the serialiser's own path, which is what
        # the rule above is only half of: the first assertion says the rule
        # answers `not_applicable` when handed the kind, and this one says the
        # row is what hands it over. Passing the first while failing this one
        # is exactly the state that stood here before the column existed.
        self.assertEqual(measurements_status_for(charge),
                         MEASUREMENTS_STATUS_NOT_APPLICABLE)

    def test_a_charge_is_not_applicable_even_if_a_record_somehow_exists(self):
        """The kind is read first, and the record's presence is not consulted.

        §E4 makes the child absent by construction for a charge, so this
        combination should never occur — which is precisely why the rule must
        state an answer for it rather than leave one to be inferred. A rule
        that consulted the record here would answer `pruned` for a posting no
        retention horizon ever governed.
        """
        self.assertEqual(
            measurements_status(USAGE_EVENT_KIND_TASK_CHARGE, measured=True),
            MEASUREMENTS_STATUS_NOT_APPLICABLE)

    def test_the_rule_is_total_over_its_two_inputs(self):
        """Four combinations, four answers, and every declared value reachable.

        A three-example test would be satisfied by a rule with a hole in it,
        and the hole would surface as `None` on the published contract.
        """
        answers = {
            (kind, measured): measurements_status(kind, measured=measured)
            for kind in USAGE_EVENT_KIND_VALUES
            for measured in (True, False)
        }
        self.assertEqual(len(answers), 4)
        self.assertTrue(set(answers.values()) <= MEASUREMENTS_STATUS_VALUES)
        self.assertEqual(set(answers.values()), MEASUREMENTS_STATUS_VALUES,
                         "a declared value is unreachable through the rule")

    def test_every_posting_reads_as_a_metered_one_today(self):
        """The seam slice 5 replaces, pinned as the fact it currently is.

        This does NOT claim to fail on the day a discriminator lands — a new
        column would classify a row it can see a marker on, and neither row
        below carries one, so nothing here would go red on its own. What it
        does is put the current reading under a name, in one place, for two
        differently-shaped rows: whoever makes `posting_kind` read a column has
        one function to change and one statement of what it used to answer,
        instead of a constant inlined at each caller.
        """
        self.assertEqual(posting_kind(self._fresh()),
                         USAGE_EVENT_KIND_METERED_USAGE)
        self.assertEqual(
            posting_kind(a_posting(
                tenant=self.tenant, customer=self.customer,
                idempotency_key="chg_2",
                billed_cost_micros=250_000)),
            USAGE_EVENT_KIND_METERED_USAGE)


class EachAmountWentNullableInTheSliceThatOwnedItsMeaningTest(TestCase):
    """The measurements went optional here; the two amounts went one slice each.

    **THE ASYMMETRY THIS CLASS WAS BUILT TO GUARD IS NOW CLOSED, AND THE CLASS
    IS REWRITTEN RATHER THAN RELAXED.** It was `TheNullabilityAsymmetryTest`,
    and its whole subject was that ONE of the two money columns was nullable and
    the other must not yet be. #351 made the second one nullable, on purpose and
    with the status column, database rule and thirty-nine reader repairs that
    entitle it to be — so the claim expired. Renamed to carry the claim it makes
    now, which is not the same claim weakened: **each amount went nullable in
    the slice that owned its meaning, and neither did so before.**

    Deleting it instead would have been the cheap move and the wrong one. The
    rule it encodes is what stopped either column pre-announcing a distinction
    no slice had decided — a second break to repair the first (ADR-0007 §3) —
    and the rule outlives the two columns it has been applied to.

    * Slice 2 owns whether a posting has measurements, so the measurements
      became optional then and neither amount did.
    * Slice 3 (#317) owns whether a SUPPLIER cost is resolved, so
      `provider_cost_micros` went nullable then, defended by the three legal
      combinations in `Posting.Meta`.
    * Slice 4 (#351) owns whether a CUSTOMER price is resolved, so
      `billed_cost_micros` went nullable then, defended by four.

    Each assertion below now fails in BOTH directions rather than one: a column
    that stopped being nullable would lose the distinction its slice exists to
    add, and the shape of each is pinned beside its defending constraint, so a
    column made nullable with no rule behind it fails in the class that owns the
    rule rather than quietly here.
    """

    def test_the_measurements_are_optional(self):
        tenant, customer = _tenant_and_customer()
        posting = a_posting(
            tenant=tenant, customer=customer,
            idempotency_key="i")
        # 0..1, and the zero is reachable: the row commits and reads back with
        # no child, which is what "optional" means for a record whose
        # optionality is carried by the relation rather than by a NULL.
        self.assertEqual(Posting.objects.filter(pk=posting.pk).count(), 1)
        self.assertFalse(
            PostingMeasurement.objects.filter(posting=posting).exists())

    def test_the_supplier_cost_is_nullable_now_that_a_slice_owns_the_meaning(self):
        """#317. The default stays 0, which is not a leftover.

        A writer that says nothing about supplier cost still records `known`
        and zero — the reading every row had before this column could be null,
        and the one every row that already existed kept when it became so. What
        changed is that `NULL` became SAYABLE; who says it is the business of
        the tickets that teach the recording path when a cost is missing.
        """
        field = Posting._meta.get_field("provider_cost_micros")
        self.assertTrue(field.null)
        self.assertEqual(field.default, 0)

    def test_the_customer_price_is_nullable_now_that_a_slice_owns_the_meaning(self):
        """#351, and the assertion is INVERTED rather than deleted.

        This read `assertFalse(field.null)` for two slices, and it was right
        both times: a column that went nullable before its slice would have
        announced a distinction with no status column to qualify it and no rule
        to defend it. Slice 4 supplies both, so the same line now says the
        opposite — which is what makes the file's history readable as a rule
        being followed rather than a check being dropped.

        The default stays 0, as the supplier half's did and for the same reason:
        a writer that says nothing about customer price has recorded what UBB
        holds. What changed is that `NULL` became SAYABLE.
        """
        field = Posting._meta.get_field("billed_cost_micros")
        self.assertTrue(field.null)
        self.assertEqual(field.default, 0)

    def test_neither_amount_went_nullable_without_a_status_beside_it(self):
        """The rule itself, rather than the two instances of it.

        The two assertions above are each about one column and would both pass
        against a column made nullable with nothing to qualify it — which is the
        thing the rule forbids, and the thing a third amount added next year
        would be at risk of. This says it once, over both pairs, by asking the
        declared pairs rather than by naming columns.
        """
        for pair in (SUPPLIER_COST, CUSTOMER_PRICE):
            amount = Posting._meta.get_field(pair.amount_column)
            status = Posting._meta.get_field(pair.status_column)
            self.assertTrue(amount.null, pair.amount_column)
            self.assertFalse(status.null, pair.status_column)


class TheHorizonHasExactlyOneClockTest(TestCase):
    """`prunable_at` is the release fact, and exactly one scheduled job writes
    it: the daily prune (#190 comment 5785029955, W5 ruling 8). Recording
    never stamps a deadline on it."""

    def test_it_is_nullable_and_has_no_default(self):
        field = PostingMeasurement._meta.get_field("prunable_at")
        self.assertTrue(field.null)
        self.assertIs(field.default, NOT_PROVIDED)

    def test_the_recording_path_leaves_it_null(self):
        tenant, customer = _tenant_and_customer()
        result = UsageService.record_usage(
            tenant, customer, "i1", measurements={"input_tokens": "5"})
        self.assertIsNone(
            PostingMeasurement.objects.get(
                posting_id=result["event_id"]).prunable_at)

    def test_exactly_one_scheduled_task_prunes_a_measurement(self):
        """Inverted at its own address by W5: it guarded against a clock being
        started by accident, and the clock is now started on purpose — so it
        holds that the daily prune is the ONE scheduled measurement prune.

        The vacuity guard is the length assertion, not the loop: a schedule
        read as empty would satisfy any count of prune entries below one.
        """
        from django.conf import settings

        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertGreater(len(schedule), 5)
        # Scheduled prunes of something that is NOT a measurement, each named
        # so that a new one is a decision taken here rather than a word that
        # slipped past. The Code Builder's snapshots are derived fixtures with
        # a retention period of their own (#580, ADR-0018 §5), and hold no
        # posting's quantities.
        not_a_measurement = {
            "apps.platform.code_builder.tasks.prune_blueprint_snapshots"}
        self.assertLessEqual(
            not_a_measurement,
            {entry["task"] for entry in schedule.values()},
            "an exemption names a task the schedule no longer runs")
        prunes = [entry["task"] for name, entry in schedule.items()
                  if entry["task"] not in not_a_measurement
                  and ("prune" in name.lower()
                       or "prune" in entry["task"].lower()
                       or "measurement" in entry["task"].lower())]
        self.assertEqual(
            prunes, ["apps.metering.usage.tasks.prune_measurement_detail"])


class TransitionClassesAreDeclaredTest(TestCase):
    """Every column states what may happen to it; exactly one — the release
    fact — states a class the database defends (W5)."""

    def test_every_column_of_the_child_is_declared(self):
        self.assertEqual(
            set(PostingMeasurement.transition_classes),
            {f.name for f in PostingMeasurement._meta.fields})

    def test_every_column_but_the_release_declares_the_record_rule(self):
        self.assertEqual(
            {column: declared for column, declared
             in PostingMeasurement.transition_classes.items()
             if declared != RECORD_RULE},
            {"prunable_at": SET_ONCE})

    def test_the_record_rule_is_not_a_class_the_database_defends(self):
        self.assertNotIn(RECORD_RULE, DATABASE_DEFENDED)
