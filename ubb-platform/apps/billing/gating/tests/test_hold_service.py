"""Task 4: HoldService — the atomic accept-time gate (Lua holds + Redis
per-run cap) for the async ingest path.

HoldService reuses the Tier-2 live-ledger keys/semantics
(live_ledger_service.py) — the SAME owner-keyed prepaid balance / postpaid
spend counter and cooperative customer-wide stop flag that the synchronous
record_usage_debit path maintains. A hold taken here is visible to (and
raced against) the synchronous path through the identical Redis keys.

Money-gate concurrency correctness is the whole point of this module, so
test_concurrent_holds_at_floor_race drives 20 REAL threads against REAL
Redis and asserts the exact final balance (no lost updates).
"""
import threading

import pytest
from django.core.cache import cache

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.hold_service import HoldService
from apps.billing.gating.services.live_ledger_service import LiveLedgerService
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _flush_redis_keys():
    # Same idiom as the other Tier-2 gating tests (test_live_ledger.py etc):
    # cache.clear() FLUSHDBs the dedicated test Redis db (15 — see root
    # conftest.py), which also wipes the raw ubb:livebal:*/livespend:*/
    # runcost:*/stop:* keys written via _client() (a separate raw connection
    # to the SAME db — not routed through django's cache API/prefixing).
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


def _item(est, run_id=None, cap=None, seed=0):
    return {"estimate_micros": est, "run_id": run_id,
            "run_cap_micros": cap, "run_seed_micros": seed}


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


def test_run_cap_rejects_without_touching_balance(enforced_prepaid_tenant, funded_owner):
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                              [_item(600_000, run_id="r1", cap=500_000)])
    assert out[0]["rejected"] and out[0]["reason"] == "cost_limit_exceeded"
    assert LiveLedgerService.read_prepaid(funded_owner.id) in (None, 20_000_000)


def test_run_cap_accepts_up_to_cap_then_rejects(enforced_prepaid_tenant, funded_owner):
    out1 = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                               [_item(400_000, run_id="r1", cap=500_000)])
    assert out1[0]["held"] and not out1[0]["rejected"]
    # 400k + 200k = 600k > 500k cap -> reject; balance already moved for the
    # FIRST item must be untouched by this second, rejected item.
    out2 = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                               [_item(200_000, run_id="r1", cap=500_000)])
    assert out2[0]["rejected"]
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 20_000_000 - 400_000


def test_settle_delta_credits_overhold(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(2_500_000)])
    HoldService.settle(funded_owner.id, enforced_prepaid_tenant, None,
                       delta_micros=300_000)   # exact was 2_200_000
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 17_800_000


def test_settle_negative_delta_debits_further(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(2_500_000)])
    # exact turned out HIGHER than the estimate -> delta is negative.
    HoldService.settle(funded_owner.id, enforced_prepaid_tenant, None,
                       delta_micros=-100_000)
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 17_400_000


def test_release_fully_credits_back(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(5_000_000)])
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 15_000_000
    HoldService.release(funded_owner.id, enforced_prepaid_tenant, None, 5_000_000)
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 20_000_000


def test_settle_credits_back_run_cost_counter_unblocking_further_holds(
        enforced_prepaid_tenant, funded_owner):
    out1 = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                               [_item(400_000, run_id="r1", cap=500_000)])
    assert out1[0]["held"]
    out2 = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                               [_item(200_000, run_id="r1", cap=500_000)])
    assert out2[0]["rejected"]
    # Full credit-back of the first hold's estimate -> run-cost counter drops
    # back to 0, so a subsequent hold under the cap succeeds again.
    HoldService.settle(funded_owner.id, enforced_prepaid_tenant, "r1", delta_micros=400_000)
    out3 = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                               [_item(200_000, run_id="r1", cap=500_000)])
    assert out3[0]["held"]


def test_postpaid_incr_increases_spend_not_decreases(enforced_postpaid_tenant, postpaid_owner):
    """Regression pin for the sign-handling note in the task brief: the
    postpaid path must INCREASE the live spend counter by the estimate, never
    decrease it (a naive DECRBY-of-negative implementation that leaks its sign
    into the run-cap increment would get this backwards)."""
    out = HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(4_000_000)])
    assert out[0]["held"]
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 4_000_000
    HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(1_000_000)])
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) == 5_000_000


def test_postpaid_run_cap_uses_positive_estimate(enforced_postpaid_tenant, postpaid_owner):
    """The run-cap counter must accumulate the POSITIVE estimate even in
    postpaid mode — not the signed value used for the spend counter move."""
    out = HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant,
                              [_item(600_000, run_id="rp1", cap=500_000)])
    assert out[0]["rejected"] and out[0]["reason"] == "cost_limit_exceeded"
    assert LiveLedgerService.read_postpaid(postpaid_owner.id) is None


def test_postpaid_budget_crossing_sets_stop(enforced_postpaid_tenant, postpaid_owner):
    BudgetConfig.objects.create(tenant=enforced_postpaid_tenant, customer=postpaid_owner,
                                cap_micros=10_000_000, hard_stop_pct=100)
    out = HoldService.acquire(postpaid_owner.id, enforced_postpaid_tenant, [_item(12_000_000)])
    assert out[0]["held"] is True
    assert out[0]["stop"] is True
    assert out[0]["stop_scope"] == "customer"


def test_enforcement_off_is_noop_fail_open(funded_owner):
    off_tenant = Tenant.objects.create(name="Off", products=["metering", "billing"],
                                       billing_mode="prepaid", enforcement_mode="off")
    out = HoldService.acquire(funded_owner.id, off_tenant, [_item(999_000_000)])
    assert out[0]["held"] and not out[0]["rejected"] and not out[0]["stop"]
    assert LiveLedgerService.read_prepaid(funded_owner.id) is None


def test_fail_open_on_redis_error_holds_every_item(enforced_prepaid_tenant, funded_owner, monkeypatch):
    import apps.billing.gating.services.hold_service as hs_mod

    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(hs_mod, "_client", _boom)
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                              [_item(1_000_000), _item(2_000_000, run_id="r1", cap=1)])
    assert len(out) == 2
    assert all(o["held"] and not o["rejected"] and not o["stop"] for o in out)


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
