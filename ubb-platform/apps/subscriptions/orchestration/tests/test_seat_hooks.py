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
from apps.platform.tenants.models import Tenant
from apps.subscriptions.models import (
    CustomerSubscriptionItem,
    StripeSubscription,
    TenantBillingPlan,
)
from apps.subscriptions.orchestration.seats import seat_count


def _business_with_sub(seats=2, status="active"):
    t = Tenant.objects.create(name="T", products=["metering", "billing"],
                              stripe_connected_account_id="acct_x", charges_enabled=True)
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="pooled", stripe_customer_id="cus_biz")
    plan = TenantBillingPlan.objects.create(tenant=t, key="pro", name="Pro",
                                            per_seat_micros=8_000_000)
    now = timezone.now()
    sub = StripeSubscription.objects.create(tenant=t, customer=biz, stripe_subscription_id="sub_1",
        stripe_product_name="Pro", status=status, amount_micros=1, currency="usd",
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

    def test_suspend_seat_via_webhook_pushes_decremented_count(self):
        from apps.billing.connectors.stripe.webhooks import handle_invoice_payment_failed
        t, biz, _plan, seats = _business_with_sub(seats=3)
        seat = seats[0]
        seat.stripe_customer_id = "cus_seat0"
        seat.save(update_fields=["stripe_customer_id"])

        class _Obj:
            def __init__(self, **kw): self.__dict__.update(kw)
        event = _Obj(account="acct_x", data=_Obj(object=_Obj(customer="cus_seat0")))
        with patch("apps.subscriptions.orchestration.service.SubscriptionOrchestrator.set_seats") as spy, \
             self.captureOnCommitCallbacks(execute=True):
            handle_invoice_payment_failed(event)
        seat.refresh_from_db()
        assert seat.status == "suspended"
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
