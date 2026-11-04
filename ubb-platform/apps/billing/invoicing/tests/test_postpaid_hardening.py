"""Hardening tests for postpaid usage push (C1 standalone-always, C2 floor+residual)."""
import datetime
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService
from apps.subscriptions.tests._helpers import a_mirrored_subscription

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
PS2, PE2 = datetime.date(2026, 7, 1), datetime.date(2026, 8, 1)


def _charge_ready_tenant():
    return Tenant.objects.create(
        name="T", products=["metering", "billing"], billing_mode="postpaid",
        stripe_connected_account_id="acct_x", charges_enabled=True)


def _postpaid_customer(t, external_id="c1"):
    return Customer.objects.create(tenant=t, external_id=external_id, stripe_customer_id="cus_1")


def _stripe_mocks(invoice_id="inv_1"):
    """Patch the raw Stripe SDK calls used inside _push_to_stripe.

    InvoiceItem.create returns objects with sequential ids; Invoice.create returns
    a fixed invoice id; finalize_invoice echoes it back; Invoice.list (the F0.1
    pre-create lookup) finds nothing (MagicMock auto_paging_iter is empty).
    """
    item_counter = {"n": 0}

    def item_create(*a, **k):
        item_counter["n"] += 1
        return MagicMock(id=f"ii_{item_counter['n']}")

    return (
        patch("apps.billing.invoicing.services.postpaid_service.stripe.InvoiceItem.create",
              side_effect=item_create),
        patch("apps.billing.invoicing.services.postpaid_service.stripe.Invoice.create",
              return_value=MagicMock(id=invoice_id)),
        patch("apps.billing.invoicing.services.postpaid_service.stripe.Invoice.finalize_invoice",
              return_value=MagicMock(id=invoice_id)),
        patch("apps.platform.events.tasks.process_single_event"),
        patch("apps.billing.invoicing.services.postpaid_service.stripe.Invoice.list",
              return_value=MagicMock()),
    )


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestStandaloneAlways:
    def test_usage_always_standalone_even_with_subscription(self):
        """C1: even with an active subscription, usage is billed on its OWN standalone
        invoice — no item is pinned with subscription=<sub_id>."""
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)
        now = timezone.now()
        a_mirrored_subscription(
            tenant=t, customer=c, stripe_subscription_id="sub_1", stripe_product_name="Pro",
            status="active", amount_micros=10_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now)

        item_p, inv_p, fin_p, ev_p, list_p = _stripe_mocks(invoice_id="inv_1")
        with item_p as m_item, inv_p as m_inv, fin_p as m_fin, ev_p, list_p, \
             patch.object(PostpaidUsageService, "aggregate_lines",
                          return_value=(500_000, [("", 500_000)])):
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)

        rec.refresh_from_db()
        # No InvoiceItem.create call carried a subscription kwarg.
        assert m_item.call_count >= 1
        for call in m_item.call_args_list:
            assert "subscription" not in call.kwargs
        # Standalone invoice path was used.
        assert m_inv.call_count == 1
        assert m_fin.call_count == 1
        assert rec.status == "pushed"
        assert rec.stripe_invoice_id == "inv_1"


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestItemsPinnedToDraft:
    def test_usage_items_pinned_to_the_draft_invoice(self):
        """B1: every usage InvoiceItem is PINNED to the draft invoice (invoice=<id>),
        so the items actually sweep onto the finalized invoice instead of floating as
        unpinned pending items (which default to 'exclude' -> an empty, unbilled invoice).
        """
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)

        item_p, inv_p, fin_p, ev_p, list_p = _stripe_mocks(invoice_id="in_1")
        with item_p as m_item, inv_p as m_inv, fin_p as m_fin, ev_p, list_p, \
             patch.object(PostpaidUsageService, "aggregate_lines",
                          return_value=(500_000, [("", 500_000)])):
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)

        rec.refresh_from_db()
        # 1. The draft invoice was created.
        assert m_inv.call_count == 1
        # 2. EVERY InvoiceItem.create pinned the item to the draft invoice.
        assert m_item.call_count >= 1
        for call in m_item.call_args_list:
            assert call.kwargs.get("invoice") == "in_1"
        # 3. finalize targeted that same invoice id.
        assert m_fin.call_count == 1
        assert m_fin.call_args_list[0].kwargs["invoice"] == "in_1"
        # 4. The record reflects the finalized invoice.
        assert rec.stripe_invoice_id == "in_1"
        assert rec.status == "pushed"

    def test_subcent_only_creates_no_empty_invoice(self):
        """B1 guard: a sub-cent-only period bills nothing, so we must NOT create an
        empty Stripe invoice — carry the residual and record the period as
        SKIPPED below one minor unit (R10 Stage C3, F-9, RULED Q5). It was
        recorded `pushed` with no invoice identity until C3: `pushed` always
        means a real Stripe invoice now."""
        from apps.billing.invoicing.models import PostpaidResidualLedger
        from apps.platform.events.models import OutboxEvent
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)

        item_p, inv_p, fin_p, ev_p, list_p = _stripe_mocks(invoice_id="in_1")
        with item_p as m_item, inv_p as m_inv, fin_p as m_fin, ev_p, list_p, \
             patch.object(PostpaidUsageService, "aggregate_lines",
                          return_value=(5_000, [("", 5_000)])):
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)

        rec.refresh_from_db()
        assert m_inv.call_count == 0   # no empty invoice
        assert m_item.call_count == 0
        assert m_fin.call_count == 0
        assert rec.status == "skipped"
        assert rec.skip_reason == "below_minor_unit"
        assert rec.stripe_invoice_id == "" and rec.pushed_at is None
        assert rec.residual_micros == 5_000
        assert PostpaidResidualLedger.objects.get(customer=c).balance_micros == 5_000
        assert not OutboxEvent.objects.filter(event_type="usage_invoice.pushed").exists()

    def test_stage_b_step_7_d8_a_sub_cent_period_is_skipped_and_its_month_closed(self):
        """Stage B step 7 (d8), end to end from a recorded posting: half a cent
        of usage in the month is carried, the period is `skipped` /
        `below_minor_unit` with no Stripe invoice and no `usage_invoice.pushed`,
        and the month is closed to backfill — its usage is in the carry."""
        from apps.billing.invoicing.models import CustomerUsageInvoice, PostpaidResidualLedger
        from apps.billing.queries import is_usage_period_closed
        from apps.metering.usage.tests._helpers import a_posting
        from apps.platform.events.models import OutboxEvent
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)
        a_posting(tenant=t, customer=c, billing_owner_id=c.id, idempotency_key="d8",
                  provider_cost_micros=1, billed_cost_micros=5_000,
                  effective_at=timezone.make_aware(timezone.datetime(2026, 6, 15)))

        item_p, inv_p, fin_p, ev_p, list_p = _stripe_mocks(invoice_id="in_localpass_d8")
        with item_p as m_item, inv_p as m_inv, fin_p, ev_p, list_p as m_list:
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)

        rec.refresh_from_db()
        assert (rec.status, rec.skip_reason) == ("skipped", "below_minor_unit")
        assert rec.total_billed_micros == 5_000 and rec.residual_micros == 5_000
        assert rec.stripe_invoice_id == ""
        assert m_inv.call_count == 0 and m_item.call_count == 0 and m_list.call_count == 0
        assert PostpaidResidualLedger.objects.get(customer=c).balance_micros == 5_000
        assert not OutboxEvent.objects.filter(event_type="usage_invoice.pushed").exists()
        assert not CustomerUsageInvoice.objects.filter(
            status="pushed", stripe_invoice_id="").exists()
        assert is_usage_period_closed(c.id, PS) is True


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestSubcentResidual:
    def test_subcent_floors_and_carries_residual(self):
        """C2: a sub-cent line floors to whole cents (no crash) and carries the residual."""
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)

        item_p, inv_p, fin_p, ev_p, list_p = _stripe_mocks(invoice_id="inv_1")
        with item_p as m_item, inv_p, fin_p, ev_p, list_p, \
             patch.object(PostpaidUsageService, "aggregate_lines",
                          return_value=(1_234_567, [("", 1_234_567)])):
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)

        rec.refresh_from_db()
        assert m_item.call_count == 1
        assert m_item.call_args_list[0].kwargs["amount"] == 123  # floor(1_234_567 / 10_000)
        assert rec.residual_micros == 4_567
        assert rec.status == "pushed"

    def test_residual_carries_into_next_period(self):
        """The residual left by one period folds into the next period's push."""
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)

        # Period 1: leaves residual 4_567.
        item_p, inv_p, fin_p, ev_p, list_p = _stripe_mocks(invoice_id="inv_1")
        with item_p, inv_p, fin_p, ev_p, list_p, \
             patch.object(PostpaidUsageService, "aggregate_lines",
                          return_value=(1_234_567, [("", 1_234_567)])):
            rec1 = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec1.refresh_from_db()
        assert rec1.residual_micros == 4_567

        # Period 2: 8_000 + 4_567 carry = 12_567 -> 1 cent, residual 2_567.
        item_p2, inv_p2, fin_p2, ev_p2, list_p2 = _stripe_mocks(invoice_id="inv_2")
        with item_p2 as m_item2, inv_p2, fin_p2, ev_p2, list_p2, \
             patch.object(PostpaidUsageService, "aggregate_lines",
                          return_value=(8_000, [("", 8_000)])):
            rec2 = PostpaidUsageService.push_customer_period(t, c, PS2, PE2)
        rec2.refresh_from_db()
        assert m_item2.call_count == 1
        assert m_item2.call_args_list[0].kwargs["amount"] == 1
        assert rec2.residual_micros == 2_567
        assert rec2.status == "pushed"
