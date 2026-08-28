from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task


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
            provider_cost_limit_micros=10_000_000,
        )
        self.assertEqual(task.provider_cost_limit_micros, 10_000_000)
        self.assertEqual(task.balance_snapshot_micros, 5_000_000)

    def test_task_without_limits(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
        )
        self.assertIsNone(task.provider_cost_limit_micros)

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
