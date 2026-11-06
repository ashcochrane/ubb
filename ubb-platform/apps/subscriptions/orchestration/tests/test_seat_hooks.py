"""(d) Seat roster change -> SubscriptionOrchestrator.set_seats(new active count).

Spies on set_seats (the real Stripe call is behind it) or on Stripe's own
``SubscriptionItem.modify``, and runs the on_commit push with
``captureOnCommitCallbacks(execute=True)``.

R10 Stage C4 (A-2, RULED Q8): every roster mutation notifies the roster hook
once inside its transaction, the push never answers a client 500 after the
commit, and the hourly reconciler converges a quantity whose push failed.
"""
import logging
import uuid
from datetime import timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.tests._rails import RailActivated
from apps.subscriptions.models import CustomerSubscriptionItem
from apps.subscriptions.orchestration.seats import seat_count
from apps.subscriptions.tests._helpers import CapturedLog, a_mirrored_subscription

SET_SEATS = "apps.subscriptions.orchestration.service.SubscriptionOrchestrator.set_seats"
MODIFY = "apps.subscriptions.orchestration.service.stripe.SubscriptionItem.modify"
BACKOFF = "apps.billing.stripe.services.stripe_service._backoff"


def _business_with_sub(seats=2, status="active", *, topology="pooled", key="",
                       **tenant_fields):
    t = Tenant.objects.create(name="T", products=["metering", "billing"],
                              stripe_connected_account_id="acct_x", charges_enabled=True,
                              **tenant_fields)
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology=topology, stripe_customer_id="cus_biz")
    plan = a_plan(tenant=t, key="pro", name="Pro",
                  per_seat_micros=8_000_000)
    now = timezone.now()
    sub = a_mirrored_subscription(tenant=t, customer=biz, stripe_subscription_id=f"sub_1{key}",
        stripe_product_name="Pro", status=status, amount_micros=10_000, currency="usd",
        interval="month", quantity=seats, current_period_start=now, current_period_end=now,
        last_synced_at=now)
    CustomerSubscriptionItem.objects.create(tenant=t, customer=biz, stripe_subscription=sub,
        stripe_subscription_item_id=f"si_s{key}", axis="seat", stripe_price_id="price_s",
        quantity=seats, plan=plan)
    existing = []
    for i in range(seats):
        existing.append(Customer.objects.create(tenant=t, external_id=f"seat{i}",
                        account_type="seat", parent=biz))
    return t, biz, plan, existing


def _episode_key(item, count):
    """The Stripe idempotency key the reconciler sends to correct ``item`` to
    ``count`` (``set_seats`` prefixes the change id with ``seat-qty-{item}-``):
    one per divergence episode, the episode being the seat item's last
    successful write (PLAN §7 item 40). Stated here, not imported, so the tests
    pin the ruled shape rather than echo the implementation; the invariant
    itself (one key per episode, a new key on recurrence) is asserted by the
    tests that use it."""
    si = item.stripe_subscription_item_id
    episode = item.updated_at.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"seat-qty-{si}-reconcile-{si}-{episode}-{count}"


class _StripeSeatQuantity:
    """Stripe's ``SubscriptionItem.modify``, as far as idempotency matters
    here. A key Stripe has already answered returns that FIRST answer and
    applies nothing (the cached replay). A new key applies the quantity and
    is cached. ``failing`` makes a new request fail before Stripe acts on it
    (a lost connection), which Stripe does not cache."""

    def __init__(self, quantity):
        self.quantity = quantity
        self.failing = False
        self.cache = {}
        self.requests = []       # (idempotency_key, quantity, what Stripe did)

    def modify(self, **kw):
        import stripe
        key = kw["idempotency_key"]
        if key in self.cache:
            self.requests.append((key, kw["quantity"], "replayed"))
            return self.cache[key]
        if self.failing:
            self.requests.append((key, kw["quantity"], "failed"))
            raise stripe.error.APIConnectionError("Stripe unreachable")
        self.quantity = kw["quantity"]
        self.requests.append((key, kw["quantity"], "applied"))
        self.cache[key] = stripe.SubscriptionItem.construct_from(
            {"id": kw["id"], "object": "subscription_item", "quantity": kw["quantity"]},
            "sk_test_sentinel")
        return self.cache[key]


def _create_seat(tenant, external_id, parent="biz"):
    """A seat created through POST /customers, the one supported Customer
    creation path (PLAN §7 item 32)."""
    from django.test import Client
    from apps.platform.tenants.models import TenantApiKey
    _, raw = TenantApiKey.create_key(tenant)
    return Client().post(
        "/api/v1/platform/customers",
        data={"external_id": external_id, "account_type": "seat",
              "parent_external_id": parent},
        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")


def _seat_log():
    """The seat module's own log lines (logger ``ubb.billing``)."""
    return CapturedLog("ubb.billing")


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
        """A seat created through POST /customers: the endpoint notifies the
        roster hook, and the listener pushes the new live count. Nothing here
        calls the listener by hand (R10 Stage C4)."""
        t, biz, _plan, _seats = _business_with_sub(seats=2)
        with patch(SET_SEATS) as spy, self.captureOnCommitCallbacks(execute=True):
            resp = _create_seat(t, "newseat")
        assert resp.status_code == 201
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

    # R10 Stage C2 (F-6, RULED Q4, PLAN §7 item 27): a payment-failed
    # suspension targets the HISTORICAL billing owner of the MATCHED LOCAL
    # invoice (fixed when the invoice entered UBB), never whichever
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


class TestSeatQuantityConverges(TestCase):
    """THE RULED REGRESSION TEST and its neighbours (A-2, RULED Q8): a push
    that fails after the roster committed converges with no further roster
    change and no operator."""

    def test_a_push_that_failed_after_commit_converges_on_the_next_reconcile(self):
        import stripe
        from apps.subscriptions.models import StripeSubscription
        from apps.subscriptions.tasks import reconcile_subscription_seat_quantities
        t, biz, _plan, _seats = _business_with_sub(seats=2)

        # The local seat count changes; Stripe's first update fails transiently.
        lost = stripe.error.APIConnectionError("Stripe unreachable")
        with patch(MODIFY, side_effect=lost) as first, patch(BACKOFF), \
                self.captureOnCommitCallbacks(execute=True):
            resp = _create_seat(t, "seat-new")
        assert resp.status_code == 201                      # no post-commit 500
        assert seat_count(biz) == 3
        assert first.called and {c.kwargs["quantity"] for c in first.call_args_list} == {3}
        item = CustomerSubscriptionItem.objects.get(stripe_subscription_item_id="si_s")
        assert item.quantity == 2                           # Stripe never took it

        # No further client mutation: the reconciler alone.
        expected_key = _episode_key(item, 3)
        with patch(MODIFY) as modify:
            reconcile_subscription_seat_quantities()
        modify.assert_called_once()
        kw = modify.call_args.kwargs
        assert (kw["id"], kw["quantity"], kw["proration_behavior"]) == (
            "si_s", 3, "create_prorations")
        assert kw["idempotency_key"] == expected_key
        item.refresh_from_db()
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_1")
        assert (item.quantity, mirror.quantity) == (3, 3)

        # A second pass finds nothing to do.
        with patch(MODIFY) as again:
            reconcile_subscription_seat_quantities()
        again.assert_not_called()

    def test_every_pass_that_finds_the_same_difference_replays_one_key(self):
        import stripe
        from apps.subscriptions.tasks import reconcile_subscription_seat_quantities
        t, biz, _plan, _seats = _business_with_sub(seats=2)
        Customer.objects.create(tenant=t, external_id="seat-new", account_type="seat",
                                parent=biz)            # the roster is 3, Stripe holds 2
        item = CustomerSubscriptionItem.objects.get(stripe_subscription_item_id="si_s")
        with patch(MODIFY, side_effect=stripe.error.APIConnectionError("down")) as failing, \
                patch(BACKOFF):
            assert reconcile_subscription_seat_quantities() == {"failed": 1}
            assert reconcile_subscription_seat_quantities() == {"failed": 1}
        with patch(MODIFY) as landing:
            assert reconcile_subscription_seat_quantities() == {"pushed": 1}
        keys = {c.kwargs["idempotency_key"]
                for c in failing.call_args_list + landing.call_args_list}
        # One unresolved mismatch, one episode: every retry replays one key.
        assert keys == {_episode_key(item, 3)}

    def test_a_count_that_recurs_after_another_landed_is_corrected_under_a_new_key(self):
        """N -> M -> N inside one Stripe idempotency window (owner/consultant
        ruling 2026-11-05, PLAN §7 item 40). With the count alone as the key,
        the second correction to N replayed the FIRST N's cached answer:
        Stripe applied nothing and stayed at M, the mirror recorded N, and the
        next pass saw no difference."""
        from apps.subscriptions.models import StripeSubscription
        from apps.subscriptions.tasks import reconcile_subscription_seat_quantities
        t, biz, _plan, _seats = _business_with_sub(seats=2)
        stripe_side = _StripeSeatQuantity(quantity=2)
        item = CustomerSubscriptionItem.objects.get(stripe_subscription_item_id="si_s")

        def mirrored():
            item.refresh_from_db()
            return item.quantity, StripeSubscription.objects.get(
                stripe_subscription_id="sub_1").quantity

        with patch(MODIFY, side_effect=stripe_side.modify), patch(BACKOFF), \
                patch("apps.platform.events.tasks.process_single_event"):
            # N = 3: the immediate push fails; the reconciler applies 3.
            stripe_side.failing = True
            with self.captureOnCommitCallbacks(execute=True):
                assert _create_seat(t, "seat-n").status_code == 201
            stripe_side.failing = False
            assert stripe_side.requests[-1][1:] == (3, "failed")       # the immediate push
            assert reconcile_subscription_seat_quantities() == {"pushed": 1}
            first_correction = stripe_side.requests[-1]
            assert (first_correction[1:], stripe_side.quantity) == ((3, "applied"), 3)

            # M = 4: the immediate push lands.
            with self.captureOnCommitCallbacks(execute=True):
                assert _create_seat(t, "seat-m").status_code == 201
            assert (stripe_side.quantity, mirrored()) == (4, (4, 4)), stripe_side.requests

            # Back to N = 3 inside the same window; the immediate push fails.
            stripe_side.failing = True
            with self.captureOnCommitCallbacks(execute=True):
                Customer.objects.get(tenant=t, external_id="seat-m").soft_delete()
            stripe_side.failing = False
            assert stripe_side.requests[-1][1:] == (3, "failed")       # the immediate push
            assert seat_count(biz) == 3
            assert (stripe_side.quantity, mirrored()) == (4, (4, 4))   # still M everywhere

            # The reconciler corrects it under a NEW key, and Stripe applies it.
            assert reconcile_subscription_seat_quantities() == {"pushed": 1}
            second_correction = stripe_side.requests[-1]
            # Stripe must APPLY the correction (not replay the first N's cached
            # answer), and the mirror records N only with it: (what Stripe did,
            # Stripe's quantity, the mirrored item and subscription).
            assert (second_correction[1:], stripe_side.quantity, mirrored()) == (
                (3, "applied"), 3, (3, 3))
            assert second_correction[0] != first_correction[0]   # a new key

            # A second pass makes no call.
            calls = len(stripe_side.requests)
            assert reconcile_subscription_seat_quantities() == {"in_step": 1}
            assert len(stripe_side.requests) == calls

    def test_a_stripe_refusal_after_commit_is_logged_and_answers_no_500(self):
        import stripe
        for error in (stripe.error.APIConnectionError("down"),
                      stripe.error.InvalidRequestError("No such subscription item", "id")):
            with self.subTest(type(error).__name__):
                t, biz, _plan, _seats = _business_with_sub(seats=2, key=type(error).__name__)
                with _seat_log() as log, patch(MODIFY, side_effect=error), patch(BACKOFF), \
                        self.captureOnCommitCallbacks(execute=True):
                    resp = _create_seat(t, "seat-new")
                assert resp.status_code == 201
                assert "seat.qty_push_failed" in log.messages()
                failed = [r for r in log.records if r.getMessage() == "seat.qty_push_failed"]
                assert failed[0].data["business_id"] == str(biz.id)

    def test_a_closed_rail_is_logged_and_skipped_by_the_reconciler(self):
        from apps.platform.tenants.models import PaymentRailClosed
        from apps.subscriptions.tasks import reconcile_subscription_seat_quantities
        t, biz, _plan, _seats = _business_with_sub(seats=2)
        Customer.objects.create(tenant=t, external_id="seat-new", account_type="seat",
                                parent=biz)
        closed = PaymentRailClosed(tenant_id=t.id, rail="tenant_money", environment="live")
        with _seat_log() as log, patch(MODIFY) as modify, patch(
                "apps.subscriptions.orchestration.service."
                "refuse_a_rail_operation_while_it_is_closed", side_effect=closed):
            assert reconcile_subscription_seat_quantities() == {"rail_closed": 1}
        modify.assert_not_called()
        refused = [r for r in log.records if r.getMessage() == "seat.qty_reconcile_failed"]
        assert [(r.levelno, r.data["reason"]) for r in refused] == [
            (logging.WARNING, "rail_closed")]

    def test_a_failed_read_on_either_side_of_the_commit_never_fails_the_change(self):
        """The listener's own reads: before the commit (in a savepoint, so the
        roster change still commits) and after it (re-resolving the roster).
        A failure in either is logged and left to the reconciler."""
        seats_module = "apps.subscriptions.orchestration.seats"
        resolve = f"{seats_module}._resolve_seat_subscription"
        from apps.subscriptions.orchestration import seats as seats_mod
        real_resolve = seats_mod._resolve_seat_subscription
        calls = []

        def fail_once_after_commit(business):
            calls.append(business.id)
            if len(calls) == 2:              # the post-commit re-read
                raise RuntimeError("read lost after commit")
            return real_resolve(business)

        cases = (("before", {"side_effect": RuntimeError("read lost before commit")}),
                 ("after", {"side_effect": fail_once_after_commit}))
        for key, failure in cases:
            with self.subTest(key):
                calls.clear()
                t, biz, _plan, _seats = _business_with_sub(seats=2, key=key)
                with _seat_log() as log, patch(resolve, **failure), patch(SET_SEATS) as spy, \
                        self.captureOnCommitCallbacks(execute=True):
                    resp = _create_seat(t, "seat-new")
                assert resp.status_code == 201
                assert Customer.objects.filter(tenant=t, external_id="seat-new").exists()
                spy.assert_not_called()
                failed = [r for r in log.records if r.getMessage() == "seat.qty_push_failed"]
                assert [(r.data["business_id"], r.data["reason"]) for r in failed] == [
                    (str(biz.id), "RuntimeError")]

    def test_a_closed_rail_after_commit_is_logged_by_the_listener_and_answers_no_500(self):
        from apps.platform.tenants.models import PaymentRailClosed
        t, biz, _plan, _seats = _business_with_sub(seats=2)
        closed = PaymentRailClosed(tenant_id=t.id, rail="tenant_money", environment="live")
        with _seat_log() as log, patch(MODIFY) as modify, patch(
                "apps.subscriptions.orchestration.service."
                "refuse_a_rail_operation_while_it_is_closed", side_effect=closed), \
                self.captureOnCommitCallbacks(execute=True):
            resp = _create_seat(t, "seat-new")
        assert resp.status_code == 201
        modify.assert_not_called()
        failed = [r for r in log.records if r.getMessage() == "seat.qty_push_failed"]
        assert [(r.data["business_id"], r.data["reason"]) for r in failed] == [
            (str(biz.id), "rail_closed")]

    def test_the_reconciler_reads_only_businesses_with_an_active_seat_subscription(self):
        from apps.subscriptions.tasks import reconcile_subscription_seat_quantities
        t, biz, _plan, _seats = _business_with_sub(seats=2, status="canceled")
        Customer.objects.create(tenant=t, external_id="seat-new", account_type="seat",
                                parent=biz)
        with patch(MODIFY) as modify:
            assert reconcile_subscription_seat_quantities() == {}
        modify.assert_not_called()

    def test_one_business_failing_does_not_stop_the_pass(self):
        import stripe
        from apps.subscriptions.tasks import reconcile_subscription_seat_quantities
        for key in ("a", "b"):
            t, biz, _plan, _seats = _business_with_sub(seats=2, key=key)
            Customer.objects.create(tenant=t, external_id="seat-new", account_type="seat",
                                    parent=biz)

        def refuse_a_only(**kw):
            if kw["id"] == "si_sa":
                raise stripe.error.InvalidRequestError("refused", "id")

        with patch(MODIFY, side_effect=refuse_a_only):
            assert reconcile_subscription_seat_quantities() == {"failed": 1, "pushed": 1}
        assert CustomerSubscriptionItem.objects.get(stripe_subscription_item_id="si_sb").quantity == 3


class TestEveryRosterMutationNotifies(RailActivated, TestCase):
    """Every seat roster mutation notifies the roster hook once, inside its own
    transaction (A-2 (i)). An ALLOCATED business's seat is its own billing
    owner, so the money suspensions land on the seat itself."""

    def _allocated(self, **tenant_fields):
        return _business_with_sub(seats=3, topology="allocated", billing_mode="prepaid",
                                  **tenant_fields)

    def test_the_enforcing_stop_pushes_the_decremented_count(self):
        from apps.billing.gating.services.stop_signal_service import (
            StopSignalService, control_id_of)
        from apps.billing.gating.tests._helpers import FIXTURE_OPENING
        from apps.platform.work import reasons
        t, biz, _plan, seats = self._allocated(enforcement_mode="enforcing")
        seat = seats[0]
        with patch(SET_SEATS) as spy, patch("apps.platform.events.tasks.process_single_event"), \
                self.captureOnCommitCallbacks(execute=True):
            StopSignalService.drive_stop(
                seat.id, t, line=reasons.HARD_FLOOR,
                control_id=control_id_of(reasons.HARD_FLOOR, seat.id, t),
                balance_micros=-1, **FIXTURE_OPENING)
        seat.refresh_from_db()
        assert (seat.status, seat.suspension_reason) == ("suspended", reasons.HARD_FLOOR)
        spy.assert_called_once()
        assert spy.call_args.args[2] == 2

    def test_the_off_floor_pushes_the_decremented_count(self):
        from apps.billing.wallets import operations as wallet_ops
        from apps.billing.wallets.models import Wallet
        from apps.platform.work import reasons
        from core.vocabulary import TRIGGER_SOURCE_USAGE_INGEST
        t, biz, _plan, seats = self._allocated()          # enforcement off
        seat = seats[0]
        Wallet.objects.create(customer=seat, balance_micros=1_000_000)
        with patch(SET_SEATS) as spy, patch("apps.platform.events.tasks.process_single_event"), \
                self.captureOnCommitCallbacks(execute=True):
            wallet_ops.draw_down_usage(
                customer_id=seat.id, tenant=t, usage_event_id=str(uuid.uuid4()),
                billed_cost_micros=2_000_000, trigger_source=TRIGGER_SOURCE_USAGE_INGEST)
        seat.refresh_from_db()
        assert (seat.status, seat.suspension_reason) == ("suspended", reasons.HARD_FLOOR)
        spy.assert_called_once()
        assert spy.call_args.args[2] == 2

    def test_a_reactivation_pushes_the_incremented_count(self):
        from apps.billing.gating.services.live_counter import LiveCounter
        from apps.platform.work import reasons
        t, biz, _plan, seats = self._allocated()
        seat = seats[0]
        Customer.objects.filter(id=seat.id).update(
            status="suspended", suspension_reason=reasons.PAYMENT_FAILED)
        assert seat_count(biz) == 2
        with patch(SET_SEATS) as spy, patch("apps.platform.events.tasks.process_single_event"), \
                self.captureOnCommitCallbacks(execute=True):
            assert LiveCounter.clear_payment_failed_suspension(seat.id) is True
        spy.assert_called_once()
        assert spy.call_args.args[2] == 3

    def test_a_manual_hold_and_its_release_push_the_count_and_converge(self):
        """The supported manual hold (R10 Stage C4, PLAN §7 item 41) is a roster
        change like any suspension: placing it pushes −1, releasing it +1, and a
        hold whose immediate push fails converges on the hourly pass."""
        from apps.billing.gating.services import manual_hold
        from apps.subscriptions.tasks import reconcile_subscription_seat_quantities
        t, biz, _plan, seats = _business_with_sub(seats=3)
        seat = seats[0]
        outbox = "apps.platform.events.tasks.process_single_event"
        with patch(SET_SEATS) as spy, patch(outbox), self.captureOnCommitCallbacks(execute=True):
            manual_hold.place_manual_hold(seat.id, operator="op-1")
        spy.assert_called_once()
        assert spy.call_args.args[2] == 2
        with patch(SET_SEATS) as spy, patch(outbox), self.captureOnCommitCallbacks(execute=True):
            manual_hold.release_manual_hold(seat.id, operator="op-1")
        spy.assert_called_once()
        assert spy.call_args.args[2] == 3

        stripe_side = _StripeSeatQuantity(quantity=3)
        with patch(MODIFY, side_effect=stripe_side.modify), patch(BACKOFF), patch(outbox):
            stripe_side.failing = True
            with self.captureOnCommitCallbacks(execute=True):
                manual_hold.place_manual_hold(seat.id, operator="op-1")
            stripe_side.failing = False
            assert stripe_side.requests[-1][1:] == (2, "failed")      # the immediate push
            assert reconcile_subscription_seat_quantities() == {"pushed": 1}
            assert (stripe_side.requests[-1][1:], stripe_side.quantity) == ((2, "applied"), 2)

    def test_two_creates_in_one_transaction_push_once_with_the_final_count(self):
        from django.db import transaction
        from apps.platform.customers.hooks import notify_seat_roster_changed
        t, biz, _plan, _seats = _business_with_sub(seats=2)
        with patch(SET_SEATS) as spy, self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                for external_id in ("new-1", "new-2"):
                    Customer.objects.create(tenant=t, external_id=external_id,
                                            account_type="seat", parent=biz)
                    notify_seat_roster_changed(biz)
        spy.assert_called_once()
        assert spy.call_args.args[2] == 4

    def test_a_rolled_back_change_queues_no_push_and_suppresses_none(self):
        """A push queued inside a savepoint that rolls back is dropped with it,
        and the next change in the same transaction still queues its own."""
        from django.db import transaction
        from apps.platform.customers.hooks import notify_seat_roster_changed
        t, biz, _plan, _seats = _business_with_sub(seats=2)
        with patch(SET_SEATS) as spy, self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                try:
                    with transaction.atomic():
                        Customer.objects.create(tenant=t, external_id="gone",
                                                account_type="seat", parent=biz)
                        notify_seat_roster_changed(biz)
                        raise RuntimeError("roll the savepoint back")
                except RuntimeError:
                    pass
                Customer.objects.create(tenant=t, external_id="kept",
                                        account_type="seat", parent=biz)
                notify_seat_roster_changed(biz)
        spy.assert_called_once()
        assert spy.call_args.args[2] == 3
