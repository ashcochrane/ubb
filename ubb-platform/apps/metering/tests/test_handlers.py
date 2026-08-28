from dataclasses import asdict

from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.schemas import RefundRequested
from apps.metering.usage.models import Posting, Refund
from apps.metering.handlers import handle_refund_requested


class HandleRefundRequestedTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.event = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1", billed_cost_micros=1_000_000,
        )

    def test_creates_refund_record(self):
        handle_refund_requested("evt_1", asdict(RefundRequested(
            tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            usage_event_id=self.event.id,
            refund_amount_micros=1_000_000,
            reason="mistake",
        )))
        refund = Refund.objects.get(posting=self.event)
        self.assertEqual(refund.amount_micros, 1_000_000)
        self.assertEqual(refund.reason, "mistake")
        self.assertEqual(refund.tenant_id, self.tenant.id)
        self.assertEqual(refund.customer_id, self.customer.id)

    def test_idempotent_on_duplicate(self):
        """Second call for same posting is silently ignored."""
        handle_refund_requested("evt_1", asdict(RefundRequested(
            tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            usage_event_id=self.event.id,
            refund_amount_micros=1_000_000,
        )))
        # Second call — should not raise
        handle_refund_requested("evt_2", asdict(RefundRequested(
            tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            usage_event_id=self.event.id,
            refund_amount_micros=1_000_000,
        )))
        self.assertEqual(Refund.objects.filter(posting=self.event).count(), 1)

    def test_missing_posting_is_skipped(self):
        import uuid
        handle_refund_requested("evt_1", asdict(RefundRequested(
            tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            usage_event_id=uuid.uuid4(),
            refund_amount_micros=1_000_000,
        )))
        self.assertEqual(Refund.objects.count(), 0)

    def test_default_empty_reason(self):
        handle_refund_requested("evt_1", asdict(RefundRequested(
            tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            usage_event_id=self.event.id,
            refund_amount_micros=500_000,
        )))
        refund = Refund.objects.get(posting=self.event)
        self.assertEqual(refund.reason, "")

    def test_refund_rejects_cross_tenant_posting(self):
        """Refund handler must not allow cross-tenant event access."""
        other_tenant = Tenant.objects.create(name="Other")
        handle_refund_requested("evt_cross", asdict(RefundRequested(
            tenant_id=other_tenant.id,
            customer_id=self.customer.id,
            usage_event_id=self.event.id,
            refund_amount_micros=1_000_000,
        )))
        # Event belongs to self.tenant, not other_tenant — should be skipped
        self.assertEqual(Refund.objects.count(), 0)
