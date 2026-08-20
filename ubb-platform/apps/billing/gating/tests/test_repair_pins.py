"""#45 acceptance pins — upward live-balance repair (delivery spec §D).

RULING A2 (#233, slice 1 / #192), quoted: "the drift CAN occur on the surviving
path... The repair's stated cause is therefore incomplete: the reservation is
one cause, not the cause."

The honesty repair: a crashed SYNCHRONOUS recording request — its live-counter
debit issued after the event row's savepoint but inside the still-open
recording transaction — wedges the prepaid live counter below reality: false
stops that the downward-only MIN-merge can never heal. The patrol's repair leg
measures expected = the durable balance from one consistent DB snapshot, then
reads the live counter; a deficit past the de-minimis writes a candidate on
pass one and, if the immediately-next pass still measures one, applies
min(d1, d2) as a relative increment — never an absolute SET — with a complete
audit row. A repair that lifts a wedged stop drives the clearing transition
through the same guard as every other clearing.

WHERE THE DEFICIT COMES FROM, and why not every pin below strands one the same
way. The pins whose subject is the deficit's PROVENANCE drive the surviving
path for real: a request over HTTP to ``POST /api/v1/metering/usage`` with the
outbox insert failing, which is the last DB write after the debit. The pins
whose subject is the repair's ARITHMETIC (min-of-two, the freshness guard, the
spike thresholds) still move the counter directly — they need a SECOND
measurement of an exact size, and a second crashed request cannot give one
without also asserting what the recording path does, which is
``api/v1/tests/test_recording_drift_pins.py``'s subject, not this module's.

Pin 7  — a strand left by the surviving path: candidate (no counter change) on
         pass one, min(d1,d2) relative-increment repair with a complete audit
         row on pass two, correct under concurrent traffic; a repair that lifts
         a wedged stop fires stop.cleared exactly once.
Pin 8  — a transient deficit that resolves between passes lapses (no repair);
         a sub-de-minimis deficit never candidates; a stale candidate can't
         prove hour-stability and starts the observation over.
Pin 10 — downward neighbors untouched: a drift-HIGH counter is the MIN-merge's
         lane, never the repair's; an absent counter is never repaired; and the
         measurement is the durable balance alone — the reservation term the
         repair was born with is gone with its cause.
Pin 11 — the repair-rate spike alert (count / amount per tenant per 24h)
         fires CRITICAL past its threshold.
Plus   — outcomes ride the hourly patrol beat onto the ops surface; postpaid
         and off tenants are out of scope.
"""
import ast
import json
import logging
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.test import Client
from django.utils import timezone

from api.v1.schemas import RecordUsageRequest
from apps.billing.gating import repair
from apps.billing.gating.models import LiveBalanceRepair
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.billing.gating.services.stop_signal_service import (
    CLEAR_BALANCE_REPAIRED,
    StopSignalService,
)
from apps.billing.gating.tasks import reconcile_live_ledgers
from apps.billing.queries import get_patrol_stats
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant, TenantApiKey


def _tenant(enf="enforcing", mode="prepaid"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


def _tenant_with_key(enf="enforcing", mode="prepaid"):
    """A tenant that can be driven over the wire — the seam the strand needs."""
    t = _tenant(enf=enf, mode=mode)
    _key, raw_key = TenantApiKey.create_key(t, label="t")
    return t, raw_key


def _customer(t, balance_micros=0, ext="c1"):
    c = Customer.objects.create(tenant=t, external_id=ext)
    Wallet.objects.create(customer=c, balance_micros=balance_micros)
    return c


def _set_live(owner_id, value):
    Door.set_balance(owner_id, int(value))


def _live(owner_id):
    return Door.balance(owner_id)


def _events(event_type):
    return OutboxEvent.objects.filter(event_type=event_type).order_by("created_at")


def _correlation_values():
    """Every required plain-string field on the recording request, each given a
    unique value.

    Read off the schema rather than spelled out. One of them is a retired term
    whose migration a later slice owes, and the ledger that owes it only ever
    shrinks — naming it here would grow that term's recorded extent instead.
    """
    return {name: f"{name}-{uuid.uuid4()}"
            for name, field in RecordUsageRequest.model_fields.items()
            if field.is_required() and field.annotation is str}


def _strand_via_the_recording_path(raw_key, customer, billed_micros):
    """Strand ``billed_micros`` on the live counter the way the SURVIVING path
    strands it — a real request whose event row rolls back after the debit.

    The injected failure is the outbox insert: the last DB write the recording
    core performs after the live-counter debit and before the transaction
    commits, so the event row rolls back from a state where the counter has
    already moved. Mechanism and ruling: ``test_recording_drift_pins.py``.
    """
    durable_before = Wallet.objects.get(customer=customer).balance_micros
    events_before = Posting.objects.count()
    declares_a_caller_supplied_cost(customer.tenant, DECLARED)
    # What the stranded request would have billed is configured now (#365).
    a_rule_that_prices_what_it_measures(customer.tenant)
    payload = {"customer_id": str(customer.id),
               "provider_cost_micros": 10_000_000,
               "event_type": DECLARED,
               "measurements": priced_at(int(billed_micros)),
               **_correlation_values()}
    with patch("apps.metering.usage.services.usage_service.write_event",
               side_effect=IntegrityError("outbox insert failed")):
        resp = Client().post(
            "/api/v1/metering/usage", data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")
    # The three properties that make this a strand rather than a spend.
    assert resp.status_code == 500
    assert Posting.objects.count() == events_before
    assert Wallet.objects.get(customer=customer).balance_micros == durable_before


NO_OUTCOMES = {"repaired": 0, "repaired_micros": 0, "repair_lapsed": 0}


@pytest.mark.django_db
class TestPin7TwoPassRepair:
    def test_pass_one_candidates_pass_two_repairs_with_full_audit(self):
        t, raw_key = _tenant_with_key()
        c = _customer(t, balance_micros=10_000_000)
        # A real 6M strand: the debit landed, the event row rolled back.
        _strand_via_the_recording_path(raw_key, c, 6_000_000)
        assert _live(c.id) == 4_000_000

        counts = repair.repair_live_balances(t)
        assert counts == NO_OUTCOMES
        row = LiveBalanceRepair.objects.get(owner=c)
        assert row.status == "candidate"
        assert row.first_deficit_micros == 6_000_000
        assert row.durable_balance_micros == 10_000_000
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
        Door.incr_balance(c.id, -1_000_000)

        counts = repair.repair_live_balances(t)
        assert counts["repaired_micros"] == 6_000_000
        assert _live(c.id) == 9_000_000  # honest: durable, not pass-one's 10M

    def test_min_takes_the_second_measurement_when_the_deficit_shrank(self):
        # Part of the wedge healed between passes (an operator credit put 2M
        # back): d2 = 4M < d1 = 6M -> only min is applied, counter lands
        # honest, never above the durable balance.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        Door.incr_balance(c.id, 2_000_000)

        counts = repair.repair_live_balances(t)
        row = LiveBalanceRepair.objects.get(owner=c)
        assert row.applied_micros == 4_000_000
        assert counts["repaired_micros"] == 4_000_000
        assert _live(c.id) == 10_000_000

    def test_min_takes_the_first_measurement_when_the_deficit_grew(self):
        # A SECOND crashed request stranded another 3M during the hour:
        # d2 = 9M > d1 = 6M -> only the hour-stable 6M is applied; the
        # residual candidates on the following pass and repairs one cycle
        # later.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        Door.incr_balance(c.id, -3_000_000)

        counts = repair.repair_live_balances(t)
        assert counts["repaired_micros"] == 6_000_000
        assert _live(c.id) == 7_000_000

        repair.repair_live_balances(t)  # third pass: the residual candidates
        fresh = LiveBalanceRepair.objects.get(owner=c, status="candidate")
        assert fresh.first_deficit_micros == 3_000_000

    def test_repair_that_lifts_a_wedged_stop_fires_stop_cleared_exactly_once(self):
        t, raw_key = _tenant_with_key()
        c = _customer(t, balance_micros=5_000_000)  # durably healthy (floor 0)
        # A real 6M strand takes the counter past the floor on a wallet that
        # never moved: the false crossing the repair exists to undo.
        _strand_via_the_recording_path(raw_key, c, 6_000_000)
        assert _live(c.id) == -1_000_000
        # The crossing's own durable transition rolled back with the request
        # that raised it; the durable lane records the wedge on its next pass
        # (patrol job 1 — the missed-transition drive), and from here on the
        # owner is stopped and suspended off a balance that is a fiction.
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        LiveCounter.ensure_stop_flag(c.id, "customer_wide_stop")
        c.refresh_from_db()
        assert c.status == "suspended"

        repair.repair_live_balances(t)  # pass one: candidate only
        assert not _events("stop.cleared").exists()
        assert LiveCounter.read(c.id, t)["stop"] is True

        repair.repair_live_balances(t)  # pass two: +6M -> 5M, wedge lifted
        assert _live(c.id) == 5_000_000
        cleared = _events("stop.cleared")
        assert cleared.count() == 1
        assert cleared.get().payload["episode_seq"] == 1
        assert cleared.get().payload["reason"] == CLEAR_BALANCE_REPAIRED
        assert LiveCounter.read(c.id, t)["stop"] is False
        c.refresh_from_db()
        assert c.status == "active"  # durable balance is healthy -> unsuspended

        # Exactly once: the reconcile bottom line and further patrol passes
        # find the episode already closed.
        LiveCounter.reconcile(c.id, t)
        repair.repair_live_balances(t)
        assert _events("stop.cleared").count() == 1

    def test_repair_that_leaves_the_counter_past_the_floor_does_not_clear(self):
        # The owner is GENUINELY past the floor (-2M durable); only the 1M
        # strand on top is repaired, and the stop stays.
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
        # A measurement taken mid-request: pass one saw a debit whose own
        # transaction had not yet committed, and by pass two it had (or was
        # credited back). The deficit drained; nothing is repaired.
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 4_000_000)
        repair.repair_live_balances(t)
        Door.incr_balance(c.id, 6_000_000)

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
    def test_the_measurement_is_the_durable_balance_alone(self):
        """The narrowed measurement (Ruling A2), pinned at its seam.

        The repair was born measuring ``durable − Σ(pending reservations)``,
        because the cause it was written for held one. The surviving cause
        holds nothing, so the reservation term goes with it and expected IS the
        durable balance. Read off the module's imports because that is where
        the term lived: the measurement reached across a product boundary into
        metering's read contract for it, and now reaches nowhere.
        """
        source = Path(repair.__file__).read_text(encoding="utf-8")
        reached_into = sorted({
            node.module for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("apps.metering")})
        assert reached_into == [], (
            "the repair's measurement is the durable balance alone; it should "
            f"read nothing from metering, but reads {reached_into}")

    def test_drift_high_counter_is_the_min_merges_lane_never_a_candidate(self):
        t = _tenant()
        c = _customer(t, balance_micros=10_000_000)
        _set_live(c.id, 15_000_000)
        assert repair.repair_live_balances(t) == NO_OUTCOMES
        assert not LiveBalanceRepair.objects.exists()
        LiveCounter.reconcile(c.id, t)  # downward: byte-identical
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
        Door.incr_balance(b.id, 3_000_000)  # b's deficit drains
        reconcile_live_ledgers()  # pass two: repair a, lapse b

        stats = get_patrol_stats(tenant_id=t.id)
        assert stats["patrol_repaired_7d"] == 1
        assert stats["patrol_repaired_micros_7d"] == 6_000_000
        assert stats["patrol_repair_lapsed_7d"] == 1
        assert _live(a.id) == 10_000_000
        assert _live(b.id) == 8_000_000

    def test_postpaid_tenants_are_out_of_scope(self):
        # The postpaid spend counter's drift lane is the MAX-merge + budget
        # reconcile; the repair is the prepaid wallet lane's alone.
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
