"""P2 (WS1): the synchronous live-spend/balance counter (LiveCounter, #111).

The counter is maintained synchronously in record_usage; P2 is write-only (P3
reads the verdict). These tests pin the decrement/credit/INCR semantics, the
flag gate, the backdate guard, the seed-once concurrency property, the
MIN/MAX reconcile directions, and pooled-owner postpaid aggregation.
"""
import datetime
import json
import threading
from unittest.mock import patch

import pytest
import redis
from django.conf import settings
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.live_counter import (Door, LiveCounter,
                                                       stop_channel)
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at)
from apps.metering.queries import get_billing_owner_billed_total
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.models import TenantApiKey
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY


def _tenant(mode="prepaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


@pytest.mark.django_db
class TestLiveCounterPrepaid:
    def setup_method(self):
        cache.clear()

    def test_flag_off_hook_is_noop(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        assert LiveCounter.debit(c.id, t, 30_000_000, now=timezone.now()) is None
        assert Door.balance(c.id) is None

    def test_seed_from_balance_then_decrby(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        out = LiveCounter.debit(c.id, t, 30_000_000, now=timezone.now())
        assert out["mode"] == "prepaid" and out["balance_micros"] == 70_000_000
        # second event: key present -> plain DECRBY
        LiveCounter.debit(c.id, t, 10_000_000, now=timezone.now())
        assert Door.balance(c.id) == 60_000_000

    def test_seed_once_across_repeated_first_use(self):
        # The SEED_AND_DECR EXISTS-guard seeds only on the first call; both
        # decrement. (Proxy for two concurrent first-use debits — the Lua is
        # atomic, so a second debit can never re-seed from the durable balance.)
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        LiveCounter.debit(c.id, t, 30_000_000, now=timezone.now())
        LiveCounter.debit(c.id, t, 30_000_000, now=timezone.now())
        assert Door.balance(c.id) == 40_000_000

    def test_credit_increments_when_seeded(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=50_000_000)
        LiveCounter.debit(c.id, t, 10_000_000, now=timezone.now())  # seeds -> 40M
        LiveCounter.credit(c.id, t, 20_000_000)
        assert Door.balance(c.id) == 60_000_000

    def test_credit_dropped_when_unseeded(self):
        # An unseeded credit is a no-op: first usage will seed from the
        # already-credited durable balance, so applying it now would double.
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=50_000_000)
        LiveCounter.credit(c.id, t, 20_000_000)
        assert Door.balance(c.id) is None

    def test_reconcile_min_merge_only_lowers(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=50_000_000)
        LiveCounter.debit(c.id, t, 10_000_000, now=timezone.now())  # live = 40M
        # durable HIGHER than live -> MIN keeps live (does not raise)
        w.balance_micros = 100_000_000
        w.save(update_fields=["balance_micros"])
        LiveCounter.reconcile(c.id, t)
        assert Door.balance(c.id) == 40_000_000
        # durable LOWER than live -> MIN lowers live toward durable
        w.balance_micros = 25_000_000
        w.save(update_fields=["balance_micros"])
        LiveCounter.reconcile(c.id, t)
        assert Door.balance(c.id) == 25_000_000


@pytest.mark.django_db
class TestLiveCounterPostpaid:
    def setup_method(self):
        cache.clear()

    def test_incr_and_read(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        out = LiveCounter.debit(c.id, t, 5_000_000, now=timezone.now())
        assert out["mode"] == "postpaid" and out["spend_micros"] == 5_000_000
        LiveCounter.debit(c.id, t, 4_000_000, now=timezone.now())
        assert Door.spend(c.id) == 9_000_000

    def test_backdated_prior_month_event_does_not_move_counter(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        LiveCounter.debit(c.id, t, 5_000_000, now=now)
        prior = now.replace(day=1) - datetime.timedelta(days=2)
        out = LiveCounter.debit(c.id, t, 9_000_000, effective_at=prior, now=now)
        assert out is None
        assert Door.spend(c.id, now=now) == 5_000_000

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
            Posting.objects.create(
                tenant=t, customer=seat, request_id=f"r{i}", idempotency_key=f"i{i}",
                provider_cost_micros=5_000_000, billed_cost_micros=5_000_000,
                billing_owner_id=biz.id)
        now = timezone.now()
        label, start, end = (lambda d: (None, d.replace(day=1),
                                        (d.replace(day=1) + datetime.timedelta(days=40)).replace(day=1)))(now.date())
        # A PAIR SINCE #351: the resolved owner-aggregated total, and how many
        # of the owner's postings it could not include.
        assert get_billing_owner_billed_total(t.id, biz.id, start, end) == {
            "billed": 10_000_000, UNPRICED_EVENT_COUNT_KEY: 0}
        # One seat already posted synchronously (owner-keyed); reconcile MAX-raises
        # to the full owner-aggregated total.
        LiveCounter.debit(biz.id, t, 5_000_000, now=now)  # live = 5M
        LiveCounter.reconcile(biz.id, t, now=now)
        assert Door.spend(biz.id, now=now) == 10_000_000


@pytest.mark.django_db
class TestStopFlag:
    """P3: the synchronous customer-wide cooperative stop flag."""

    def setup_method(self):
        cache.clear()

    def test_crossing_sets_flag_and_returns_verdict(self):
        t = _tenant()  # prepaid, enforcing; default min_balance floor = 0
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        out = LiveCounter.debit(c.id, t, 6_000_000, now=timezone.now())
        assert out["balance_micros"] == -1_000_000  # below floor (0)
        assert out["stop"] is True
        assert out["stop_reason"] == "customer_wide_stop"
        assert out["stop_scope"] == "customer"
        assert LiveCounter.read(c.id, t)["stop"] is True

    def test_non_crossing_sets_no_flag(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=100_000_000)
        out = LiveCounter.debit(c.id, t, 10_000_000, now=timezone.now())
        assert out["stop"] is False
        assert LiveCounter.read(c.id, t)["stop"] is False

    def test_flag_clears_on_credit_recovery(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        LiveCounter.debit(c.id, t, 6_000_000, now=timezone.now())  # flag set
        assert LiveCounter.read(c.id, t)["stop"] is True
        LiveCounter.credit(c.id, t, 10_000_000)  # live -1M -> 9M >= floor -> clear
        assert LiveCounter.read(c.id, t)["stop"] is False

    def test_off_sets_no_flag_and_reads_clear(self):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        assert LiveCounter.debit(c.id, t, 6_000_000, now=timezone.now()) is None
        assert LiveCounter.read(c.id, t)["stop"] is False

    def test_postpaid_crossing_at_budget_cap(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000,
                                    hard_stop_pct=100, enforce_mode="blocking")
        out = LiveCounter.debit(c.id, t, 12_000_000, now=timezone.now())
        assert out["spend_micros"] == 12_000_000
        assert out["stop"] is True

    def test_postpaid_alert_only_budget_never_stops_the_live_lane(self):
        """#110 drift resolution: enforce_mode is honored by EVERY lane via
        crossing.budget_stop_threshold — an alert_only budget (also the model
        default) alerts but can never stop. Pre-#110 the live fast lane
        ignored enforce_mode and would have stopped here."""
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000,
                                    hard_stop_pct=100, enforce_mode="alert_only")
        out = LiveCounter.debit(c.id, t, 12_000_000, now=timezone.now())
        assert out["spend_micros"] == 12_000_000  # the counter still tracks
        assert out["stop"] is False
        assert LiveCounter.read(c.id, t)["stop"] is False

    def test_postpaid_reconcile_clears_stale_flag_next_month(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000,
                                    enforce_mode="blocking")
        now = timezone.now()
        LiveCounter.debit(c.id, t, 12_000_000, now=now)  # flag set
        assert LiveCounter.read(c.id, t)["stop"] is True
        # Next month: fresh livespend key, durable spend 0 -> under cap -> the
        # monthless stop flag is cleared by the reconcile backstop.
        next_month = (now.replace(day=1) + datetime.timedelta(days=40)).replace(day=1)
        LiveCounter.reconcile(c.id, t, now=next_month)
        assert LiveCounter.read(c.id, t)["stop"] is False

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_crossing_returns_stop_event_persists_and_replays(self, _m):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        # The event that crosses the floor bills 6,000,000 — a figure the
        # tenant's own rule charges now, not one the call states (#365).
        a_rule_that_prices_what_it_measures(t)
        res = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            measurements=priced_at(6_000_000))
        # I3: the breaching event is recorded + charged (200 cooperative, not rolled back)
        assert res["stop"] is True and res["stop_reason"] == "customer_wide_stop"
        assert Posting.objects.filter(id=res["event_id"]).exists()
        # I4: the idempotent replay return ALSO carries the stop verdict
        replay = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            measurements=priced_at(6_000_000))
        assert replay["event_id"] == res["event_id"]
        assert replay["stop"] is True

    @patch("apps.platform.events.tasks.process_single_event")
    def test_pin2_failed_event_insert_rolls_the_transition_back(self, _m, monkeypatch):
        """Delivery pin 2 (#43, spec §A): the signal transition and its
        outbox write are ONE savepoint. A failed stop.fired INSERT rolls the
        StopSignalState transition (and the folded suspension) back with it —
        "signalled internally but never queued" is impossible by construction
        — while the ambient money path commits untouched: the usage event
        lands, bills, and the response still carries the flag verdict. What
        remains is a clean "not yet signalled" state, re-detected by the
        durable lane on the next landing event or by the patrol within the
        hour (pinned in test_patrol_pins.py, #44).

        The failure is simulated with a REAL failed SQL statement (SELECT 1/0
        -> DataError, a DatabaseError subclass), not a pure-Python raise —
        only a genuine DB error aborts the transaction, so only this shape of
        test can catch a missing savepoint."""
        from django.db import connection
        from apps.billing.gating.models import StopSignalState
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
        a_rule_that_prices_what_it_measures(t)
        res = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            measurements=priced_at(6_000_000))  # crosses the floor -> _set_stop fires
        # The one rule: record_usage returned normally; the tipping event
        # landed and billed.
        assert res["stop"] is True and res["stop_reason"] == "customer_wide_stop"
        assert Posting.objects.get(id=res["event_id"]).billed_cost_micros == 6_000_000
        # The ambient transaction stayed usable: the UsageRecorded outbox row
        # (written AFTER the failed StopFired insert) still landed.
        assert OutboxEvent.objects.filter(
            event_type="usage.recorded", payload__event_id=str(res["event_id"])).exists()
        # The savepoint took the transition down WITH the failed insert: no
        # ledger row, no stop.fired, no folded suspension — cleanly
        # un-signalled, never "transitioned but unqueued".
        assert not StopSignalState.objects.filter(owner=c).exists()
        assert not OutboxEvent.objects.filter(event_type="stop.fired").exists()
        c.refresh_from_db()
        assert c.status == "active"


@pytest.mark.django_db(transaction=True)
def test_concurrent_debits_at_floor_race():
    """20 threads x 1_500_000 against a 20_000_000 balance: every debit is
    atomic, the final balance is exactly 20_000_000 - 20*1_500_000, and the
    stop flag is set — the crossing detected exactly, no lost updates.

    Money-gate concurrency correctness under REAL threads against REAL Redis
    and real Lua. This pin rode ``LiveCounter.hold`` until #239; its subject
    was never the reservation but ``_SEED_AND_DECR`` — the seed-if-absent
    then DECRBY script — which is what ``debit`` runs on the surviving
    recording path. It is the only threaded test over this module's Lua, and
    ``test_seed_once_across_repeated_first_use`` does not replace it: that one
    is sequential, so it proves the seed fires once but not that concurrent
    decrements never lose an update.

    Needs transaction=True: real threads open separate DB connections, which
    (under the default rollback-wrapped django_db marker) cannot see the
    fixture's uncommitted Tenant/Customer/Wallet rows — a query deep in
    _crossed() (BillingTenantConfig.get_or_create's FK to tenant_id) would
    then fail invisibly-to-the-thread and get masked by debit's fail-open
    contract. transaction=True commits the rows for real so every thread's
    connection sees them, letting the race actually exercise Redis-level
    atomicity rather than each thread independently fail-opening.
    """
    cache.clear()
    t = _tenant()  # prepaid, enforcing; default min_balance floor = 0
    c = Customer.objects.create(tenant=t, external_id="race-owner")
    Wallet.objects.create(customer=c, balance_micros=20_000_000)

    results = []

    def go():
        try:
            results.append(LiveCounter.debit(c.id, t, 1_500_000,
                                             now=timezone.now()))
        finally:
            from django.db import connections
            connections.close_all()

    ts = [threading.Thread(target=go) for _ in range(20)]
    [thread.start() for thread in ts]
    [thread.join() for thread in ts]

    assert Door.balance(c.id) == 20_000_000 - 30_000_000
    # Fail-open returns None; a lost debit would show up in the balance above,
    # so this asserts every call actually reached the counter.
    assert all(r is not None for r in results)
    assert any(r["stop"] for r in results)


@pytest.mark.django_db
class TestStopPropagation:
    """``_set_stop``'s two best-effort fan-out legs, driven by the ONE
    surviving counter write.

    These pins used to ride ``LiveCounter.hold``; the reservation trio went
    with the async recording lane (#239) and the pins came here rather than
    going with it, because their subject is ``_set_stop`` — a mechanism the
    synchronous debit path still runs on every crossing. Losing them with the
    lane would have left the pub/sub publish, the one PUBLIC key-shaped name
    this module exposes, pinned by nothing but its own format test.

    The pub/sub leg is the reason this class exists: the ``stop.fired``
    emission guard is pinned durably elsewhere (test_stop_resume_pins.py,
    test_patrol_pins.py), the publish is not.
    """

    def setup_method(self):
        cache.clear()

    @staticmethod
    def _raw_client():
        return redis.from_url(settings.REDIS_URL)

    @classmethod
    def _subscribe(cls, owner_id):
        client = cls._raw_client()
        # ignore_subscribe_messages: get_message() should only ever surface the
        # real published payload, never the channel's own "subscribe" ack.
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        # PubSub.__init__ only keeps a reference to client.connection_pool, NOT
        # to `client` itself. Without this, `client` (a plain local var) would
        # be garbage-collected the moment this method returns, and
        # redis.Redis.__del__ calls close() ->
        # connection_pool.disconnect(inuse_connections=True) — which tears down
        # the very (in-use!) socket `pubsub` just subscribed on, silently. The
        # pubsub object doesn't notice: its next get_message() call
        # transparently reconnects + re-subscribes (redis-py's on_connect
        # hook), so there's no exception — but any publish sent during that
        # dead window is lost with zero visible error. Keeping `client` alive
        # on the pubsub object for the caller's lifetime prevents this.
        pubsub._keepalive_client = client
        pubsub.subscribe(stop_channel(owner_id))
        # Force the SUBSCRIBE round-trip to complete before returning, so a
        # publish emitted immediately after this call is guaranteed to be seen.
        pubsub.get_message(timeout=1)
        return pubsub

    @staticmethod
    def _funded_owner(t, balance_micros=20_000_000):
        c = Customer.objects.create(tenant=t, external_id="owner1")
        Wallet.objects.create(customer=c, balance_micros=balance_micros)
        return c

    def test_floor_crossing_publishes_once_and_emits_one_outbox_row(self):
        t = _tenant()  # prepaid, enforcing; default min_balance floor = 0
        c = self._funded_owner(t)
        pubsub = self._subscribe(c.id)
        try:
            LiveCounter.debit(c.id, t, 19_600_000, now=timezone.now())
            assert pubsub.get_message(timeout=0.2) is None  # no crossing yet

            out = LiveCounter.debit(c.id, t, 500_000, now=timezone.now())
            assert out["stop"] is True

            msg = pubsub.get_message(timeout=1)
            assert msg is not None and msg["type"] == "message"
            assert msg["data"].decode() == "customer_wide_stop"
            assert pubsub.get_message(timeout=0.2) is None  # exactly one

            assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1
            event = OutboxEvent.objects.get(event_type="stop.fired")
            assert event.payload["owner_id"] == str(c.id)
            assert event.payload["reason"] == "customer_wide_stop"
            assert event.payload["scope"] == "customer"
            assert event.payload["tenant_id"] == str(t.id)
        finally:
            pubsub.close()

    def test_second_crossing_while_flag_set_does_not_spam(self):
        t = _tenant()
        c = self._funded_owner(t)
        LiveCounter.debit(c.id, t, 19_600_000, now=timezone.now())
        LiveCounter.debit(c.id, t, 500_000, now=timezone.now())  # crosses
        assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1

        pubsub = self._subscribe(c.id)
        try:
            # Still stopped (flag already set) -> another crossing must NOT
            # publish/emit again (transition-only, no spam).
            out = LiveCounter.debit(c.id, t, 500_000, now=timezone.now())
            assert out["stop"] is True
            assert pubsub.get_message(timeout=0.3) is None
            assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1
        finally:
            pubsub.close()

    def test_flag_only_delete_does_not_re_emit_but_a_real_clear_re_arms(self):
        """#39: emission dedup lives on the signal ledger, not the Redis flag.

        A bare flag delete (a Redis flush / blind window, not a real recovery)
        re-arms the FAST LANE's pub/sub + flag, but the re-driven ledger
        transition loses (the episode is still open) — no duplicate
        stop.fired. Closing the episode through the guard (as every real
        clearing path does) re-arms emission: the next crossing opens episode
        2 and fires again.
        """
        from apps.billing.gating.services.stop_signal_service import (
            CLEAR_BALANCE_RECOVERED, StopSignalService)

        t = _tenant()
        c = self._funded_owner(t)
        LiveCounter.debit(c.id, t, 19_600_000, now=timezone.now())
        LiveCounter.debit(c.id, t, 500_000, now=timezone.now())  # crosses
        assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1

        Door.delete_stop(c.id)

        pubsub = self._subscribe(c.id)
        try:
            out = LiveCounter.debit(c.id, t, 500_000, now=timezone.now())
            assert out["stop"] is True
            msg = pubsub.get_message(timeout=1)
            assert msg is not None and msg["data"].decode() == "customer_wide_stop"
            # Episode still open on the ledger -> the re-set lost the transition.
            assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1
        finally:
            pubsub.close()

        # A REAL clear (through the guard) closes episode 1...
        StopSignalService.drive_clear(c.id, t, reason=CLEAR_BALANCE_RECOVERED)
        Door.delete_stop(c.id)
        # ...so the next crossing opens episode 2 and emits exactly once more.
        LiveCounter.debit(c.id, t, 500_000, now=timezone.now())
        fired = OutboxEvent.objects.filter(event_type="stop.fired").order_by("created_at")
        assert fired.count() == 2
        assert [e.payload["episode_seq"] for e in fired] == [1, 2]

    def test_publish_failure_does_not_raise_into_the_debit(self, monkeypatch):
        def _boom_publish(self, *args, **kwargs):
            raise ConnectionError("redis publish down")

        monkeypatch.setattr(redis.Redis, "publish", _boom_publish)

        t = _tenant()
        c = self._funded_owner(t)
        LiveCounter.debit(c.id, t, 19_600_000, now=timezone.now())
        out = LiveCounter.debit(c.id, t, 500_000, now=timezone.now())  # crosses
        assert out["stop"] is True
        # The outbox event (a separate best-effort side effect) still fires even
        # though pub/sub publish blew up.
        assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1


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
        LiveCounter.debit(c.id, t, 10_000_000, now=timezone.now())
        assert Door.balance(c.id) == 90_000_000

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
        assert Door.balance(c.id) == 110_000_000
