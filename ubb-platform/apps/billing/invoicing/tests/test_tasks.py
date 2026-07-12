import datetime

import pytest
import stripe
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
                                  billing_mode="postpaid", stripe_connected_account_id="acct_x",
                                  charges_enabled=True)
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


def _seq_ids():
    n = {"i": 0}
    def f(*a, **k):
        n["i"] += 1
        return MagicMock(id=f"obj_{n['i']}")
    return f


@pytest.mark.django_db
class TestPostpaidReconcile:
    PS = datetime.date(2026, 6, 1)
    PE = datetime.date(2026, 7, 1)

    def _tenant_customer(self):
        t = Tenant.objects.create(name="PP", products=["metering", "billing"],
                                  billing_mode="postpaid", stripe_connected_account_id="acct_x",
                                  charges_enabled=True)
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        return t, c

    def test_stale_pushing_row_is_reclaimed_and_repushed_with_same_rec_id_keys(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t, c = self._tenant_customer()
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=1, billed_cost_micros=1_000_000)
        rec = CustomerUsageInvoice.objects.create(tenant=t, customer=c, period_start=self.PS,
            period_end=self.PE, status="pushing", total_billed_micros=1_000_000)
        stale = timezone.now() - datetime.timedelta(minutes=45)
        CustomerUsageInvoice.objects.filter(id=rec.id).update(updated_at=stale)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call",
                   side_effect=_seq_ids()) as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "pushed"
        assert rec.line_items.count() == 1
        # Read-deny-list: only these callables may go keyless; ANY other Stripe
        # call is a WRITE and a missing idempotency_key must fail this test.
        read_fns = {stripe.Invoice.list, stripe.Invoice.retrieve, stripe.InvoiceItem.list}
        writes = [ck for ck in mock_sc.call_args_list if ck.args[0] not in read_fns]
        assert writes
        assert all(str(rec.id) in ck.kwargs.get("idempotency_key", "") for ck in writes)
        keys = [ck.kwargs["idempotency_key"] for ck in writes]
        assert any(k == f"usage-invoice-{rec.id}" for k in keys)  # gen-0 legacy shape
        assert any(k == f"usage-finalize-{rec.id}" for k in keys)

    def test_fresh_pushing_row_is_left_alone(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t, c = self._tenant_customer()
        rec = CustomerUsageInvoice.objects.create(tenant=t, customer=c, period_start=self.PS,
            period_end=self.PE, status="pushing", total_billed_micros=1_000_000)
        fresh = timezone.now() - datetime.timedelta(minutes=5)
        CustomerUsageInvoice.objects.filter(id=rec.id).update(updated_at=fresh)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc:
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "pushing"
        mock_sc.assert_not_called()

    def test_failed_row_is_retried(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t, c = self._tenant_customer()
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=1, billed_cost_micros=1_000_000)
        rec = CustomerUsageInvoice.objects.create(tenant=t, customer=c, period_start=self.PS,
            period_end=self.PE, status="failed", total_billed_micros=0)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call",
                   side_effect=_seq_ids()), \
             patch("apps.platform.events.tasks.process_single_event"):
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "pushed"

    # The old 24h updated_at-based "stuck" bound lived here; it compared an
    # auto_now column every claim refreshed, so it never fired in practice. The
    # retry bound (attempts + wall-clock from first_attempted_at) now lives in
    # PostpaidUsageService.push_customer_period — see test_postpaid_resume_bounds.

    def test_recent_pending_row_is_still_retried(self):
        """A pending row under the attempts/wall-clock cap is retried (not failed)."""
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t, c = self._tenant_customer()
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=1, billed_cost_micros=1_000_000)
        rec = CustomerUsageInvoice.objects.create(tenant=t, customer=c, period_start=self.PS,
            period_end=self.PE, status="pending", total_billed_micros=1_000_000)
        recent = timezone.now() - datetime.timedelta(hours=2)
        CustomerUsageInvoice.objects.filter(id=rec.id).update(updated_at=recent)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call",
                   side_effect=_seq_ids()), \
             patch("apps.platform.events.tasks.process_single_event"):
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "pushed"  # retried, not failed
