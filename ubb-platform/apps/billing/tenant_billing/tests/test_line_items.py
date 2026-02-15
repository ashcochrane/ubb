import pytest
from datetime import date

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice, TenantInvoiceLineItem


@pytest.mark.django_db
class TestTenantInvoiceLineItem:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
        )
        self.invoice = TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=self.period,
            total_amount_micros=500_000_000,
        )

    def test_create_line_item(self):
        item = TenantInvoiceLineItem.objects.create(
            invoice=self.invoice,
            product="billing",
            description="Usage throughput fee (1.00%)",
            amount_micros=500_000_000,
        )
        assert item.product == "billing"

    def test_multiple_line_items_per_invoice(self):
        TenantInvoiceLineItem.objects.create(
            invoice=self.invoice,
            product="billing",
            description="Usage throughput fee (1.00%)",
            amount_micros=400_000_000,
        )
        TenantInvoiceLineItem.objects.create(
            invoice=self.invoice,
            product="referrals",
            description="Referral payout fee (5.00%)",
            amount_micros=100_000_000,
        )
        assert self.invoice.line_items.count() == 2
