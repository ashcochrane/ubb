"""Task 4: HoldService — the atomic accept-time hold (Lua) for the async
ingest path.

HoldService reuses the Tier-2 live-ledger keys/semantics
(live_ledger_service.py) — the SAME owner-keyed prepaid balance / postpaid
spend counter and cooperative customer-wide stop flag that the synchronous
record_usage_debit path maintains. A hold taken here is visible to (and
raced against) the synchronous path through the identical Redis keys.

One-rule (#37): acquire ALWAYS holds — nothing on this path ever rejects an
item. Per-item verdicts carry only {held, stop, stop_reason, stop_scope};
the retired accept-time per-unit cap lane (ubb:runcost:* keys, the
check-then-increment reject branch) is gone, so unit-limit detection lives at
settle (UsageService.settle_raw), never here.

Money-gate concurrency correctness is the whole point of this module, so
test_concurrent_holds_at_floor_race drives 20 REAL threads against REAL
Redis and asserts the exact final balance (no lost updates).
"""
import threading

import pytest
import redis
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.hold_service import HoldService
from apps.billing.gating.services.live_ledger_service import LiveLedgerService
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _flush_redis_keys():
    # Same idiom as the other Tier-2 gating tests (test_live_ledger.py etc):
    # cache.clear() FLUSHDBs the dedicated test Redis db (see root
    # conftest.py), which also wipes the raw ubb:livebal:*/livespend:*/
    # stop:* keys written via _client() (a separate raw connection to the
    # SAME db — not routed through django's cache API/prefixing).
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def enforced_prepaid_tenant():
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode="prepaid", enforcement_mode="enforcing")


@pytest.fixture
def enforced_postpaid_tenant():
    return Tenant.objects.create(name="TP", products=["metering", "billing"],
                                 billing_mode="postpaid", enforcement_mode="enforcing")


@pytest.fixture
def funded_owner(enforced_prepaid_tenant):
    c = Customer.objects.create(tenant=enforced_prepaid_tenant, external_id="owner1")
    Wallet.objects.create(customer=c, balance_micros=20_000_000)
    return c


@pytest.fixture
def postpaid_owner(enforced_postpaid_tenant):
    return Customer.objects.create(tenant=enforced_postpaid_tenant, external_id="powner1")


def _item(est, effective_at=None):
    return {"estimate_micros": est, "effective_at": effective_at}


def test_hold_decrements_live_balance(enforced_prepaid_tenant, funded_owner):
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                              [_item(2_920_000)])
    assert out[0]["held"] and not out[0]["stop"]
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 17_080_000


def test_floor_crossing_sets_stop_but_holds(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(19_600_000)])
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])
    assert out[0]["held"] is True          # cooperative (I3)
    assert out[0]["stop"] is True
    assert out[0]["stop_scope"] == "customer"


def test_acquire_never_rejects_far_beyond_balance(enforced_prepaid_tenant, funded_owner):
    # One-rule (#37) replacement pin for the retired accept-time cap lane:
    # an item FAR beyond any balance is still held — the verdict dict has no
    # rejected/reason keys at all; the crossing surfaces only via the
    # cooperative stop fields.
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                              [_item(999_000_000_000)])
    assert out[0]["held"] is True
    assert set(out[0]) == {"held", "stop", "stop_reason", "stop_scope"}
    assert out[0]["stop"] is True
    assert out[0]["stop_scope"] == "customer"
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 20_000_000 - 999_000_000_000


# ---- Task 7: stop propagation (pub/sub + stop.fired outbox event) --------

def _raw_client():
    # Same idiom as test_card_cache.py: a separate raw connection to the
    # SAME test Redis db that _client() inside the services uses.
    return redis.from_url(settings.REDIS_URL)


def _subscribe(owner_id):
    client = _raw_client()
    # ignore_subscribe_messages: get_message() should only ever surface the
    # real published payload, never the channel's own "subscribe" ack.
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    # PubSub.__init__ only keeps a reference to client.connection_pool, NOT to
    # `client` itself. Without this, `client` (a plain local var) would be
    # garbage-collected the moment this function returns, and redis.Redis.__del__
    # calls close() -> connection_pool.disconnect(inuse_connections=True) —
    # which tears down the very (in-use!) socket `pubsub` just subscribed on,
    # silently. The pubsub object doesn't notice: its next get_message() call
    # transparently reconnects + re-subscribes (redis-py's on_connect hook), so
    # there's no exception — but any publish sent during that dead window is
    # lost with zero visible error. Keeping `client` alive on the pubsub object
    # for the caller's lifetime prevents this.
    pubsub._keepalive_client = client
    pubsub.subscribe(f"ubb:stopchan:{owner_id}")
    # Force the SUBSCRIBE round-trip to complete before returning, so a
    # publish emitted immediately after this call is guaranteed to be seen.
    pubsub.get_message(timeout=1)
    return pubsub


def test_floor_crossing_publishes_once_and_emits_one_outbox_row(
        enforced_prepaid_tenant, funded_owner):
    pubsub = _subscribe(funded_owner.id)
    try:
        HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(19_600_000)])
        assert pubsub.get_message(timeout=0.2) is None  # no crossing yet -> no publish

        out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])
        assert out[0]["stop"] is True

        msg = pubsub.get_message(timeout=1)
        assert msg is not None and msg["type"] == "message"
        assert msg["data"].decode() == "customer_wide_stop"
        assert pubsub.get_message(timeout=0.2) is None  # exactly one message

        assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1
        event = OutboxEvent.objects.get(event_type="stop.fired")
        assert event.payload["owner_id"] == str(funded_owner.id)
        assert event.payload["reason"] == "customer_wide_stop"
        assert event.payload["scope"] == "customer"
        assert event.payload["tenant_id"] == str(enforced_prepaid_tenant.id)
    finally:
        pubsub.close()


def test_second_crossing_while_flag_set_does_not_spam(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(19_600_000)])
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])  # crosses
    assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1

    pubsub = _subscribe(funded_owner.id)
    try:
        # Still stopped (flag already set) -> another crossing must NOT
        # publish/emit again (transition-only, no spam).
        out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])
        assert out[0]["stop"] is True
        assert pubsub.get_message(timeout=0.3) is None
        assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1
    finally:
        pubsub.close()


def test_flag_only_delete_does_not_re_emit_but_a_real_clear_re_arms(enforced_prepaid_tenant, funded_owner):
    """#39: emission dedup moved from the Redis NX flag to the signal ledger.

    A bare flag delete (a Redis flush / blind window, not a real recovery)
    re-arms the FAST LANE's pub/sub + flag, but the re-driven ledger
    transition loses (the episode is still open) — no duplicate stop.fired.
    Closing the episode through the guard (as every real clearing path does)
    re-arms emission: the next crossing opens episode 2 and fires again.
    """
    from apps.billing.gating.services.stop_signal_service import (
        CLEAR_BALANCE_RECOVERED, StopSignalService)

    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(19_600_000)])
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])  # crosses
    assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1

    LiveLedgerService._clear_stop(funded_owner.id)

    pubsub = _subscribe(funded_owner.id)
    try:
        out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])
        assert out[0]["stop"] is True
        msg = pubsub.get_message(timeout=1)
        assert msg is not None and msg["data"].decode() == "customer_wide_stop"
        # Episode still open on the ledger -> the re-set lost the transition.
        assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1
    finally:
        pubsub.close()

    # A REAL clear (through the guard) closes episode 1...
    StopSignalService.drive_clear(funded_owner.id, enforced_prepaid_tenant,
                                  reason=CLEAR_BALANCE_RECOVERED)
    LiveLedgerService._clear_stop(funded_owner.id)
    # ...so the next crossing opens episode 2 and emits exactly once more.
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])
    fired = OutboxEvent.objects.filter(event_type="stop.fired").order_by("created_at")
    assert fired.count() == 2
    assert [e.payload["episode_seq"] for e in fired] == [1, 2]


def test_publish_failure_does_not_raise_into_acquire(enforced_prepaid_tenant, funded_owner, monkeypatch):
    def _boom_publish(self, *args, **kwargs):
        raise ConnectionError("redis publish down")

    monkeypatch.setattr(redis.Redis, "publish", _boom_publish)

    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(19_600_000)])
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])  # crosses
    assert out[0]["held"] is True
    assert out[0]["stop"] is True
    # The outbox event (a separate best-effort side effect) still fires even
    # though pub/sub publish blew up.
    assert OutboxEvent.objects.filter(event_type="stop.fired").count() == 1


def test_settle_delta_credits_overhold(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(2_500_000)])
    HoldService.settle(funded_owner.id, enforced_prepaid_tenant, 300_000)  # exact was 2_200_000
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 17_800_000


def test_settle_negative_delta_debits_further(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(2_500_000)])
    # exact turned out HIGHER than the estimate -> delta is negative.
    HoldService.settle(funded_owner.id, enforced_prepaid_tenant, -100_000)
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 17_400_000


def test_release_fully_credits_back(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(5_000_000)])
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 15_000_000
    HoldService.release(funded_owner.id, enforced_prepaid_tenant, 5_000_000)
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 20_000_000


def test_postpaid_incr_increases_spend_not_decreases(enforced_postpaid_tenant, postpaid_owner):
    """Regression pin for the sign-handling note in the task brief: the
    postpaid path must INCREASE the live spend counter by the estimate, never
    decrease it (a naive DECRBY-of-negative implementation would get this
    backwards)."""
    out = HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(4_000_000)])
    assert out[0]["held"]
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 4_000_000
    HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(1_000_000)])
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 5_000_000


def test_postpaid_settle_delta_lowers_live_spend(enforced_postpaid_tenant, postpaid_owner):
    """Postpaid settle must lower the live month-to-date spend counter by the
    over-hold (LiveLedgerService.credit no-ops for postpaid, so settle needs
    its own direct livespend adjustment — otherwise every over-estimate
    permanently inflates the counter: reconcile_postpaid only MAX-merges and
    can never lower it back)."""
    HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(2_500_000)])
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 2_500_000
    HoldService.settle(postpaid_owner.id, enforced_postpaid_tenant, 300_000)  # exact was 2_200_000
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 2_200_000


def test_postpaid_settle_negative_delta_raises_live_spend(enforced_postpaid_tenant, postpaid_owner):
    HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(2_500_000)])
    # exact came in HIGHER than the estimate -> delta negative -> spend rises.
    HoldService.settle(postpaid_owner.id, enforced_postpaid_tenant, -100_000)
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 2_600_000


def test_postpaid_release_restores_live_spend(enforced_postpaid_tenant, postpaid_owner):
    HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(4_000_000)])
    HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(1_000_000)])
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 5_000_000
    # Full release of the second hold (duplicate/failed append) -> back to
    # the pre-hold value.
    HoldService.release(postpaid_owner.id, enforced_postpaid_tenant, 1_000_000)
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 4_000_000


def test_postpaid_budget_crossing_sets_stop(enforced_postpaid_tenant, postpaid_owner):
    BudgetConfig.objects.create(tenant=enforced_postpaid_tenant, customer=postpaid_owner,
                                cap_micros=10_000_000, hard_stop_pct=100)
    out = HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(12_000_000)])
    assert out[0]["held"] is True
    assert out[0]["stop"] is True
    assert out[0]["stop_scope"] == "customer"


# ---- Final-review fix batch #2: I9 postpaid prior-month guard parity -----

def _prior_month_instant():
    from django.utils import timezone
    from datetime import timedelta
    now = timezone.now()
    return now.replace(day=1) - timedelta(days=1)


def test_postpaid_prior_month_acquire_skips_livespend(
        enforced_postpaid_tenant, postpaid_owner):
    """A batch item backdated to a PRIOR calendar month must not move the
    live spend counter (I9 parity with record_usage_debit) — it is still
    held."""
    out = HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant,
                              [_item(4_000_000, effective_at=_prior_month_instant())])
    assert out[0]["held"] is True
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) is None


def test_postpaid_current_month_acquire_unaffected_by_prior_month_guard(
        enforced_postpaid_tenant, postpaid_owner):
    """Regression: an item with no effective_at (or a current-month one)
    must move the live spend counter exactly as before the I9 fix."""
    out = HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant,
                              [_item(4_000_000, effective_at=None)])
    assert out[0]["held"] is True
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 4_000_000


def test_postpaid_settle_of_prior_month_event_skips_livespend_adjustment(
        enforced_postpaid_tenant, postpaid_owner):
    """settle() must mirror acquire()'s prior-month skip: settling an event
    whose effective_at falls in a PRIOR month must not adjust the current
    month's (unrelated) livespend counter."""
    HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(3_000_000)])
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 3_000_000

    HoldService.settle(postpaid_owner.id, enforced_postpaid_tenant, 500_000,
                       effective_at=_prior_month_instant())
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 3_000_000  # unchanged


def test_postpaid_settle_of_current_month_event_unaffected_by_the_guard(
        enforced_postpaid_tenant, postpaid_owner):
    """Regression: a settle with NO effective_at (or a current-month one)
    still adjusts the live spend counter exactly as before."""
    HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(3_000_000)])
    HoldService.settle(postpaid_owner.id, enforced_postpaid_tenant, 500_000)
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 2_500_000


def test_enforcement_off_is_noop_fail_open(funded_owner):
    off_tenant = Tenant.objects.create(name="Off", products=["metering", "billing"],
                                       billing_mode="prepaid", enforcement_mode="off")
    out = HoldService.acquire(funded_owner.id, off_tenant, [_item(999_000_000)])
    assert out[0]["held"] and not out[0]["stop"]
    assert LiveLedgerService.read_prepaid(funded_owner.id) is None


def test_fail_open_on_redis_error_holds_every_item(enforced_prepaid_tenant, funded_owner, monkeypatch):
    import apps.billing.gating.services.hold_service as hs_mod

    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(hs_mod, "_client", _boom)
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                              [_item(1_000_000), _item(2_000_000)])
    assert len(out) == 2
    assert all(o["held"] and not o["stop"] for o in out)


# ---- Final-review fix batch #3: threshold hoisted out of the per-item loop

def test_acquire_threshold_query_count_does_not_scale_with_batch_size(
        enforced_prepaid_tenant, funded_owner):
    """Before the fix, LiveLedgerService._crossed (and its ORM lookup) ran
    ONCE PER HELD ITEM inside acquire()'s loop -- so a 50-item batch issued
    ~50x the ORM queries of a 1-item batch. The threshold is now resolved
    ONCE per acquire() call and compared per item in plain Python, so the
    query count must be IDENTICAL regardless of N."""
    CustomerBillingProfile.objects.create(customer=funded_owner, min_balance_micros=-5_000_000)

    with CaptureQueriesContext(connection) as ctx_one:
        out1 = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(10_000)])
    assert out1[0]["held"]
    one_item_queries = len(ctx_one.captured_queries)

    with CaptureQueriesContext(connection) as ctx_many:
        out50 = HoldService.acquire(
            funded_owner.id, enforced_prepaid_tenant, [_item(10_000) for _ in range(50)])
    assert all(o["held"] for o in out50)
    fifty_item_queries = len(ctx_many.captured_queries)

    assert fifty_item_queries == one_item_queries
    # Sanity bound: a small per-batch constant (seed read + threshold read),
    # not a query storm.
    assert fifty_item_queries <= 3


def test_batch_pipelines_multiple_items_one_call(enforced_prepaid_tenant, funded_owner):
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                              [_item(1_000_000), _item(2_000_000)])
    assert out[0]["held"] and out[1]["held"]
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 20_000_000 - 3_000_000


@pytest.mark.django_db(transaction=True)
def test_concurrent_holds_at_floor_race(enforced_prepaid_tenant, funded_owner):
    """20 threads x 1_500_000 against a 20_000_000 balance: every hold is
    atomic, final balance is exactly 20_000_000 - 20*1_500_000, and the stop
    flag is set (crossing detected exactly, no lost updates).

    Needs transaction=True: real threads open separate DB connections, which
    (under the default rollback-wrapped django_db marker) cannot see the
    fixture's uncommitted Tenant/Customer/Wallet rows — a query deep in
    _crossed() (BillingTenantConfig.get_or_create's FK to tenant_id) would
    then fail invisibly-to-the-thread and get masked by HoldService's
    fail-open contract. transaction=True commits the fixtures for real so
    every thread's connection sees them, letting the race actually exercise
    Redis-level atomicity rather than each thread independently fail-opening.
    """
    results = []

    def go():
        try:
            results.extend(HoldService.acquire(
                funded_owner.id, enforced_prepaid_tenant, [_item(1_500_000)]))
        finally:
            from django.db import connections
            connections.close_all()

    ts = [threading.Thread(target=go) for _ in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 20_000_000 - 30_000_000
    assert any(r["stop"] for r in results)
