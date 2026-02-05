from datetime import date
from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.tenant_billing.tasks import generate_tenant_platform_invoices


class PlatformInvoiceStripeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test",
            stripe_connected_account_id="acct_test",
            stripe_customer_id="cus_tenant_test",  # Tenant as UBB's customer
            platform_fee_percentage=1.00,
        )
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_usage_cost_micros=100_000_000_000,
            event_count=5000,
            platform_fee_micros=1_000_000_000,
        )

    @patch("apps.billing.stripe.services.stripe_service.stripe_call")
    def test_creates_stripe_invoice_for_platform_fee(self, mock_stripe_call):
        mock_invoice = MagicMock()
        mock_invoice.id = "inv_platform_test"
        mock_stripe_call.return_value = mock_invoice

        generate_tenant_platform_invoices()

        invoice = TenantInvoice.objects.get(billing_period=self.period)
        self.assertEqual(invoice.total_amount_micros, 1_000_000_000)
        self.assertEqual(invoice.status, "finalized")

        # Verify Stripe was called with tenant's customer ID, not connected account
        create_call = mock_stripe_call.call_args_list[0]
        self.assertNotIn("stripe_account", create_call.kwargs)

    @patch("apps.billing.stripe.services.stripe_service.stripe_call")
    def test_stripe_failure_keeps_period_closed_for_retry(self, mock_stripe_call):
        """On Stripe failure, period stays closed so next run retries."""
        mock_stripe_call.side_effect = Exception("Stripe down")

        generate_tenant_platform_invoices()

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "closed")  # NOT "invoiced"
        self.assertFalse(TenantInvoice.objects.filter(billing_period=self.period).exists())

    def test_zero_fee_period_auto_invoiced(self):
        self.period.platform_fee_micros = 0
        self.period.save()

        generate_tenant_platform_invoices()

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "invoiced")
        self.assertFalse(TenantInvoice.objects.filter(billing_period=self.period).exists())
