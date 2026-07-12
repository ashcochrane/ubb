"""P6b (D13/D15): durable postpaid suspend + suspension_reason + un-suspend.

The postpaid durable suspend is driven by the synchronous customer-wide stop
flag (single source of truth) and emitted ONLY by the async handler on the
winning active->suspended transition. suspension_reason records WHY; only a
monetary reason is auto-cleared on recovery, so a top-up never silently
un-suspends an admin/fraud suspension.
"""
import uuid

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.live_ledger_service import LiveLedgerService
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

    def test_durable_suspend_when_flag_set(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 12_000_000, now=timezone.now())  # cap crossed -> flag
        handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, 12_000_000))
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == "budget_exceeded"
        assert _suspend_events(c.id).count() == 1

    def test_single_emit_on_repeat_events(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 12_000_000, now=timezone.now())
        handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, 5_000_000))
        handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, 5_000_000))
        assert _suspend_events(c.id).count() == 1  # winning transition only

    def test_no_durable_suspend_in_advisory(self):
        t = _tenant(enf="advisory")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 12_000_000, now=timezone.now())  # flag set (advisory)
        handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, 12_000_000))
        c.refresh_from_db()
        assert c.status == "active"  # advisory never durably suspends


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
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())  # flag set
        c.status = "suspended"
        c.suspension_reason = "min_balance_exceeded"
        c.save(update_fields=["status", "suspension_reason"])
        LiveLedgerService.credit(c.id, t, 10_000_000)  # recovers above floor
        c.refresh_from_db()
        assert c.status == "active"
        assert c.suspension_reason == ""

    def test_credit_recovery_does_not_unsuspend_nonmoney_reason(self):
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())
        c.status = "suspended"
        c.suspension_reason = "fraud_review"  # admin suspension
        c.save(update_fields=["status", "suspension_reason"])
        LiveLedgerService.credit(c.id, t, 10_000_000)
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
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000)
        reconcile_live_ledgers()
        c.refresh_from_db()
        assert c.status == "active"
        assert c.suspension_reason == ""

    def test_credit_unsuspend_gated_on_durable_balance(self):
        # The live counter can over-state (e.g. an unmirrored dispute debit) —
        # un-suspend must use the DURABLE wallet, not the live counter.
        from apps.billing.gating.services.live_ledger_service import _client, _livebal_key
        t = _tenant(mode="prepaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="c1",
                                    status="suspended", suspension_reason="min_balance_exceeded")
        Wallet.objects.create(customer=c, balance_micros=-5_000_000)  # durable below floor
        _client().set(_livebal_key(c.id), 1_000_000)  # live counter over-states
        LiveLedgerService.credit(c.id, t, 100_000)  # live -> 1.1M >= floor, durable still -5M
        c.refresh_from_db()
        assert c.status == "suspended"  # NOT un-suspended (durable still below floor)
