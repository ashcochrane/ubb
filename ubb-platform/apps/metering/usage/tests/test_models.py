from django.db import IntegrityError
from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import UsageEvent


class UsageEventModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="user_1",
        )

    def test_create_event(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_abc123",
            idempotency_key="idem_abc123",
            cost_micros=500_000,
        )
        self.assertEqual(event.cost_micros, 500_000)
        self.assertEqual(event.request_id, "req_abc123")
        self.assertIsNotNone(event.effective_at)

    def test_event_immutability_save(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_abc123",
            idempotency_key="idem_abc123",
            cost_micros=500_000,
        )
        event.cost_micros = 999_999
        with self.assertRaises(ValueError):
            event.save()

    def test_event_immutability_delete(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_abc123",
            idempotency_key="idem_abc123",
            cost_micros=500_000,
        )
        with self.assertRaises(ValueError):
            event.delete()

    def test_idempotency_constraint(self):
        UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_abc123",
            idempotency_key="idem_duplicate",
            cost_micros=500_000,
        )
        with self.assertRaises(IntegrityError):
            UsageEvent.objects.create(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_def456",
                idempotency_key="idem_duplicate",
                cost_micros=300_000,
            )
