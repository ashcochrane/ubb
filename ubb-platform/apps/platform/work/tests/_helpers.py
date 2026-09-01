"""Shared setup for the work app's service-level tests
(`docs/conventions/testing.md`).

`WorkTestBase` was `test_subtasks.SubtaskTestBase` until a second module needed
the same three things — a tenant, a customer, and a factory for pieces of work
that can nest. It is here rather than there because a fixture two test modules
share belongs in one place, and because copying ten lines of setup is how two
modules come to stand their work up slightly differently.
"""
from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant
from apps.platform.work.services import TaskService


class WorkTestBase(TestCase):
    """A tenant with both products, one customer, and work on demand."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Subtasks", products=["metering", "billing"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1")

    def _task(self, limit=None, balance=100_000_000, parent=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit,
            billing_owner_id=self.customer.id, parent=parent)

    def _a_parent_and_its_contained_work(self, **kwargs):
        """The pair almost every containment case needs: a top-level unit and
        one piece of work running inside it."""
        parent = self._task(**kwargs)
        return parent, self._task(parent=parent)

    def _events(self, event_type):
        return OutboxEvent.objects.filter(event_type=event_type)
