"""#40 acceptance pins — the soft floor: wind-down line (spec §F, Pin 12).

Pin 12 — crossing the soft line refuses a NEW TOP-LEVEL task start
(`soft_floor_reached`) while a subtask start under an active parent passes,
and usage events keep landing and billing; `soft_floor.crossed` /
`soft_floor.cleared` fire exactly once per crossing through the transition
guard; acks never change on a soft-floor crossing.

Plus the resolution rule: the soft line resolves customer override → tenant
default → None (no soft floor), and always sits AT OR ABOVE the hard floor's
line (the resolver clamps a misconfigured lower line up to the hard floor).

Since #44 the hourly patrol (the reconcile pass) also holds soft-family SET
power: a missed soft crossing is re-detected from durable truth within one
interval — late, never lost. Its re-mint rails are pinned in
test_patrol_pins.py.
"""
import uuid
from dataclasses import asdict

import pytest
from django.core.cache import cache

from apps.billing.gating.models import StopSignalState
from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.gating.services.stop_signal_service import StopSignalService
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.queries import get_billing_config, get_customer_soft_min_balance
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import UsageRecorded
from apps.platform.tenants.models import Tenant

HARD = 5_000_000  # hard floor: the stop line is -5_000_000
SOFT = 2_000_000  # soft floor: the wind-down line is -2_000_000


def _tenant(enf="enforcing", mode="prepaid"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


def _customer(t, balance_micros=0, hard=HARD, soft=SOFT):
    c = Customer.objects.create(tenant=t, external_id="c1")
    Wallet.objects.create(customer=c, balance_micros=balance_micros)
    CustomerBillingProfile.objects.create(customer=c, min_balance_micros=hard,
                                          soft_min_balance_micros=soft)
    return c


def _drain(t, c, billed):
    handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
        tenant_id=t.id, customer_id=c.id, billing_owner_id=c.id,
        event_id=str(uuid.uuid4()), cost_micros=billed)))


def _crossed():
    return OutboxEvent.objects.filter(event_type="soft_floor.crossed").order_by("created_at")


def _cleared():
    return OutboxEvent.objects.filter(event_type="soft_floor.cleared").order_by("created_at")


def _hard_fired():
    return OutboxEvent.objects.filter(event_type="stop.fired")


@pytest.mark.django_db
class TestSoftFloorResolution:
    def test_customer_override_wins(self):
        t = _tenant()
        c = _customer(t, soft=SOFT)
        cfg = get_billing_config(t.id)
        cfg.soft_min_balance_micros = 1_000_000
        cfg.save()
        assert get_customer_soft_min_balance(c.id, t.id) == SOFT

    def test_tenant_default_when_no_override(self):
        t = _tenant()
        c = _customer(t, soft=None)
        cfg = get_billing_config(t.id)
        cfg.soft_min_balance_micros = 1_000_000
        cfg.save()
        assert get_customer_soft_min_balance(c.id, t.id) == 1_000_000

    def test_none_when_unconfigured(self):
        t = _tenant()
        c = _customer(t, soft=None)
        assert get_customer_soft_min_balance(c.id, t.id) is None

    def test_resolution_clamps_to_at_or_above_the_hard_floor(self):
        # A soft value ABOVE the hard's would place the wind-down line BELOW
        # the stop line (-8M < -5M) — the resolver clamps it up to the hard
        # floor so the invariant holds even for stale/cross-level configs.
        t = _tenant()
        c = _customer(t, hard=HARD, soft=8_000_000)
        assert get_customer_soft_min_balance(c.id, t.id) == HARD

    def test_negative_value_places_the_line_above_zero(self):
        # The wind-down-with-money-left case: soft=-2M is the line at +2M.
        t = _tenant()
        c = _customer(t, hard=0, soft=-2_000_000)
        assert get_customer_soft_min_balance(c.id, t.id) == -2_000_000


@pytest.mark.django_db
class TestPin12StartGate:
    def setup_method(self):
        cache.clear()

    def test_crossing_refuses_a_new_top_level_task_start(self):
        t = _tenant()
        c = _customer(t, balance_micros=-3_000_000)  # past soft (-2M), above hard (-5M)
        out = RiskService.check(c, create_task=True)
        assert out["allowed"] is False
        assert out["reason"] == "soft_floor_reached"
        assert out["task_id"] is None

    def test_plain_pre_check_is_also_refused(self):
        # pre_check IS the start-gate (the poll asks "may new work start").
        t = _tenant()
        c = _customer(t, balance_micros=-3_000_000)
        out = RiskService.check(c)
        assert out["allowed"] is False
        assert out["reason"] == "soft_floor_reached"

    def test_subtask_start_under_an_active_parent_passes(self):
        t = _tenant()
        c = _customer(t, balance_micros=0)
        parent = RiskService.check(c, create_task=True)
        assert parent["allowed"] is True
        Wallet.objects.filter(customer=c).update(balance_micros=-3_000_000)
        # A contained child of running work is running work completing —
        # explicitly permitted past the soft line.
        child = RiskService.check(c, create_task=True,
                                  parent_task_id=parent["task_id"])
        assert child["allowed"] is True
        assert child["task_id"] is not None
        # ...while a sibling TOP-LEVEL start stays refused.
        top = RiskService.check(c, create_task=True)
        assert top["allowed"] is False and top["reason"] == "soft_floor_reached"

    def test_hard_floor_wins_below_both_lines(self):
        t = _tenant()
        c = _customer(t, balance_micros=-6_000_000)
        out = RiskService.check(c, create_task=True)
        assert out["allowed"] is False
        assert out["reason"] == "insufficient_funds"

    def test_above_the_soft_line_passes(self):
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        assert RiskService.check(c, create_task=True)["allowed"] is True

    def test_no_soft_floor_configured_never_refuses(self):
        t = _tenant()
        c = _customer(t, balance_micros=-3_000_000, soft=None)
        assert RiskService.check(c, create_task=True)["allowed"] is True

    def test_positive_balance_can_still_be_past_a_raised_soft_line(self):
        # soft=-2M puts the wind-down line at +2M: a customer with money
        # left is refused new starts while running work completes.
        t = _tenant()
        c = _customer(t, balance_micros=1_500_000, hard=0, soft=-2_000_000)
        out = RiskService.check(c, create_task=True)
        assert out["allowed"] is False
        assert out["reason"] == "soft_floor_reached"

    def test_enforcement_off_never_refuses(self):
        t = _tenant(enf="off")
        c = _customer(t, balance_micros=-3_000_000)
        assert RiskService.check(c, create_task=True)["allowed"] is True

    def test_postpaid_has_no_soft_floor(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        cfg = get_billing_config(t.id)
        cfg.soft_min_balance_micros = -1_000_000  # line at +1M; balance reads 0
        cfg.save()
        assert RiskService.check(c, create_task=True)["allowed"] is True


@pytest.mark.django_db
class TestPin12PairExactlyOnce:
    def setup_method(self):
        cache.clear()

    def test_durable_crossing_emits_soft_floor_crossed_once(self):
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 3_000_000)  # 0 -> -3M crosses the soft line (-2M) only
        assert _crossed().count() == 1
        payload = _crossed().get().payload
        assert payload["episode_seq"] == 1
        assert payload["balance_micros"] == -3_000_000
        assert payload["soft_min_balance_micros"] == SOFT
        assert payload["owner_id"] == str(c.id)
        row = StopSignalState.objects.get(owner=c, family="soft_floor")
        assert row.state == "stopped" and row.episode_seq == 1
        # Never a stop, never a suspension: the hard floor did not cross.
        assert _hard_fired().count() == 0
        c.refresh_from_db()
        assert c.status == "active"

    def test_events_keep_landing_and_billing_past_the_soft_line(self):
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 3_000_000)   # crosses the soft line
        _drain(t, c, 1_000_000)   # -3M -> -4M: still landing, still billing
        w = Wallet.objects.get(customer=c)
        assert w.balance_micros == -4_000_000
        assert w.transactions.filter(transaction_type="USAGE_DEDUCTION").count() == 2
        # The edge already crossed — no re-fire, no second episode.
        assert _crossed().count() == 1

    def test_acks_never_change_on_a_soft_crossing(self):
        t = _tenant()
        c = _customer(t)
        # The sync fast lane debits straight past the soft line: the ack's
        # stop verdict must not change (stop=true keeps meaning exactly one
        # thing), and NO fast-lane soft signal exists — signal latency is
        # outbox latency (the durable drawdown handler), by design.
        out = LiveCounter.debit(c.id, t, 3_000_000)
        assert out["stop"] is False
        assert LiveCounter.read(c.id, t)["stop"] is False
        assert _crossed().count() == 0  # no second Redis threshold, no fast lane

    def test_a_replayed_transition_loses(self):
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 3_000_000)
        assert StopSignalService.drive_soft_crossed(
            c.id, t, balance_micros=-3_000_000, soft_min_balance_micros=SOFT) is None
        assert _crossed().count() == 1

    def test_hard_and_soft_families_fire_independently_on_one_event(self):
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 6_000_000)  # 0 -> -6M crosses BOTH lines at once
        assert _crossed().count() == 1
        assert _hard_fired().count() == 1
        assert StopSignalState.objects.get(owner=c, family="soft_floor").episode_seq == 1
        assert StopSignalState.objects.get(owner=c, family="floor_stop").episode_seq == 1

    def test_credit_clears_at_the_exact_recross_once(self):
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 3_000_000)                      # crossed, episode 1
        # The durable top-up lands first (every credit site), then the hook.
        Wallet.objects.filter(customer=c).update(balance_micros=-2_000_000)
        LiveCounter.credit(c.id, t, 1_000_000)  # -2M >= -2M: AT the line
        assert _cleared().count() == 1
        payload = _cleared().get().payload
        assert payload["episode_seq"] == 1
        assert payload["reason"] == "balance_recovered"
        assert payload["balance_micros"] == -2_000_000
        LiveCounter.credit(c.id, t, 1_000_000)  # already cleared -> loses
        assert _cleared().count() == 1

    def test_a_credit_that_does_not_recross_does_not_clear(self):
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 3_000_000)
        Wallet.objects.filter(customer=c).update(balance_micros=-2_500_000)
        LiveCounter.credit(c.id, t, 500_000)   # -2.5M still past -2M
        assert _cleared().count() == 0

    def test_reconcile_clears_a_stale_soft_crossing(self):
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 3_000_000)
        # The credit hook was lost: only the durable wallet shows recovery.
        Wallet.objects.filter(customer=c).update(balance_micros=0)
        cache.clear()
        LiveCounter.reconcile(c.id, t)
        assert _cleared().count() == 1
        assert _cleared().get().payload["reason"] == "reconciled"
        LiveCounter.reconcile(c.id, t)  # same position -> loses
        assert _cleared().count() == 1

    def test_reconcile_sets_a_missed_soft_crossing(self):
        # #44 (delivery spec §C.1): the patrol — the hourly reconcile pass —
        # gained soft-family SET power. A crossing whose detection was torn
        # down is re-driven from durable truth within one interval.
        t = _tenant()
        c = _customer(t, balance_micros=-3_000_000)  # past soft, never signaled
        LiveCounter.reconcile(c.id, t)
        assert _crossed().count() == 1
        assert _crossed().get().payload["episode_seq"] == 1
        assert _cleared().count() == 0
        LiveCounter.reconcile(c.id, t)  # same position -> loses
        assert _crossed().count() == 1

    def test_episodes_pair_up_across_a_full_cycle(self):
        t = _tenant()
        c = _customer(t)
        _drain(t, c, 3_000_000)                      # crossed, episode 1
        Wallet.objects.filter(customer=c).update(balance_micros=0)
        LiveCounter.credit(c.id, t, 3_000_000)  # cleared, episode 1
        _drain(t, c, 3_000_000)                      # crossed, episode 2
        assert [e.payload["episode_seq"] for e in _crossed()] == [1, 2]
        assert [e.payload["episode_seq"] for e in _cleared()] == [1]

    def test_enforcement_off_emits_nothing(self):
        t = _tenant(enf="off")
        c = _customer(t)
        _drain(t, c, 3_000_000)
        assert _crossed().count() == 0
        assert not StopSignalState.objects.filter(owner=c).exists()
