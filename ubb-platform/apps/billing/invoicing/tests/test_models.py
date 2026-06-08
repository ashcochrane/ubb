import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestPostpaidModels:
    def test_create_usage_invoice_and_line_items(self):
        from apps.billing.invoicing.models import (
            CustomerUsageInvoice, UsageInvoiceLineItem, PostpaidUsageConfig)
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        inv = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=datetime.date(2026, 6, 1),
            period_end=datetime.date(2026, 7, 1), total_billed_micros=1_000_000, currency="usd")
        assert inv.status == "pending"
        UsageInvoiceLineItem.objects.create(usage_invoice=inv, dimension="", amount_micros=1_000_000)
        assert inv.line_items.count() == 1
        cfg = PostpaidUsageConfig.objects.create(tenant=t)
        assert cfg.usage_line_item_group_by == ""
