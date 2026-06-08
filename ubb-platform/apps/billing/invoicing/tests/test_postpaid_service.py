import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.invoicing.models import PostpaidUsageConfig
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


@pytest.mark.django_db
class TestAggregate:
    def _events(self, t, c):
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=600_000, billed_cost_micros=800_000, product_id="chat")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r2", idempotency_key="i2",
            provider_cost_micros=100_000, billed_cost_micros=200_000, product_id="")  # no product

    def test_single_line_default(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        self._events(t, c)
        total, lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert total == 1_000_000
        assert lines == [("", 1_000_000)]

    def test_group_by_product_with_other_bucket(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="product_id")
        self._events(t, c)
        total, lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert total == 1_000_000
        assert sum(a for _, a in lines) == total                 # invariant: lines sum to total
        labels = dict(lines)
        assert labels["chat"] == 800_000 and labels["(other)"] == 200_000

    def test_group_by_tag_with_other_bucket(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="tag:seat")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=1, billed_cost_micros=500_000, tags={"seat": "alice"})
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r2", idempotency_key="i2",
            provider_cost_micros=1, billed_cost_micros=300_000, tags=None)  # no tag
        total, lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert total == 800_000 and sum(a for _, a in lines) == 800_000
        assert dict(lines)["alice"] == 500_000 and dict(lines)["(other)"] == 300_000


@pytest.mark.django_db
class TestPush:
    def _setup(self, with_sub=False):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="postpaid", stripe_connected_account_id="acct_x")
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=600_000, billed_cost_micros=1_000_000)
        if with_sub:
            from apps.subscriptions.models import StripeSubscription
            from django.utils import timezone
            now = timezone.now()
            StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="sub_1",
                stripe_product_name="Pro", status="active", amount_micros=1, currency="usd",
                interval="month", current_period_start=now, current_period_end=now, last_synced_at=now)
        return t, c

    def test_push_pending_items_when_subscription_active(self):
        from unittest.mock import patch, MagicMock
        t, c = self._setup(with_sub=True)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="ii_1")
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.total_billed_micros == 1_000_000
        assert rec.stripe_invoice_id == ""  # rode the subscription invoice — no standalone
        assert rec.line_items.count() == 1
        keys = [ck.kwargs.get("idempotency_key", "") for ck in mock_sc.call_args_list]
        assert any(k.startswith(f"usage-item-{rec.id}") for k in keys)
        assert not any(k.startswith(f"usage-invoice-{rec.id}") for k in keys)

    def test_push_standalone_invoice_when_no_subscription(self):
        from unittest.mock import patch, MagicMock
        t, c = self._setup(with_sub=False)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="obj_1")
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.stripe_invoice_id == "obj_1"
        keys = [ck.kwargs.get("idempotency_key", "") for ck in mock_sc.call_args_list]
        assert any(k.startswith(f"usage-invoice-{rec.id}") for k in keys)
        assert any(k.startswith(f"usage-finalize-{rec.id}") for k in keys)

    def test_idempotent_rerun_no_new_records(self):
        from unittest.mock import patch, MagicMock
        from apps.billing.invoicing.models import UsageInvoiceLineItem
        t, c = self._setup(with_sub=True)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="ii_1")
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
            n = mock_sc.call_count
            PostpaidUsageService.push_customer_period(t, c, PS, PE)  # re-run
        assert mock_sc.call_count == n  # no new Stripe calls on an already-pushed period
        assert UsageInvoiceLineItem.objects.count() == 1

    def test_skipped_when_no_stripe_customer(self):
        from unittest.mock import patch
        t, c = self._setup(with_sub=False)
        c.stripe_customer_id = ""
        c.save(update_fields=["stripe_customer_id"])
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc:
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        assert rec.status == "skipped" and rec.skip_reason == "no_stripe_customer"
        mock_sc.assert_not_called()
