"""The measured quantities became a child record with a lifecycle of their own (#270).

Three things are worth proving here and they are not the same thing.

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
3. **The move carried its data, in both directions.** ADR-0007 §1 refuses a
   migration that adds a column beside the one it claims to move; the fold's
   forward and reverse callables are therefore run against a real database with
   real rows, rather than being asserted to exist.

**The retention horizon ships with no clock behind it.** `prunable_at` is a
column and nothing else: no prune job, no schedule, no owner, no default. Two
merged decisions independently record that no document anywhere states the short
clock, and shipping a column is not the same as starting one. `TheHorizonHasNoClockBehindItTest`
is what stops one being started by accident.
"""
from django.db import IntegrityError, connection, transaction
from django.db import migrations as operations
from django.db.migrations.loader import MigrationLoader
from django.db.models import NOT_PROVIDED
from django.test import TestCase

from apps.metering.usage.models import Posting, PostingMeasurement
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.transitions import DATABASE_DEFENDED, RECORD_RULE

APP_LABEL = "usage"
FOLD_MIGRATION = "0031_the_measurements_become_a_child_record"
PARENT_MIGRATION = "0030_the_usage_row_becomes_the_posting"

#: The columns the child was ruled to carry, over and above the ones every
#: record in this repository inherits.
DECLARED_COLUMNS = ("posting", "usage_metrics", "recorded_at", "prunable_at")


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
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
        posting = Posting.objects.create(
            tenant=tenant, customer=customer, request_id="r", idempotency_key="i")
        PostingMeasurement.objects.create(
            posting=posting, usage_metrics={"input_tokens": 12},
            recorded_at=posting.created_at)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PostingMeasurement.objects.create(
                    posting=posting, usage_metrics={},
                    recorded_at=posting.created_at)

    def test_recorded_at_is_when_the_quantities_were_recorded(self):
        """Not when this row was written — the two are different facts.

        A row folded out of a posting by 0031 carries the moment its posting
        arrived, which is long before the fold ran. Only a column of its own can
        say that, which is why `created_at` does not stand in for it.
        """
        tenant, customer = _tenant_and_customer()
        result = UsageService.record_usage(
            tenant, customer, "r1", "i1", usage_metrics={"input_tokens": 900})
        measurement = PostingMeasurement.objects.get(
            posting_id=result["event_id"])
        posting = Posting.objects.get(id=result["event_id"])
        self.assertEqual(measurement.recorded_at, posting.created_at)

    def test_the_quantities_are_read_through_the_posting_and_never_written(self):
        """The move cost no reader anything, and it cost every writer.

        `Posting.usage_metrics` is a read-through onto the child now. Every
        reader that used to read the column reads this and sees what it saw
        before; a writer that tries to set it fails, which is the half that
        makes "there is one encoding of the quantities" true rather than
        merely intended (ADR-0006 §4).
        """
        tenant, customer = _tenant_and_customer()
        result = UsageService.record_usage(
            tenant, customer, "r1", "i1", usage_metrics={"input_tokens": 1200})
        posting = Posting.objects.get(id=result["event_id"])

        self.assertEqual(posting.usage_metrics, {"input_tokens": 1200})
        with self.assertRaises(AttributeError):
            posting.usage_metrics = {"input_tokens": 0}
        self.assertNotIn("usage_metrics",
                         {f.name for f in Posting._meta.fields})

    def test_the_strict_coverage_flag_still_defaults_off(self):
        """Carried in from `test_usage_metrics_field.py`, which this module
        replaces: that file was named for a column that is no longer on the
        posting, and its one assertion about the tenant flag beside it would
        otherwise have been lost with it.
        """
        tenant, _ = _tenant_and_customer()
        self.assertIs(tenant.require_cost_card_coverage, False)


class AbsenceIsExpressedByAbsenceTest(TestCase):
    """A posting that was never measured has no child. Not an empty one."""

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        # The control: an ordinary metered posting, recorded through the real
        # path. Without it, every assertion below would pass just as well
        # against a table nothing ever writes to.
        self.measured = Posting.objects.get(
            id=UsageService.record_usage(
                self.tenant, self.customer, "r1", "i1",
                usage_metrics={"input_tokens": 1200})["event_id"])
        # The subject: a posting standing in for the synthetic charge — a Task
        # sold at one agreed price, projected as a posting with revenue and no
        # provider operation behind it. The `kind` column that will name it
        # lands in a later slice; what makes the charge's child absent is that
        # nothing outside the metered recording path creates one, and that is
        # what this pins.
        self.charge = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="", idempotency_key="chg_1",
            billed_cost_micros=250_000)

    def test_the_control_has_a_child(self):
        self.assertEqual(self.measured.measurement.usage_metrics,
                         {"input_tokens": 1200})

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
            self.assertEqual(self.charge.usage_metrics, {})
        self.assertEqual(PostingMeasurement.objects.count(), 1)


class TheNullabilityAsymmetryTest(TestCase):
    """The measurements go optional here; the two cost columns do not.

    It reads like an inconsistency and it is the rule: **each field goes
    nullable in the slice that owns its meaning.** Slice 2 owns whether a
    posting has measurements, so the measurements become optional now. Slices 3
    and 4 own whether a cost is *resolved*, and until then a cost column that
    went nullable would be saying something no slice has decided — `NULL` for
    "not resolved" is exactly the distinction `RESOLVE_ONCE` is being built to
    carry, and pre-announcing it here would be a second break to repair the
    first (ADR-0007 §3).
    """

    def test_the_measurements_are_optional(self):
        tenant, customer = _tenant_and_customer()
        posting = Posting.objects.create(
            tenant=tenant, customer=customer, request_id="r",
            idempotency_key="i")
        # 0..1, and the zero is reachable: the row commits and reads back with
        # no child, which is what "optional" means for a record whose
        # optionality is carried by the relation rather than by a NULL.
        self.assertEqual(Posting.objects.filter(pk=posting.pk).count(), 1)
        self.assertFalse(
            PostingMeasurement.objects.filter(posting=posting).exists())

    def test_the_two_cost_columns_are_untouched_and_still_non_nullable(self):
        for name in ("provider_cost_micros", "billed_cost_micros"):
            with self.subTest(column=name):
                field = Posting._meta.get_field(name)
                self.assertFalse(field.null)
                self.assertEqual(field.default, 0)


class TheHorizonHasNoClockBehindItTest(TestCase):
    """`prunable_at` is a column. There is no policy anywhere behind it."""

    def test_it_is_nullable_and_has_no_default(self):
        field = PostingMeasurement._meta.get_field("prunable_at")
        self.assertTrue(field.null)
        self.assertIs(field.default, NOT_PROVIDED)

    def test_the_recording_path_leaves_it_null(self):
        tenant, customer = _tenant_and_customer()
        result = UsageService.record_usage(
            tenant, customer, "r1", "i1", usage_metrics={"input_tokens": 5})
        self.assertIsNone(
            PostingMeasurement.objects.get(
                posting_id=result["event_id"]).prunable_at)

    def test_no_scheduled_task_prunes_a_measurement(self):
        """The vacuity guard is the length assertion, not the loop.

        A schedule read as empty — a settings import that resolved to nothing —
        would satisfy "no prune entry" and say nothing at all.
        """
        from django.conf import settings

        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertGreater(len(schedule), 5)
        offenders = [name for name, entry in schedule.items()
                     if "prune" in name.lower()
                     or "prune" in entry["task"].lower()
                     or "measurement" in entry["task"].lower()]
        self.assertEqual(offenders, [])


class TransitionClassesAreDeclaredTest(TestCase):
    """Every column states what may happen to it; none states a defended class."""

    def test_every_column_of_the_child_is_declared(self):
        self.assertEqual(
            set(PostingMeasurement.transition_classes),
            {f.name for f in PostingMeasurement._meta.fields})

    def test_they_are_declared_into_the_record_rule(self):
        self.assertEqual(
            set(PostingMeasurement.transition_classes.values()), {RECORD_RULE})

    def test_the_record_rule_is_not_a_class_the_database_defends(self):
        self.assertNotIn(RECORD_RULE, DATABASE_DEFENDED)


class TheFoldCarriesItsDataTest(TestCase):
    """The migration moves the column rather than adding one beside it."""

    def setUp(self):
        self.migration = MigrationLoader(connection).get_migration(
            APP_LABEL, FOLD_MIGRATION)

    def _index_of(self, op_type):
        for index, op in enumerate(self.migration.operations):
            if isinstance(op, op_type):
                return index
        self.fail(f"the migration carries no {op_type.__name__}")

    def test_the_data_moves_before_the_column_goes(self):
        """This ordering IS ADR-0007 §1 for a column that changes tables.

        Autodetected, the two operations arrive the other way round — the
        column is dropped and an empty table is created beside it, which is
        the add-plus-remove §1 refuses and the pre-squash exemption is spent.
        """
        self.assertLess(self._index_of(operations.CreateModel),
                        self._index_of(operations.RunPython))
        self.assertLess(self._index_of(operations.RunPython),
                        self._index_of(operations.RemoveField))

    def test_the_reverse_is_not_a_noop(self):
        run_python = self.migration.operations[
            self._index_of(operations.RunPython)]
        self.assertIsNot(run_python.reverse_code, operations.RunPython.noop)

    def test_every_operation_can_be_reversed(self):
        for op in self.migration.operations:
            with self.subTest(operation=type(op).__name__):
                self.assertTrue(op.reversible)


class TheReverseIsExercisedTest(TestCase):
    """Forward and back, against a real database, with a real row.

    The fold's callables run against the state they see inside the migration:
    the child created, the posting's column not yet dropped. The live table no
    longer has that column, so the test puts it back for its own duration —
    PostgreSQL runs DDL inside the transaction this `TestCase` rolls back, so
    the column leaves with everything else and no other test can see it.
    """

    def setUp(self):
        loader = MigrationLoader(connection)
        self.migration = loader.get_migration(APP_LABEL, FOLD_MIGRATION)
        state = loader.project_state((APP_LABEL, PARENT_MIGRATION))
        for op in self.migration.operations:
            if isinstance(op, operations.CreateModel):
                op.state_forwards(APP_LABEL, state)
        self.historical = state.apps
        self.Posting = self.historical.get_model(APP_LABEL, "Posting")
        self.Measurement = self.historical.get_model(
            APP_LABEL, "PostingMeasurement")
        with connection.schema_editor() as editor:
            editor.add_field(self.Posting,
                             self.Posting._meta.get_field("usage_metrics"))
        self.run_python = next(op for op in self.migration.operations
                               if isinstance(op, operations.RunPython))

    def _run(self, code):
        with connection.schema_editor() as editor:
            code(self.historical, editor)

    def test_a_bag_survives_the_round_trip(self):
        tenant, customer = _tenant_and_customer()
        posting = self.Posting.objects.create(
            tenant_id=tenant.id, customer_id=customer.id,
            request_id="r", idempotency_key="i",
            usage_metrics={"input_tokens": 1200, "searches": 2})

        self._run(self.run_python.code)

        measurement = self.Measurement.objects.get(posting_id=posting.id)
        self.assertEqual(measurement.usage_metrics,
                         {"input_tokens": 1200, "searches": 2})
        self.assertEqual(measurement.recorded_at, posting.created_at)
        self.assertIsNone(measurement.prunable_at)

        # Blank the column first: otherwise a reverse that wrote nothing at all
        # would pass this on the value the forward fold never removed.
        self.Posting.objects.filter(pk=posting.pk).update(usage_metrics={})

        self._run(self.run_python.reverse_code)

        self.assertEqual(
            self.Posting.objects.values_list("usage_metrics", flat=True).get(
                pk=posting.pk),
            {"input_tokens": 1200, "searches": 2})
        self.assertEqual(self.Measurement.objects.count(), 0)

    def test_a_posting_with_no_bag_folds_to_an_empty_one_rather_than_null(self):
        """Every posting the fold sees is a measured one — the discriminator
        that would let it skip a synthetic charge does not exist yet, and
        inventing one at migration time would be guessing at rows it cannot
        classify. `{}` is what those postings already stored inline.
        """
        tenant, customer = _tenant_and_customer()
        posting = self.Posting.objects.create(
            tenant_id=tenant.id, customer_id=customer.id,
            request_id="r", idempotency_key="i", usage_metrics={})

        self._run(self.run_python.code)

        self.assertEqual(
            self.Measurement.objects.get(posting_id=posting.id).usage_metrics,
            {})
