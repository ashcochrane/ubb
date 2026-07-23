"""P6b (D13/D15) as reshaped by #39: durable suspend + suspension_reason +
un-suspend, riding the StopSignalState transition guard.

The postpaid durable suspend now happens at the CROSSING, inside the winning
stop transition (StopSignalService.drive_stop, reached from the fast lane's
_set_stop) — the async drawdown handler no longer reads the stop flag, so a
crossing observed by several lanes suspends and emits exactly once.
suspension_reason records WHY; only a monetary reason is auto-cleared on
recovery, so a top-up never silently un-suspends an admin/fraud suspension.
"""
import uuid

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


def _tenant(mode="postpaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


def _payload(t, c, billed):
    return {"tenant_id": str(t.id), "customer_id": str(c.id),
            "event_id": str(uuid.uuid4()), "cost_micros": billed}


def _suspend_events(cid):
    return OutboxEvent.objects.filter(
        event_type="billing.customer_suspended", payload__customer_id=str(cid))


@pytest.mark.django_db
class TestPostpaidDurableSuspend:
    def setup_method(self):
        cache.clear()

    def test_durable_suspend_at_the_crossing(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000,
                                    enforce_mode="enforcing")
        # The fast lane's crossing wins the stop transition and suspends there
        # (#39) — the handler drain adds nothing for postpaid.
        LiveCounter.debit(c.id, t, 12_000_000, now=timezone.now())
        handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, 12_000_000))
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == "budget_exceeded"
        assert _suspend_events(c.id).count() == 1

    def test_single_emit_on_repeat_events(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000,
                                    enforce_mode="enforcing")
        LiveCounter.debit(c.id, t, 12_000_000, now=timezone.now())
        LiveCounter.debit(c.id, t, 5_000_000, now=timezone.now())
        handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, 5_000_000))
        handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, 5_000_000))
        assert _suspend_events(c.id).count() == 1  # winning transition only


@pytest.mark.django_db
class TestPrepaidSuspendReason:
    def setup_method(self):
        cache.clear()

    def test_prepaid_floor_suspend_records_reason(self):
        t = _tenant(mode="prepaid", enf="off")  # prepaid floor suspend is baseline
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, 5_000_000))  # -> -5M < floor 0
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == "min_balance_exceeded"


@pytest.mark.django_db
class TestUnsuspendOnRecovery:
    def setup_method(self):
        cache.clear()

    def test_credit_recovery_unsuspends_money_reason(self):
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveCounter.debit(c.id, t, 6_000_000, now=timezone.now())  # flag set
        c.status = "suspended"
        c.suspension_reason = "min_balance_exceeded"
        c.save(update_fields=["status", "suspension_reason"])
        LiveCounter.credit(c.id, t, 10_000_000)  # recovers above floor
        c.refresh_from_db()
        assert c.status == "active"
        assert c.suspension_reason == ""

    def test_credit_recovery_does_not_unsuspend_nonmoney_reason(self):
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveCounter.debit(c.id, t, 6_000_000, now=timezone.now())
        c.status = "suspended"
        c.suspension_reason = "fraud_review"  # admin suspension
        c.save(update_fields=["status", "suspension_reason"])
        LiveCounter.credit(c.id, t, 10_000_000)
        c.refresh_from_db()
        assert c.status == "suspended"  # never auto-cleared


@pytest.mark.django_db
class TestP6bReviewFixes:
    def setup_method(self):
        cache.clear()

    def test_postpaid_suspended_idle_owner_unsuspended_by_reconcile(self):
        # Deadlock fix: a budget-suspended postpaid owner with NO current-month
        # usage (start-gate-blocked) must still be reconciled + un-suspended.
        from apps.billing.gating.tasks import reconcile_live_ledgers
        t = _tenant()  # postpaid enforcing
        c = Customer.objects.create(tenant=t, external_id="c1",
                                    status="suspended", suspension_reason="budget_exceeded")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000,
                                    enforce_mode="enforcing")
        reconcile_live_ledgers()
        c.refresh_from_db()
        assert c.status == "active"
        assert c.suspension_reason == ""

    def test_credit_unsuspend_gated_on_durable_balance(self):
        # The live counter can over-state (e.g. an unmirrored dispute debit) —
        # un-suspend must use the DURABLE wallet, not the live counter.
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1",
                                    status="suspended", suspension_reason="min_balance_exceeded")
        Wallet.objects.create(customer=c, balance_micros=-5_000_000)  # durable below floor
        Door.set_balance(c.id, 1_000_000)  # live counter over-states
        LiveCounter.credit(c.id, t, 100_000)  # live -> 1.1M >= floor, durable still -5M
        c.refresh_from_db()
        assert c.status == "suspended"  # NOT un-suspended (durable still below floor)
