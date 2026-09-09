from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.work.models import CEILING_STATUS_CHOICES, Task
from core.crossing import CeilingAssessment
from core.vocabulary import (
    CEILING_STATUS_CEILING_REACHED, CEILING_STATUS_INDETERMINATE,
    CEILING_STATUS_NOT_APPLICABLE, CEILING_STATUS_VALUES,
    CEILING_STATUS_WITHIN_CEILING)


class TaskModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_task_creation_defaults(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=1_000_000,
        )
        self.assertEqual(task.status, "active")
        self.assertEqual(task.total_billed_cost_micros, 0)
        self.assertEqual(task.total_provider_cost_micros, 0)
        self.assertEqual(task.event_count, 0)
        self.assertIsNone(task.completed_at)

    def test_task_str_representation(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=1_000_000,
            total_billed_cost_micros=500_000,
        )
        self.assertIn("active", str(task))
        self.assertIn("500000", str(task))

    def test_task_with_all_limits(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=5_000_000,
            task_cogs_ceiling_micros=10_000_000,
        )
        self.assertEqual(task.task_cogs_ceiling_micros, 10_000_000)
        self.assertEqual(task.balance_snapshot_micros, 5_000_000)

    def test_task_without_limits(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
        )
        self.assertIsNone(task.task_cogs_ceiling_micros)

    def test_task_with_external_task_id(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
            external_task_id="workflow-abc-123",
        )
        self.assertEqual(task.external_task_id, "workflow-abc-123")

    def test_task_with_metadata(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
            metadata={"workflow": "scouting", "region": "AU"},
        )
        self.assertEqual(task.metadata["workflow"], "scouting")


class TheRowAssessesItsOwnCeilingTest(TestCase):
    """`ceiling_status` is DERIVED on the row, never stored (ADR-0006 R4; #452,
    slice 6 §3): the registry's four-way rule over three columns the row
    already holds — the pinned ceiling, the running known supplier total and
    the unresolved-event count — through the one predicate in
    `core.crossing`. The two utilisation figures travel WITH it as one value
    (`ceiling_assessment`) and are null exactly where no ceiling applies.

    The model is the registry's declared consumer for the concept, so this is
    also where the closed set is held by reference (`CEILING_STATUS_CHOICES`,
    on `TASK_STATUS_CHOICES`'s footing: identities from the registry, wording
    here) — asserted below against the registry's own whole-set name.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Assess")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1")

    def _row(self, *, ceiling, known=0, unresolved=0):
        return Task.objects.create(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0, task_cogs_ceiling_micros=ceiling,
            total_provider_cost_micros=known,
            unresolved_event_count=unresolved)

    def test_no_pinned_ceiling_is_not_applicable_with_no_utilisation(self):
        for known, unresolved in ((0, 0), (10**9, 0), (0, 2), (10**9, 2)):
            row = self._row(ceiling=None, known=known, unresolved=unresolved)
            self.assertEqual(row.ceiling_assessment, CeilingAssessment(
                CEILING_STATUS_NOT_APPLICABLE, None, None))

    def test_known_at_or_above_is_reached_whatever_remains_unresolved(self):
        for known, unresolved in ((1_000, 0), (1_000, 3), (1_001, 0)):
            assessment = self._row(ceiling=1_000, known=known,
                                   unresolved=unresolved).ceiling_assessment
            self.assertEqual(assessment.status, CEILING_STATUS_CEILING_REACHED)
            self.assertGreaterEqual(assessment.used_percentage, 100)
            self.assertEqual(assessment.remaining_micros, 0)

    def test_known_below_is_indeterminate_or_within_by_what_is_unresolved(self):
        indeterminate = self._row(ceiling=1_000, known=400, unresolved=1)
        within = self._row(ceiling=1_000, known=400, unresolved=0)
        # The figures are over the KNOWN total in both, which is why the
        # status is what tells a reader whether they are exact or a floor.
        self.assertEqual(indeterminate.ceiling_assessment, CeilingAssessment(
            CEILING_STATUS_INDETERMINATE, 40, 600))
        self.assertEqual(within.ceiling_assessment, CeilingAssessment(
            CEILING_STATUS_WITHIN_CEILING, 40, 600))

    def test_the_query_form_selects_exactly_the_rows_the_property_calls_reached(self):
        """The patrol's sweep and the analytics reached-count select ROWS with
        `core.crossing.ceiling_reached_q`; the row in hand answers with the
        property. One compare in two spellings, pinned to each other over
        every boundary shape on real rows, so a query cannot say `>` where
        the row says `>=`."""
        from core.crossing import ceiling_reached_q
        rows = [self._row(ceiling=None, known=10**9),
                self._row(ceiling=1_000, known=999),
                self._row(ceiling=1_000, known=1_000),
                self._row(ceiling=1_000, known=1_001),
                self._row(ceiling=1_000, known=999, unresolved=5)]
        selected = set(Task.objects.filter(ceiling_reached_q(
            "total_provider_cost_micros", "task_cogs_ceiling_micros")
        ).values_list("id", flat=True))
        reached = {row.id for row in rows
                   if row.ceiling_assessment.status == CEILING_STATUS_CEILING_REACHED}
        self.assertEqual(selected, reached)
        self.assertEqual(len(reached), 2)  # on the line, and past it

    def test_the_model_holds_the_registrys_whole_set_by_reference(self):
        self.assertEqual({value for value, _ in CEILING_STATUS_CHOICES},
                         CEILING_STATUS_VALUES)
        self.assertEqual(len(CEILING_STATUS_CHOICES), len(CEILING_STATUS_VALUES))


class TheKeysClaimIsHeldByTheDatabaseTest(TestCase):
    """`UNIQUE(tenant, customer, idempotency_key)`, asserted at the database.

    ⚠ NOT THROUGH THE START GATE, WHICH IS THE POINT. That gate reads the
    claim first and answers a repeat itself, so a route-level test proves what
    the handler decided to do rather than what a second writer is ALLOWED to
    do — and the constraint's real job is the case no handler sees: two
    identical starts racing, both finding nothing, both inserting. These write
    through the ORM for exactly that reason.

    Every case runs its INSERT inside its own `atomic` block, because a failed
    statement poisons the surrounding transaction and the next write in the
    same test would fail for a reason that is not its own.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Claims", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1")

    def _unit(self, customer=None, tenant=None, **fields):
        return Task.objects.create(
            tenant=tenant or self.tenant, customer=customer or self.customer,
            balance_snapshot_micros=0, **fields)

    def test_a_second_use_of_one_key_is_refused_within_a_tenant_and_customer(self):
        self._unit(idempotency_key="nightly-batch")
        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                self._unit(idempotency_key="nightly-batch")
        self.assertIn("uq_task_idempotency_key", str(refusal.exception))

    def test_the_same_key_is_permitted_for_a_different_customer(self):
        """THE SCOPE IS THE POSTING'S OWN, ON THE SAME ARGUMENT: both are a
        caller reporting that something happened FOR A NAMED CUSTOMER, and two
        of a tenant's customers may each run a `nightly-batch`."""
        second = Customer.objects.create(
            tenant=self.tenant, external_id="cust-2")
        self._unit(idempotency_key="nightly-batch")
        self._unit(customer=second, idempotency_key="nightly-batch")
        self.assertEqual(
            Task.objects.filter(idempotency_key="nightly-batch").count(), 2)

    def test_the_same_key_is_permitted_for_a_different_tenant(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        theirs = Customer.objects.create(tenant=other, external_id="cust-1")
        self._unit(idempotency_key="nightly-batch")
        self._unit(tenant=other, customer=theirs,
                   idempotency_key="nightly-batch")
        self.assertEqual(
            Task.objects.filter(idempotency_key="nightly-batch").count(), 2)

    def test_the_rule_is_partial_so_unclaimed_work_never_collides(self):
        """Every unit of work registered before the key existed holds NULL,
        and NULL is outside the rule rather than a value inside it. Were the
        column to hold "" instead, each such row would collide with every
        other and the migration could not have been a pure addition.
        """
        self._unit()
        self._unit()
        self.assertEqual(
            Task.objects.filter(idempotency_key__isnull=True).count(), 2)
