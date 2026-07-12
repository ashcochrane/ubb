"""P2 (WS1): the synchronous live-spend/balance counter.

The counter is maintained synchronously in record_usage; P2 is write-only (P3
reads the verdict). These tests pin the decrement/credit/INCR semantics, the
flag gate, the backdate guard, the seed-once concurrency property, the
MIN/MAX reconcile directions, and pooled-owner postpaid aggregation.
"""
import datetime
import json
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.live_ledger_service import LiveLedgerService
from apps.billing.wallets.models import Wallet
from apps.metering.queries import get_billing_owner_billed_total
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.models import TenantApiKey


def _tenant(mode="prepaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


@pytest.mark.django_db
class TestLiveLedgerPrepaid:
    def setup_method(self):
        cache.clear()

    def test_flag_off_hook_is_noop(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        assert LiveLedgerService.record_usage_debit(c.id, t, 30_000_000, now=timezone.now()) is None
        assert LiveLedgerService.read_prepaid(c.id) is None

    def test_seed_from_balance_then_decrby(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        out = LiveLedgerService.record_usage_debit(c.id, t, 30_000_000, now=timezone.now())
        assert out["mode"] == "prepaid" and out["balance_micros"] == 70_000_000
        # second event: key present -> plain DECRBY
        LiveLedgerService.record_usage_debit(c.id, t, 10_000_000, now=timezone.now())
        assert LiveLedgerService.read_prepaid(c.id) == 60_000_000

    def test_seed_once_across_repeated_first_use(self):
        # The SEED_AND_DECR EXISTS-guard seeds only on the first call; both
        # decrement. (Proxy for two concurrent first-use debits — the Lua is
        # atomic, so a second debit can never re-seed from the durable balance.)
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 30_000_000, now=timezone.now())
        LiveLedgerService.record_usage_debit(c.id, t, 30_000_000, now=timezone.now())
        assert LiveLedgerService.read_prepaid(c.id) == 40_000_000

    def test_credit_increments_when_seeded(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=50_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 10_000_000, now=timezone.now())  # seeds -> 40M
        LiveLedgerService.credit(c.id, t, 20_000_000)
        assert LiveLedgerService.read_prepaid(c.id) == 60_000_000

    def test_credit_dropped_when_unseeded(self):
        # An unseeded credit is a no-op: first usage will seed from the
        # already-credited durable balance, so applying it now would double.
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=50_000_000)
        LiveLedgerService.credit(c.id, t, 20_000_000)
        assert LiveLedgerService.read_prepaid(c.id) is None

    def test_reconcile_min_merge_only_lowers(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=50_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 10_000_000, now=timezone.now())  # live = 40M
        # durable HIGHER than live -> MIN keeps live (does not raise)
        w.balance_micros = 100_000_000
        w.save(update_fields=["balance_micros"])
        LiveLedgerService.reconcile_prepaid(c.id, t)
        assert LiveLedgerService.read_prepaid(c.id) == 40_000_000
        # durable LOWER than live -> MIN lowers live toward durable
        w.balance_micros = 25_000_000
        w.save(update_fields=["balance_micros"])
        LiveLedgerService.reconcile_prepaid(c.id, t)
        assert LiveLedgerService.read_prepaid(c.id) == 25_000_000


@pytest.mark.django_db
class TestLiveLedgerPostpaid:
    def setup_method(self):
        cache.clear()

    def test_incr_and_read(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        out = LiveLedgerService.record_usage_debit(c.id, t, 5_000_000, now=timezone.now())
        assert out["mode"] == "postpaid" and out["spend_micros"] == 5_000_000
        LiveLedgerService.record_usage_debit(c.id, t, 4_000_000, now=timezone.now())
        assert LiveLedgerService.read_postpaid(c.id) == 9_000_000

    def test_backdated_prior_month_event_does_not_move_counter(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        LiveLedgerService.record_usage_debit(c.id, t, 5_000_000, now=now)
        prior = now.replace(day=1) - datetime.timedelta(days=2)
        out = LiveLedgerService.record_usage_debit(c.id, t, 9_000_000, effective_at=prior, now=now)
        assert out is None
        assert LiveLedgerService.read_postpaid(c.id, now=now) == 5_000_000

    def test_pooled_postpaid_aggregates_seats_at_owner(self):
        t = _tenant(mode="postpaid")
        biz = Customer.objects.create(tenant=t, external_id="biz",
                                      account_type="business", billing_topology="pooled")
        s1 = Customer.objects.create(tenant=t, external_id="s1",
                                     account_type="seat", parent=biz)
        s2 = Customer.objects.create(tenant=t, external_id="s2",
                                     account_type="seat", parent=biz)
        assert s1.resolve_billing_owner().id == biz.id  # pooled -> business
        # Durable events for both seats pin the business as billing owner.
        for i, seat in enumerate((s1, s2)):
            UsageEvent.objects.create(
                tenant=t, customer=seat, request_id=f"r{i}", idempotency_key=f"i{i}",
                provider_cost_micros=5_000_000, billed_cost_micros=5_000_000,
                billing_owner_id=biz.id)
        now = timezone.now()
        label, start, end = (lambda d: (None, d.replace(day=1),
                                        (d.replace(day=1) + datetime.timedelta(days=40)).replace(day=1)))(now.date())
        assert get_billing_owner_billed_total(t.id, biz.id, start, end) == 10_000_000
        # One seat already posted synchronously (owner-keyed); reconcile MAX-raises
        # to the full owner-aggregated total.
        LiveLedgerService.record_usage_debit(biz.id, t, 5_000_000, now=now)  # live = 5M
        LiveLedgerService.reconcile_postpaid(biz.id, t, now=now)
        assert LiveLedgerService.read_postpaid(biz.id, now=now) == 10_000_000


@pytest.mark.django_db
class TestStopFlag:
    """P3: the synchronous customer-wide cooperative stop flag."""

    def setup_method(self):
        cache.clear()

    def test_crossing_sets_flag_and_returns_verdict(self):
        t = _tenant()  # prepaid, enforcing; default min_balance floor = 0
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        out = LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())
        assert out["balance_micros"] == -1_000_000  # below floor (0)
        assert out["stop"] is True
        assert out["stop_reason"] == "customer_wide_stop"
        assert out["stop_scope"] == "customer"
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is True

    def test_non_crossing_sets_no_flag(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        out = LiveLedgerService.record_usage_debit(c.id, t, 10_000_000, now=timezone.now())
        assert out["stop"] is False
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is False

    def test_flag_clears_on_credit_recovery(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())  # flag set
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is True
        LiveLedgerService.credit(c.id, t, 10_000_000)  # live -1M -> 9M >= floor -> clear
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is False

    def test_advisory_mode_still_sets_flag(self):
        t = _tenant(enf="advisory")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        out = LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now())
        assert out["stop"] is True  # advisory computes+emits; UBB itself never blocks

    def test_off_sets_no_flag_and_reads_clear(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        assert LiveLedgerService.record_usage_debit(c.id, t, 6_000_000, now=timezone.now()) is None
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is False

    def test_postpaid_crossing_at_budget_cap(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000, hard_stop_pct=100)
        out = LiveLedgerService.record_usage_debit(c.id, t, 12_000_000, now=timezone.now())
        assert out["spend_micros"] == 12_000_000
        assert out["stop"] is True

    def test_postpaid_reconcile_clears_stale_flag_next_month(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000)
        now = timezone.now()
        LiveLedgerService.record_usage_debit(c.id, t, 12_000_000, now=now)  # flag set
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is True
        # Next month: fresh livespend key, durable spend 0 -> under cap -> the
        # monthless stop flag is cleared by the reconcile backstop.
        next_month = (now.replace(day=1) + datetime.timedelta(days=40)).replace(day=1)
        LiveLedgerService.reconcile_postpaid(c.id, t, now=next_month)
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is False

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_crossing_returns_stop_event_persists_and_replays(self, _m):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        res = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            billed_cost_micros=6_000_000)
        # I3: the breaching event is recorded + charged (200 cooperative, not rolled back)
        assert res["stop"] is True and res["stop_reason"] == "customer_wide_stop"
        assert UsageEvent.objects.filter(id=res["event_id"]).exists()
        # I4: the idempotent replay return ALSO carries the stop verdict
        replay = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            billed_cost_micros=6_000_000)
        assert replay["event_id"] == res["event_id"]
        assert replay["stop"] is True

    @patch("apps.platform.events.tasks.process_single_event")
    def test_stop_fired_db_failure_cannot_poison_record_usage_transaction(self, _m, monkeypatch):
        """Task 7 regression: _set_stop's StopFired outbox INSERT runs INSIDE
        record_usage's outer @transaction.atomic on the sync path. If that
        INSERT fails at the DB level, a bare try/except swallows the Python
        exception but leaves the ambient Postgres transaction ABORTED — the
        very next statement (write_event(UsageRecorded)) would raise
        "current transaction is aborted", 500ing the money path. _set_stop's
        savepoint (transaction.atomic inside the try/except) must roll the
        failed INSERT back cleanly.

        The failure is simulated with a REAL failed SQL statement (SELECT 1/0
        -> DataError, a DatabaseError subclass), not a pure-Python raise —
        only a genuine DB error aborts the transaction, so only this shape of
        test can catch a missing savepoint."""
        from django.db import connection
        from apps.platform.events.models import OutboxEvent

        orig_create = OutboxEvent.objects.create

        def _create(**kwargs):
            if kwargs.get("event_type") == "stop.fired":
                with connection.cursor() as cur:
                    cur.execute("SELECT 1/0")  # DataError; aborts the ambient tx
            return orig_create(**kwargs)

        monkeypatch.setattr(OutboxEvent.objects, "create", _create)

        t = _tenant()  # prepaid, enforcing; floor = 0
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        res = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            billed_cost_micros=6_000_000)  # crosses the floor -> _set_stop fires
        # record_usage returned normally, with the stop verdict.
        assert res["stop"] is True and res["stop_reason"] == "customer_wide_stop"
        assert UsageEvent.objects.filter(id=res["event_id"]).exists()
        # The UsageRecorded outbox row (written AFTER the failed StopFired
        # insert, in the same outer transaction) still landed...
        assert OutboxEvent.objects.filter(
            event_type="usage.recorded", payload__event_id=str(res["event_id"])).exists()
        # ...and the StopFired emission was dropped (best-effort), not retried.
        assert not OutboxEvent.objects.filter(event_type="stop.fired").exists()


@pytest.mark.django_db
class TestCreditHookFiresThroughEndpoint:
    """Proves the on_commit credit hook actually reaches the live counter via a
    real request (the wiring the unit tests don't exercise). The other four
    credit sites use the identical transaction.on_commit(credit) pattern."""

    def setup_method(self):
        cache.clear()

    def test_manual_credit_endpoint_raises_live_balance(self, django_capture_on_commit_callbacks):
        t = _tenant()  # prepaid, enforcing
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        _key, raw = TenantApiKey.create_key(t, label="t")
        # Seed the live counter (credit only applies once seeded).
        LiveLedgerService.record_usage_debit(c.id, t, 10_000_000, now=timezone.now())
        assert LiveLedgerService.read_prepaid(c.id) == 90_000_000

        with django_capture_on_commit_callbacks(execute=True):
            resp = Client().post(
                "/api/v1/billing/credit",
                data=json.dumps({"customer_id": "c1", "amount_micros": 20_000_000,
                                 "source": "goodwill", "reference": "tkt-1",
                                 "idempotency_key": "idem_tkt_1"}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert resp.status_code == 200
        # 90M − (durable credit mirrored) → 110M on the fast path.
        assert LiveLedgerService.read_prepaid(c.id) == 110_000_000
