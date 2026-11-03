"""(d) Seat roster change -> SubscriptionOrchestrator.set_seats(new active count).

Uses transaction=True so the on_commit push actually fires, and spies on
set_seats (the real Stripe call is behind it; stripe is mocked elsewhere).
"""
import uuid
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.subscriptions.models import CustomerSubscriptionItem
from apps.subscriptions.orchestration.seats import seat_count
from apps.subscriptions.tests._helpers import a_mirrored_subscription


def _business_with_sub(seats=2, status="active"):
    t = Tenant.objects.create(name="T", products=["metering", "billing"],
                              stripe_connected_account_id="acct_x", charges_enabled=True)
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="pooled", stripe_customer_id="cus_biz")
    plan = a_plan(tenant=t, key="pro", name="Pro",
                  per_seat_micros=8_000_000)
    now = timezone.now()
    sub = a_mirrored_subscription(tenant=t, customer=biz, stripe_subscription_id="sub_1",
        stripe_product_name="Pro", status=status, amount_micros=10_000, currency="usd",
        interval="month", quantity=seats, current_period_start=now, current_period_end=now,
        last_synced_at=now)
    CustomerSubscriptionItem.objects.create(tenant=t, customer=biz, stripe_subscription=sub,
        stripe_subscription_item_id="si_s", axis="seat", stripe_price_id="price_s",
        quantity=seats, plan=plan)
    existing = []
    for i in range(seats):
        existing.append(Customer.objects.create(tenant=t, external_id=f"seat{i}",
                        account_type="seat", parent=biz))
    return t, biz, plan, existing


class TestSeatCountHelper(TestCase):
    def test_counts_only_live_active_seats(self):
        t, biz, _plan, seats = _business_with_sub(seats=3)
        assert seat_count(biz) == 3
        seats[0].status = "suspended"
        seats[0].save(update_fields=["status"])
        assert seat_count(biz) == 2          # suspended drops out
        seats[1].soft_delete()
        assert seat_count(biz) == 1          # soft-deleted drops out


class TestSeatCreateHook(TestCase):
    def test_create_seat_pushes_incremented_count(self):
        from apps.subscriptions.orchestration.seats import sync_seat_quantity_on_commit
        from django.db import transaction
        t, biz, _plan, _seats = _business_with_sub(seats=2)
        with patch("apps.subscriptions.orchestration.service.SubscriptionOrchestrator.set_seats") as spy, \
             self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                Customer.objects.create(tenant=t, external_id="newseat",
                                        account_type="seat", parent=biz)
                sync_seat_quantity_on_commit(biz)
        spy.assert_called_once()
        # new active count = 2 existing + 1 new = 3
        assert spy.call_args.args[2] == 3 or spy.call_args.kwargs.get("new_seats") == 3
        _, kw = spy.call_args
        assert "change_event_id" in kw


class TestSeatRemoveHook(TestCase):
    def test_soft_delete_seat_pushes_decremented_count(self):
        t, biz, _plan, seats = _business_with_sub(seats=3)
        with patch("apps.subscriptions.orchestration.service.SubscriptionOrchestrator.set_seats") as spy, \
             patch("apps.platform.events.tasks.process_single_event"), \
             self.captureOnCommitCallbacks(execute=True):
            seats[0].soft_delete()
        spy.assert_called_once()
        assert spy.call_args.args[2] == 2 or spy.call_args.kwargs.get("new_seats") == 2

    # R10 Stage C2 (F-6, RULED Q4): a payment-failed suspension targets the
    # canonical billing owner of the MATCHED LOCAL invoice, never whichever
    # customer carries the Stripe customer id, and an unmatched Stripe invoice
    # suspends nobody. The pin this replaces drove the handler with an invoice
    # that matched no local row and expected the seat suspended — the defect.

    class _Obj:
        def __init__(self, **kw): self.__dict__.update(kw)

    def _payment_failed(self, **inv):
        from apps.billing.connectors.stripe.webhooks import handle_invoice_payment_failed
        fields = {"id": None, "subscription": None, "parent": None,
                  "hosted_invoice_url": "", "invoice_pdf": "", **inv}
        event = self._Obj(account="acct_x", data=self._Obj(object=self._Obj(**fields)))
        with patch("apps.subscriptions.orchestration.service.SubscriptionOrchestrator.set_seats") as spy, \
             self.captureOnCommitCallbacks(execute=True):
            handle_invoice_payment_failed(event)
        return spy

    def test_an_unmatched_payment_failure_suspends_nobody_and_pushes_nothing(self):
        t, biz, _plan, seats = _business_with_sub(seats=3)
        seat = seats[0]
        seat.stripe_customer_id = "cus_seat0"
        seat.save(update_fields=["stripe_customer_id"])
        spy = self._payment_failed(id="in_nobody_holds_this", customer="cus_seat0")
        seat.refresh_from_db()
        biz.refresh_from_db()
        assert (seat.status, biz.status) == ("active", "active")
        spy.assert_not_called()

    def test_a_failed_subscription_invoice_suspends_the_business_and_leaves_the_roster(self):
        from apps.platform.work import reasons
        from apps.subscriptions.models import SubscriptionInvoice
        t, biz, _plan, seats = _business_with_sub(seats=3)
        sub = biz.stripe_subscriptions.get(stripe_subscription_id="sub_1")
        SubscriptionInvoice.objects.create(
            tenant=t, customer=biz, billing_owner=biz, stripe_subscription=sub, stripe_invoice_id="in_biz_1",
            amount_paid_micros=0, currency="usd", status="open")
        spy = self._payment_failed(id="in_biz_1", subscription="sub_1", customer="cus_biz")
        biz.refresh_from_db()
        assert (biz.status, biz.suspension_reason) == ("suspended", reasons.PAYMENT_FAILED)
        for seat in seats:
            seat.refresh_from_db()
            assert seat.status == "active"
        # The roster did not change — the owner's standing did — so nothing
        # is pushed to the seat quantity.
        assert seat_count(biz) == 3
        spy.assert_not_called()

    def test_a_failed_invoice_owned_by_an_allocated_seat_suspends_it_and_pushes_decremented_count(self):
        import datetime
        from apps.billing.invoicing.models import CustomerUsageInvoice
        from apps.platform.work import reasons
        t, biz, _plan, seats = _business_with_sub(seats=3)
        # An ALLOCATED topology: each seat is its own billing owner, so a
        # seat's own usage invoice names the seat.
        biz.billing_topology = "allocated"
        biz.save(update_fields=["billing_topology"])
        seat = seats[0]
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=seat, period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1), total_billed_micros=1_000_000,
            status="pushed", stripe_invoice_id="in_seat0_usage")
        spy = self._payment_failed(id="in_seat0_usage", customer="cus_seat0")
        seat.refresh_from_db()
        biz.refresh_from_db()
        assert (seat.status, seat.suspension_reason) == ("suspended", reasons.PAYMENT_FAILED)
        assert biz.status == "active"
        spy.assert_called_once()
        assert spy.call_args.args[2] == 2 or spy.call_args.kwargs.get("new_seats") == 2


class TestNoSubscriptionNoop(TestCase):
    def test_create_seat_without_subscription_is_noop(self):
        from apps.subscriptions.orchestration.seats import sync_seat_quantity_on_commit
        from django.db import transaction
        t = Tenant.objects.create(name="T2", products=["metering", "billing"])
        biz = Customer.objects.create(tenant=t, external_id="biz2", account_type="business",
                                      billing_topology="pooled")
        with patch("apps.subscriptions.orchestration.service.SubscriptionOrchestrator.set_seats") as spy, \
             self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                Customer.objects.create(tenant=t, external_id="seatx",
                                        account_type="seat", parent=biz)
                sync_seat_quantity_on_commit(biz)
        spy.assert_not_called()
