import datetime
import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.wallets.tasks import reconcile_usage_drawdowns


def _old_event(t, c, owner_id, billed, key_suffix, *, effective_at=None):
    e = UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key=key_suffix,
                                  billed_cost_micros=billed, billing_owner_id=owner_id)
    # F4.2: the repair scan is ARRIVAL-basis (created_at) — age the arrival
    # time past GRACE; effective_at is irrelevant to eligibility.
    aged = timezone.now() - datetime.timedelta(hours=8)
    UsageEvent.objects.filter(id=e.id).update(
        created_at=aged, effective_at=effective_at if effective_at else aged)
    return e


@pytest.mark.django_db
class TestReconcileDrawdowns:
    def test_repairs_missing_debit_exactly_once(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        e = _old_event(t, c, c.id, 2_000_000, "i1")  # committed usage, NO debit
        reconcile_usage_drawdowns()
        w.refresh_from_db()
        assert w.balance_micros == -2_000_000
        assert WalletTransaction.objects.filter(wallet=w, usage_event_id=e.id,
                                                transaction_type="USAGE_DEDUCTION").count() == 1
        reconcile_usage_drawdowns()  # idempotent
        w.refresh_from_db()
        assert w.balance_micros == -2_000_000

    def test_does_not_redebit_already_debited_via_column(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=-2_000_000)
        e = _old_event(t, c, c.id, 2_000_000, "i1")
        WalletTransaction.objects.create(wallet=w, transaction_type="USAGE_DEDUCTION",
            amount_micros=-2_000_000, balance_after_micros=-2_000_000,
            reference_id=str(e.id), idempotency_key="usage_deduction:OLD_OUTBOX_KEY",
            usage_event_id=e.id)  # old key, but column backfilled
        reconcile_usage_drawdowns()
        w.refresh_from_db()
        assert w.balance_micros == -2_000_000  # NOT re-debited (column anti-join)
        assert WalletTransaction.objects.filter(wallet=w, usage_event_id=e.id).count() == 1

    def test_skips_fresh_events_within_grace(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i1",
                                  billed_cost_micros=2_000_000, billing_owner_id=c.id)  # created_at = now
        reconcile_usage_drawdowns()
        w.refresh_from_db()
        assert w.balance_micros == 0  # within grace -> not repaired

    def test_backfilled_event_repaired_on_arrival_basis(self):
        """basis=created proof: effective_at 30 days ago (older than the 7d
        LOOKBACK), but the event ARRIVED 8h ago — it must be repaired
        exactly-once via the usage_deduction:{id} key. Under the old
        effective-basis scan this event was invisible to repair forever."""
        t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        e = _old_event(t, c, c.id, 3_000_000, "i-backfill",
                       effective_at=timezone.now() - datetime.timedelta(days=30))
        reconcile_usage_drawdowns()
        w.refresh_from_db()
        assert w.balance_micros == -3_000_000
        tx = WalletTransaction.objects.get(wallet=w, usage_event_id=e.id)
        assert tx.idempotency_key == f"usage_deduction:{e.id}"
        reconcile_usage_drawdowns()  # exactly-once
        w.refresh_from_db()
        assert w.balance_micros == -3_000_000
        assert WalletTransaction.objects.filter(wallet=w, usage_event_id=e.id).count() == 1

    def test_fresh_arrival_with_old_effective_at_waits_for_grace(self):
        """An event backdated 30d but inserted JUST NOW is inside the arrival
        grace window — the live outbox path still owns it; no repair yet."""
        t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        e = UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i1",
                                      billed_cost_micros=2_000_000, billing_owner_id=c.id)
        UsageEvent.objects.filter(id=e.id).update(
            effective_at=timezone.now() - datetime.timedelta(days=30))  # created_at stays now
        reconcile_usage_drawdowns()
        w.refresh_from_db()
        assert w.balance_micros == 0
