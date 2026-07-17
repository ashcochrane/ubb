"""#45 acceptance pins — upward live-balance repair (delivery spec §D).

The honesty repair: an orphaned hold (acquired, then its RawIngestEvent row
rolled back with a crashed request) wedges the prepaid live counter below
reality — false stops that the downward-only MIN-merge can never heal. The
patrol's repair leg measures expected = durable − Σ(genuinely pending holds)
from one consistent DB snapshot, then reads the live counter; a deficit past
the de-minimis writes a candidate on pass one and, if the immediately-next
pass still measures one, applies min(d1, d2) as a relative increment — never
an absolute SET — with a complete audit row. A repair that lifts a wedged
stop drives the clearing transition through the same guard as every other
clearing.

Pin 7  — injected orphan deficit: candidate (no counter change) on pass one,
         min(d1,d2) relative-increment repair with a complete audit row on
         pass two, correct under concurrent traffic; a repair that lifts a
         wedged stop fires stop.cleared exactly once.
Pin 8  — a transient deficit that resolves between passes lapses (no repair);
         a sub-de-minimis deficit never candidates; a stale candidate can't
         prove hour-stability and starts the observation over.
Pin 10 — downward neighbors untouched: genuinely pending holds are not a
         deficit; a drift-high counter is the MIN-merge's lane, never the
         repair's.
Pin 11 — the repair-rate spike alert (count / amount per tenant per 24h)
         fires CRITICAL past its threshold.
Plus   — outcomes ride the hourly patrol beat onto the ops surface; postpaid
         and off tenants are out of scope.
"""
import logging
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing.gating import repair
from apps.billing.gating.models import LiveBalanceRepair
from apps.billing.gating.services.live_ledger_service import (
    LiveLedgerService,
    _client,
    _livebal_key,
)
from apps.billing.gating.services.stop_signal_service import (
    CLEAR_BALANCE_REPAIRED,
    StopSignalService,
)
from apps.billing.gating.tasks import reconcile_live_ledgers
from apps.billing.queries import get_patrol_stats
from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import RawIngestEvent
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


def _tenant(enf="enforcing", mode="prepaid"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


def _customer(t, balance_micros=0, ext="c1"):
    c = Customer.objects.create(tenant=t, external_id=ext)
    Wallet.objects.create(customer=c, balance_micros=balance_micros)
    return c


def _set_live(owner_id, value):
    _client().set(_livebal_key(owner_id), int(value))


def _live(owner_id):
    return LiveLedgerService.read_prepaid(owner_id)


def _events(event_type):
    return OutboxEvent.objects.filter(event_type=event_type).order_by("created_at")


def _pending_row(t, c, estimate, held=True, status="pending", key="k1"):
    return RawIngestEvent.objects.create(
        tenant=t, customer=c, billing_owner_id=c.id, idempotency_key=key,
        estimate_micros=estimate, estimate_exact=True, held=held, status=status)


NO_OUTCOMES = {"repaired": 0, "repaired_micros": 0, "repair_lapsed": 0}


@pytest.mark.django_db
class TestPin7TwoPassRepair:
    def test_pass_one_candidates_pass_two_repairs_with_full_audit(self):
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)  # a 6M orphan: hold taken, row rolled back

        counts = repair.repair_live_balances(t)
        assert counts == NO_OUTCOMES
        row = LiveBalanceRepair.objects.get(owner=c)
        assert row.status == "candidate"
        assert row.first_deficit_micros == 6_000_000
        assert row.durable_balance_micros == 10_000_000
        assert row.pending_hold_micros == 0
        assert row.second_deficit_micros is None
        assert row.applied_micros is None
        assert row.resolved_at is None
        assert _live(c.id) == 4_000_000  # pass one changes nothing

        counts = repair.repair_live_balances(t)
        assert counts == {"repaired": 1, "repaired_micros": 6_000_000,
                          "repair_lapsed": 0}
        row.refresh_from_db()
        assert row.status == "repaired"
        assert row.second_deficit_micros == 6_000_000
        assert row.applied_micros == 6_000_000
        assert row.live_before_micros == 4_000_000
        assert row.live_after_micros == 10_000_000
        assert row.resolved_at is not None
        assert _live(c.id) == 10_000_000

        # A third pass finds an honest counter: nothing new.
        assert repair.repair_live_balances(t) == NO_OUTCOMES
        assert LiveBalanceRepair.objects.filter(owner=c).count() == 1

    def test_relative_increment_is_correct_under_concurrent_traffic(self):
        # Honest traffic between the passes debits BOTH the durable wallet
        # and the live counter by 1M: the deficit is unchanged (6M) and the
        # INCRBY lands the counter exactly on the durable balance. An
        # absolute SET to pass-one's expected (10M) would erase the debit.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)

        Wallet.objects.filter(customer=c).update(balance_micros=9_000_000)
        _client().decrby(_livebal_key(c.id), 1_000_000)

        counts = repair.repair_live_balances(t)
        assert counts["repaired_micros"] == 6_000_000
        assert _live(c.id) == 9_000_000  # honest: durable, not pass-one's 10M

    def test_min_takes_the_second_measurement_when_the_deficit_shrank(self):
        # Part of the wedge healed between passes (a late settle credited 2M
        # back): d2 = 4M < d1 = 6M -> only min is applied, counter lands
        # honest, never above the durable balance.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        _client().incrby(_livebal_key(c.id), 2_000_000)

        counts = repair.repair_live_balances(t)
        row = LiveBalanceRepair.objects.get(owner=c)
        assert row.applied_micros == 4_000_000
        assert counts["repaired_micros"] == 4_000_000
        assert _live(c.id) == 10_000_000

    def test_min_takes_the_first_measurement_when_the_deficit_grew(self):
        # A NEW orphan (3M) accrued during the hour: d2 = 9M > d1 = 6M ->
        # only the hour-stable 6M is applied; the residual candidates on the
        # following pass and repairs one cycle later.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        _client().decrby(_livebal_key(c.id), 3_000_000)

        counts = repair.repair_live_balances(t)
        assert counts["repaired_micros"] == 6_000_000
        assert _live(c.id) == 7_000_000

        repair.repair_live_balances(t)  # third pass: the residual candidates
        fresh = LiveBalanceRepair.objects.get(owner=c, status="candidate")
        assert fresh.first_deficit_micros == 3_000_000

    def test_repair_that_lifts_a_wedged_stop_fires_stop_cleared_exactly_once(self):
        t = _tenant()
        c = _customer(t, balance_micros=5_000_000)  # durably healthy (floor 0)
        _set_live(c.id, -1_000_000)  # wedged below the floor by a 6M orphan
        # The wedge's false crossing stopped + suspended the owner durably.
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        LiveLedgerService.ensure_stop_flag(c.id, "customer_wide_stop")
        c.refresh_from_db()
        assert c.status == "suspended"

        repair.repair_live_balances(t)  # pass one: candidate only
        assert not _events("stop.cleared").exists()
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is True

        repair.repair_live_balances(t)  # pass two: +6M -> 5M, wedge lifted
        assert _live(c.id) == 5_000_000
        cleared = _events("stop.cleared")
        assert cleared.count() == 1
        assert cleared.get().payload["episode_seq"] == 1
        assert cleared.get().payload["reason"] == CLEAR_BALANCE_REPAIRED
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is False
        c.refresh_from_db()
        assert c.status == "active"  # durable balance is healthy -> unsuspended

        # Exactly once: the reconcile bottom line and further patrol passes
        # find the episode already closed.
        LiveLedgerService.reconcile_prepaid(c.id, t)
        repair.repair_live_balances(t)
        assert _events("stop.cleared").count() == 1

    def test_repair_that_leaves_the_counter_past_the_floor_does_not_clear(self):
        # The owner is GENUINELY past the floor (-2M durable); only the 1M
        # orphan on top is repaired, and the stop stays.
        t = _tenant()
        c = _customer(t, balance_micros=-2_000_000)
        _set_live(c.id, -3_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")

        repair.repair_live_balances(t)
        repair.repair_live_balances(t)
        assert _live(c.id) == -2_000_000
        row = LiveBalanceRepair.objects.get(owner=c)
        assert row.status == "repaired"
        assert row.applied_micros == 1_000_000
        assert not _events("stop.cleared").exists()
        c.refresh_from_db()
        assert c.status == "suspended"


@pytest.mark.django_db
class TestPin8TransientAndDeMinimis:
    def test_transient_deficit_lapses_without_repair(self):
        # A settle backlog: pass one saw the holds' debits before their rows
        # (or their credits) landed; by pass two the deficit drained.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        _client().incrby(_livebal_key(c.id), 6_000_000)

        counts = repair.repair_live_balances(t)
        assert counts == {"repaired": 0, "repaired_micros": 0,
                          "repair_lapsed": 1}
        row = LiveBalanceRepair.objects.get(owner=c)
        assert row.status == "lapsed"
        assert row.second_deficit_micros == 0
        assert row.applied_micros is None
        assert row.resolved_at is not None
        assert _live(c.id) == 10_000_000  # untouched by the repair

    def test_sub_de_minimis_deficit_never_candidates(self):
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 10_000_000 - repair.REPAIR_DE_MINIMIS_MICROS + 1)
        assert repair.repair_live_balances(t) == NO_OUTCOMES
        assert not LiveBalanceRepair.objects.exists()

    def test_stale_candidate_lapses_and_the_observation_starts_over(self):
        # The immediately-next-pass guard: a candidate older than the
        # freshness window (a skipped beat, downtime) can't prove the deficit
        # was stable for the full hour — it lapses unconfirmed and a fresh
        # candidate restarts the observation. No repair this pass.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        LiveBalanceRepair.objects.update(
            created_at=timezone.now() - timedelta(hours=3))

        counts = repair.repair_live_balances(t)
        assert counts == {"repaired": 0, "repaired_micros": 0,
                          "repair_lapsed": 1}
        assert _live(c.id) == 4_000_000
        stale = LiveBalanceRepair.objects.get(status="lapsed")
        assert stale.second_deficit_micros is None  # never confirmed in time
        fresh = LiveBalanceRepair.objects.get(status="candidate")
        assert fresh.first_deficit_micros == 6_000_000


@pytest.mark.django_db
class TestPin10DownwardNeighborsUntouched:
    def test_genuinely_pending_holds_are_not_a_deficit(self):
        # live == durable − pending: the counter is honest. Neither the
        # MIN-merge (target = durable; only lowers) nor the repair moves it.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _pending_row(t, c, 3_000_000)
        _set_live(c.id, 7_000_000)

        LiveLedgerService.reconcile_prepaid(c.id, t)
        assert repair.repair_live_balances(t) == NO_OUTCOMES
        assert _live(c.id) == 7_000_000
        assert not LiveBalanceRepair.objects.exists()

    def test_only_genuinely_pending_held_rows_count(self):
        # Settled/duplicate/failed rows have drained (or released) their
        # holds; a held=False append never took one. None of them may shrink
        # the expected balance.
        from apps.metering.queries import get_pending_held_estimate_total
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _pending_row(t, c, 3_000_000, key="p1")
        _pending_row(t, c, 1_000_000, status="settled", key="p2")
        _pending_row(t, c, 1_000_000, status="duplicate", key="p3")
        _pending_row(t, c, 1_000_000, status="failed", key="p4")
        _pending_row(t, c, 1_000_000, held=False, key="p5")
        assert get_pending_held_estimate_total(t.id, c.id) == 3_000_000

    def test_drift_high_counter_is_the_min_merges_lane_never_a_candidate(self):
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 15_000_000)
        assert repair.repair_live_balances(t) == NO_OUTCOMES
        assert not LiveBalanceRepair.objects.exists()
        LiveLedgerService.reconcile_prepaid(c.id, t)  # downward: byte-identical
        assert _live(c.id) == 10_000_000

    def test_absent_counter_is_never_repaired(self):
        # No live key -> nothing to repair (first use seeds from durable).
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        assert repair.repair_live_balances(t) == NO_OUTCOMES
        assert not LiveBalanceRepair.objects.exists()
        assert _live(c.id) is None


@pytest.mark.django_db
class TestPin11RepairSpikeAlert:
    def test_spike_past_the_count_threshold_alerts_critical(self, caplog,
                                                            monkeypatch):
        monkeypatch.setattr(repair, "REPAIR_SPIKE_COUNT_24H", 2)
        t = _tenant()
        for ext in ("c1", "c2"):
            c = _customer(t, balance_micros=10_000_000, ext=ext)
            _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)  # candidates
        with caplog.at_level(logging.CRITICAL, logger="ubb.billing"):
            repair.repair_live_balances(t)  # two repairs -> spike
        spikes = [r for r in caplog.records
                  if r.msg == "live_balance.repair_spike"]
        assert len(spikes) == 1
        assert spikes[0].levelno == logging.CRITICAL
        assert spikes[0].data["repairs_24h"] == 2
        assert spikes[0].data["amount_micros_24h"] == 12_000_000

    def test_spike_past_the_amount_threshold_alerts_critical(self, caplog,
                                                             monkeypatch):
        monkeypatch.setattr(repair, "REPAIR_SPIKE_AMOUNT_MICROS_24H",
                            5_000_000)
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        with caplog.at_level(logging.CRITICAL, logger="ubb.billing"):
            repair.repair_live_balances(t)  # one 6M repair -> amount spike
        assert any(r.msg == "live_balance.repair_spike"
                   for r in caplog.records)

    def test_below_threshold_stays_quiet(self, caplog):
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        with caplog.at_level(logging.CRITICAL, logger="ubb.billing"):
            repair.repair_live_balances(t)
        assert not any(r.msg == "live_balance.repair_spike"
                       for r in caplog.records)


@pytest.mark.django_db
class TestRepairRidesThePatrol:
    def test_outcomes_ride_the_beat_and_the_ops_surface(self):
        t = _tenant()
        a = _customer(t, balance_micros=10_000_000, ext="a")  # will repair
        _set_live(a.id, 4_000_000)
        b = _customer(t, balance_micros=8_000_000, ext="b")   # will lapse
        _set_live(b.id, 5_000_000)

        reconcile_live_ledgers()  # pass one: two candidates
        _client().incrby(_livebal_key(b.id), 3_000_000)  # b's deficit drains
        reconcile_live_ledgers()  # pass two: repair a, lapse b

        stats = get_patrol_stats(tenant_id=t.id)
        assert stats["patrol_repaired_7d"] == 1
        assert stats["patrol_repaired_micros_7d"] == 6_000_000
        assert stats["patrol_repair_lapsed_7d"] == 1
        assert _live(a.id) == 10_000_000
        assert _live(b.id) == 8_000_000

    def test_postpaid_tenants_are_out_of_scope(self):
        # The postpaid spend counter's drift lane is the MAX-merge +
        # budget reconcile; the repair exists only where holds exist.
        t = _tenant(mode="postpaid")
        assert repair.repair_live_balances(t) == NO_OUTCOMES

    def test_off_tenants_never_repair(self):
        # The beat never reaches an off tenant; the direct call is guarded
        # too (mode off = the whole signal suite is byte-for-byte a no-op).
        t = _tenant(enf="off")
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        assert repair.repair_live_balances(t) == NO_OUTCOMES
        assert not LiveBalanceRepair.objects.exists()
