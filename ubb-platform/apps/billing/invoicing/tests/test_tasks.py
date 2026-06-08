import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
class TestPostpaidClose:
    def test_close_pushes_postpaid_customer(self):
        from apps.billing.invoicing.tasks import close_postpaid_usage_periods, _prior_month
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t = Tenant.objects.create(name="PP", products=["metering", "billing"],
                                  billing_mode="postpaid", stripe_connected_account_id="acct_x")
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        start, end = _prior_month()
        ev = UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=500_000, billed_cost_micros=1_000_000)
        # auto_now_add can't be set on create — force effective_at into the prior month:
        UsageEvent.objects.filter(id=ev.id).update(
            effective_at=timezone.make_aware(timezone.datetime(start.year, start.month, 15)))
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="ii_1")
            close_postpaid_usage_periods()
        rec = CustomerUsageInvoice.objects.get(tenant=t, customer=c, period_start=start)
        assert rec.status == "pushed" and rec.total_billed_micros == 1_000_000

    def test_close_ignores_non_postpaid(self):
        from apps.billing.invoicing.tasks import close_postpaid_usage_periods, _prior_month
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t = Tenant.objects.create(name="PRE", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        start, _ = _prior_month()
        ev = UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=1, billed_cost_micros=1_000_000)
        UsageEvent.objects.filter(id=ev.id).update(
            effective_at=timezone.make_aware(timezone.datetime(start.year, start.month, 15)))
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call"):
            close_postpaid_usage_periods()
        assert not CustomerUsageInvoice.objects.filter(tenant=t).exists()  # prepaid is not invoiced
