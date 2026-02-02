from datetime import date
from django.test import TestCase
from django.db import IntegrityError, transaction
from apps.tenants.models import Tenant
from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice


class TenantBillingPeriodTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=1.00,
        )

    def test_create_billing_period(self):
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
        )
        self.assertEqual(period.status, "open")
        self.assertEqual(period.total_usage_cost_micros, 0)
        self.assertEqual(period.event_count, 0)
        self.assertEqual(period.platform_fee_micros, 0)

    def test_only_one_open_period_per_tenant(self):
        """Partial unique index ensures only one open period per tenant."""
        TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
        )
        # Different date range, same tenant, still open — should fail
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TenantBillingPeriod.objects.create(
                    tenant=self.tenant,
                    period_start=date(2026, 2, 1),
                    period_end=date(2026, 3, 1),
                )

    def test_closed_period_allows_new_open(self):
        """After closing a period, a new open period can be created."""
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
        )
        period.status = "closed"
        period.save(update_fields=["status"])

        # New open period should succeed
        new_period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 3, 1),
        )
        self.assertEqual(new_period.status, "open")


class TenantInvoiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_usage_cost_micros=50_000_000_000,
            platform_fee_micros=500_000_000,
        )

    def test_create_tenant_invoice(self):
        invoice = TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=self.period,
            total_amount_micros=500_000_000,
        )
        self.assertEqual(invoice.status, "draft")

    def test_one_invoice_per_period(self):
        TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=self.period,
            total_amount_micros=500_000_000,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TenantInvoice.objects.create(
                    tenant=self.tenant,
                    billing_period=self.period,
                    total_amount_micros=500_000_000,
                )
