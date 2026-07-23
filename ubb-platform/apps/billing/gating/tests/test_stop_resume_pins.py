"""#39 acceptance pins — the hard-floor stop/resume pair across all lanes.

Spec pins (docs/plans/2026-07-15-one-rule-enforcement-spec.md §L):
  Pin 4  — the durable lane fires the stop at the CONFIGURED floor with Redis
           down; fast + durable lanes together fire exactly one stop per
           crossing (episode dedup), and suspension emission rides the same
           guard (no double-fire).
  Pin 5  — reconcile SETs a missed stop (not just clears a stale one).
  Pin 6  — resume fires at the exact re-cross via credit, reconcile, and the
           durable (Redis-blind credit fallback) paths — once per episode.
  Pin 11 — the zero-crossing balance-overage EARLY WARNING still fires at
           zero, distinct from the stop/resume pair.
"""
import uuid
from dataclasses import asdict

import pytest
from django.core.cache import cache

from apps.billing.gating.models import StopSignalState
from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.gating.services.stop_signal_service import StopSignalService
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import UsageRecorded
from apps.platform.tenants.models import Tenant

FLOOR = 5_000_000  # configured min balance: the stop line is -5_000_000


def _tenant(enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode="prepaid", enforcement_mode=enf)


def _customer(t, balance_micros=0):
    c = Customer.objects.create(tenant=t, external_id="c1")
    Wallet.objects.create(customer=c, balance_micros=balance_micros)
    CustomerBillingProfile.objects.create(customer=c, min_balance_micros=FLOOR)
    return c


def _payload(t, c, billed):
    return asdict(UsageRecorded(
        tenant_id=t.id, customer_id=c.id, billing_owner_id=c.id,
        event_id=str(uuid.uuid4()), cost_micros=billed))


def _drain(t, c, billed):
    handle_usage_recorded_billing(str(uuid.uuid4()), _payload(t, c, billed))


def _fired():
    return OutboxEvent.objects.filter(event_type="stop.fired").order_by("created_at")


def _cleared():
    return OutboxEvent.objects.filter(event_type="stop.cleared").order_by("created_at")


def _suspended_events():
    return OutboxEvent.objects.filter(event_type="billing.customer_suspended")


def _overage_events():
    return OutboxEvent.objects.filter(event_type="billing.balance_overage")


def _break_redis(monkeypatch):
    def _boom():
        raise ConnectionError("redis down")
    monkeypatch.setattr(
        "apps.billing.gating.services.live_counter._client", _boom)


@pytest.mark.django_db
class TestPin4DurableLane:
    def setup_method(self):
        cache.clear()

    def test_durable_lane_fires_at_configured_floor_with_redis_down(self, monkeypatch):
        _break_redis(monkeypatch)
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 6_000_000)  # 0 -> -6M crosses the -5M configured floor
        assert _fired().count() == 1
        payload = _fired().get().payload
        assert payload["episode_seq"] == 1
        assert payload["reason"] == "customer_wide_stop"
        row = StopSignalState.objects.get(owner=c, family="floor_stop")
        assert row.state == "stopped" and row.episode_seq == 1
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == "min_balance_exceeded"

    def test_durable_lane_watches_the_configured_floor_not_zero(self, monkeypatch):
        _break_redis(monkeypatch)
        t = _tenant()
        c = _customer(t, balance_micros=3_000_000)
        _drain(t, c, 6_000_000)  # 3M -> -3M: crosses ZERO, not the -5M floor
        assert _overage_events().count() == 1  # early warning at zero (Pin 11)
        assert _fired().count() == 0           # the stop waits for the floor
        _drain(t, c, 4_000_000)  # -3M -> -7M: crosses the configured floor
        assert _overage_events().count() == 1  # zero already crossed — no re-fire
        assert _fired().count() == 1

    def test_fast_and_durable_lanes_fire_exactly_one_stop_and_one_suspend(self):
        t = _tenant()
        c = _customer(t)
        # Fast lane sees the crossing at arrival (live counter seeds from the
        # durable balance, then debits past the floor) and wins the episode.
        out = LiveCounter.debit(c.id, t, 6_000_000)
        assert out["stop"] is True
        assert _fired().count() == 1
        # The durable drawdown handler then replays the same crossing on the
        # durable wallet — its transition loses: no second stop, no second
        # suspension (the suspension emission rides the same guard).
        _drain(t, c, 6_000_000)
        assert _fired().count() == 1
        assert _suspended_events().count() == 1
        assert StopSignalState.objects.get(owner=c, family="floor_stop").episode_seq == 1


@pytest.mark.django_db
class TestPin5ReconcileSetsAMissedStop:
    def setup_method(self):
        cache.clear()

    def test_reconcile_sets_a_missed_stop(self):
        t = _tenant()
        c = _customer(t, balance_micros=-6_000_000)  # already past the floor,
        # but no lane ever signaled it (blind window): no flag, no ledger row.
        LiveCounter.reconcile(c.id, t)
        assert _fired().count() == 1
        assert _fired().get().payload["episode_seq"] == 1
        assert LiveCounter.read(c.id, t)["stop"] is True  # flag re-aligned
        c.refresh_from_db()
        assert c.status == "suspended"

    def test_reconcile_sets_the_missed_stop_even_with_redis_down(self, monkeypatch):
        _break_redis(monkeypatch)
        t = _tenant()
        c = _customer(t, balance_micros=-6_000_000)
        LiveCounter.reconcile(c.id, t)
        assert _fired().count() == 1
        c.refresh_from_db()
        assert c.status == "suspended"

    def test_reconcile_is_idempotent_per_position(self):
        t = _tenant()
        c = _customer(t, balance_micros=-6_000_000)
        LiveCounter.reconcile(c.id, t)
        LiveCounter.reconcile(c.id, t)  # same position -> loses
        assert _fired().count() == 1


@pytest.mark.django_db
class TestPin6ResumeOncePerEpisode:
    def setup_method(self):
        cache.clear()

    def _open_episode(self, t, c):
        out = LiveCounter.debit(c.id, t, 6_000_000)
        assert out["stop"] is True
        assert _fired().count() == 1

    def test_credit_path_clears_at_the_exact_recross_once(self):
        t = _tenant()
        c = _customer(t)
        self._open_episode(t, c)  # live -6M
        # The durable top-up lands first (every credit site), then the hook.
        Wallet.objects.filter(customer=c).update(balance_micros=10_000_000)
        LiveCounter.credit(c.id, t, 10_000_000)  # live -> 4M ≥ -5M
        assert _cleared().count() == 1
        payload = _cleared().get().payload
        assert payload["episode_seq"] == 1
        assert payload["balance_micros"] == 4_000_000
        assert LiveCounter.read(c.id, t)["stop"] is False
        c.refresh_from_db()
        assert c.status == "active"  # durable balance recovered -> un-suspended
        LiveCounter.credit(c.id, t, 1_000_000)  # already cleared -> loses
        assert _cleared().count() == 1

    def test_a_credit_that_does_not_recross_does_not_clear(self):
        t = _tenant()
        c = _customer(t)
        self._open_episode(t, c)                      # live -6M
        LiveCounter.credit(c.id, t, 500_000)    # live -5.5M, still past floor
        assert _cleared().count() == 0
        assert LiveCounter.read(c.id, t)["stop"] is True

    def test_reconcile_path_clears_once(self):
        t = _tenant()
        c = _customer(t)
        self._open_episode(t, c)
        # The fast credit hook was lost (key expired / flushed): only the
        # durable wallet shows the recovery. Reconcile is the bottom line.
        cache.clear()  # drop the live counter — reconcile re-seeds from durable
        Wallet.objects.filter(customer=c).update(balance_micros=10_000_000)
        LiveCounter.reconcile(c.id, t)
        assert _cleared().count() == 1
        assert _cleared().get().payload["episode_seq"] == 1
        c.refresh_from_db()
        assert c.status == "active"
        LiveCounter.reconcile(c.id, t)  # already cleared -> loses
        assert _cleared().count() == 1

    def test_durable_path_clears_when_redis_is_blind(self, monkeypatch):
        t = _tenant()
        c = _customer(t)
        self._open_episode(t, c)
        Wallet.objects.filter(customer=c).update(balance_micros=10_000_000)
        _break_redis(monkeypatch)
        # The credit hook still fires from the durable credit site; with the
        # fast INCRBY blind, the DURABLE balance decides the re-cross — the
        # resume signals now, not an hour later at reconcile.
        LiveCounter.credit(c.id, t, 10_000_000)
        assert _cleared().count() == 1
        assert _cleared().get().payload["balance_micros"] == 10_000_000
        c.refresh_from_db()
        assert c.status == "active"

    def test_episodes_pair_up_across_a_full_cycle(self):
        t = _tenant()
        c = _customer(t)
        self._open_episode(t, c)                       # stop, episode 1
        Wallet.objects.filter(customer=c).update(balance_micros=10_000_000)
        LiveCounter.credit(c.id, t, 10_000_000)  # clear, episode 1 (live 4M)
        out = LiveCounter.debit(c.id, t, 12_000_000)  # live -8M
        assert out["stop"] is True                     # stop, episode 2
        assert [e.payload["episode_seq"] for e in _fired()] == [1, 2]
        assert [e.payload["episode_seq"] for e in _cleared()] == [1]


@pytest.mark.django_db
class TestPin11EarlyWarningUnaffected:
    def setup_method(self):
        cache.clear()

    def test_zero_crossing_fires_overage_without_a_stop(self):
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        _drain(t, c, 2_000_000)  # 1M -> -1M: zero crossed, floor (-5M) not
        assert _overage_events().count() == 1
        payload = _overage_events().get().payload
        assert payload["balance_micros"] == -1_000_000
        assert payload["overage_micros"] == 1_000_000
        assert _fired().count() == 0
        assert not StopSignalState.objects.filter(owner=c).exists()

    def test_enforcement_off_is_tier1_byte_for_byte(self):
        t = _tenant(enf="off")
        c = _customer(t)
        _drain(t, c, 6_000_000)  # crosses zero AND the floor
        assert _overage_events().count() == 1     # early warning unchanged
        assert _fired().count() == 0              # no signal suite when off
        assert not StopSignalState.objects.filter(owner=c).exists()
        c.refresh_from_db()
        assert c.status == "suspended"            # Tier-1 baseline suspension
        assert c.suspension_reason == "min_balance_exceeded"
        assert _suspended_events().count() == 1
