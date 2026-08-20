"""#46 acceptance pins — the live-counter-maintenance switch (delivery spec §E).

One switch, two honest postures: ``Tenant.live_counter_maintenance_enabled``
(default ON, read only through ``flags.live_counter_maintenance_on``) governs
real-time counter maintenance — the synchronous live-counter write and its
crossing check on the recording path, the reconciles' counter jobs, and the
upward repair. It selects WHEN the counters are maintained rather than which
route an event takes in (#149 §6.5); it was named for an arrival-time lane
until #246, and that lane died in slice 1 without ever having owned it. OFF is
the honest degraded posture: recording writes no live-counter Redis keys and
detection happens on the durable drawdown lane, at its latency. That durable
lane — the signal ledger, the patrol jobs, webhook delivery, ack verdicts —
never switches off, and maintains the ack-verdict flag in both postures, so
the tenant-facing contract is identical either way.

**Every posture below is driven through ``POST /api/v1/metering/usage`` —
the one way to report usage (#192).** These assertions were always about the
guarantee rather than the route: each one names the guarantee it preserves
so that a later reader can tell a preserved invariant from a deleted one.

Pin 9 — switch OFF: recording writes no Redis counter keys (both billing
        modes); acks keep the identical schema with verdicts from the
        durable-maintained flag; a floor crossing signals at the durable
        lane's latency; OFF→ON re-seeds via the immediate reconcile; the
        flag is read only through the flags module; default is ON.
Plus  — the upward repair is inert with maintenance off; patrol jobs 1–4
        (missed-transition drive, flag re-alignment, re-mint, sweep) run
        identically with maintenance off; ON→OFF needs no drain, because the
        recording path debits the exact cost as it records it.
"""
import ast
import json
import uuid
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import Client

from apps.billing.gating import repair
from apps.billing.gating.models import LiveBalanceRepair, StopSignalState
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.billing.gating.services.stop_signal_service import StopSignalService
from apps.billing.gating.tasks import (
    reconcile_live_ledgers,
    reconcile_tenant_live_counters,
)
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import UsageRecorded
from apps.platform.work.models import Task
from apps.platform.work.reasons import CUSTOMER_WIDE_STOP
from apps.platform.tenants.flags import live_counter_maintenance_on
from apps.platform.tenants.models import Tenant, TenantApiKey


def _tenant(mode="prepaid", maintenance=True, enf="enforcing"):
    tenant = Tenant.objects.create(
        name="T", products=["metering", "billing"],
        billing_mode=mode, enforcement_mode=enf,
        live_counter_maintenance_enabled=maintenance)
    # Every tenant here records usage through `_record`, and what an event
    # bills is the tenant's own configuration now rather than the call's (#365).
    # The rule matches ONE declared quantity, so an event measuring anything
    # else still falls where it fell before.
    a_rule_that_prices_what_it_measures(tenant)
    return tenant


def _customer(t, balance_micros=0, ext="c1"):
    c = Customer.objects.create(tenant=t, external_id=ext)
    Wallet.objects.create(customer=c, balance_micros=balance_micros)
    return c


def _auth(t):
    _k, raw = TenantApiKey.create_key(t, label="t")
    return {"HTTP_AUTHORIZATION": f"Bearer {raw}"}


def _record(client, auth, c, billed=1_000_000, key=None):
    """The one way to report usage — every posture assertion drives this.

    There is no second recording helper here any more: the module used to run
    each posture twice, once per lane, and the lanes have collapsed into one.
    """
    key = key or f"k-{uuid.uuid4()}"
    # ⚠ THE AMOUNT IS CONFIGURED, NOT SENT (#365). This body used to state what
    # to bill; the request has no such field any more and REFUSES one, so the
    # caller's number becomes a quantity the tenant's own rule prices at exactly
    # it. Callers of this helper still say one figure and still never learn how.
    return client.post("/api/v1/metering/usage", data=json.dumps({
        "customer_id": str(c.id), "request_id": key, "idempotency_key": key,
        "measurements": priced_at(billed)}),
        content_type="application/json", **auth)


def _events(event_type):
    return OutboxEvent.objects.filter(event_type=event_type).order_by("created_at")


@pytest.mark.django_db
class TestDefaultAndAccessor:
    def test_default_is_on_including_a_plain_new_tenant(self):
        t = Tenant.objects.create(name="fresh", products=["metering"])
        assert t.live_counter_maintenance_enabled is True

    def test_accessor_truth_table(self):
        # The flag is a posture WITHIN enforcing — meaningless outside it.
        assert live_counter_maintenance_on(_tenant(maintenance=True)) is True
        assert live_counter_maintenance_on(_tenant(maintenance=False)) is False
        assert live_counter_maintenance_on(_tenant(maintenance=True, enf="off")) is False


@pytest.mark.django_db
class TestPin9RecordingWritesNoRedisKeys:
    """Switch OFF: real-time counter maintenance is off at record time — no
    live counter, no crossing detection — in both billing modes.

    Preserves: with the switch off, recording writes no live-counter Redis key,
    and the event still lands and bills. (Idempotency SETNX keys are dedup
    plumbing, not counter maintenance, and are out of scope.)"""

    def setup_method(self):
        cache.clear()

    def test_prepaid_recording_writes_no_counter_and_no_flag(self):
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=1_000_000)
        # Together these would cross the (default 0) floor if maintenance were on.
        client, auth = Client(), _auth(t)
        first = _record(client, auth, c, billed=900_000)
        second = _record(client, auth, c, billed=200_000)
        assert first.status_code == 200 and second.status_code == 200
        # No record-time detection: the crossing is real but undetected
        # until the durable drawdown lane runs — the honest degraded posture.
        assert first.json()["stop"] is False
        assert second.json()["stop"] is False
        # The ack still reports the cost — now the settled one, since the
        # recording path prices exactly and there is no estimate to carry.
        assert first.json()["billed_cost_micros"] == 900_000
        assert Door.balance(c.id) is None                       # no counter
        assert Door.stop_reason(c.id) is None                   # no flag
        # Both events landed and billed — nothing was reserved anywhere.
        assert Posting.objects.filter(tenant=t).count() == 2

    def test_postpaid_recording_writes_no_livespend(self):
        t = _tenant(mode="postpaid", maintenance=False)
        c = _customer(t)
        r = _record(Client(), _auth(t), c, billed=5_000_000)
        assert r.status_code == 200
        assert Door.spend(c.id) is None

    def test_recording_no_counter_and_event_still_lands_and_bills(self):
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=5_000_000)
        r = _record(Client(), _auth(t), c, billed=8_000_000, key="k1")
        assert r.status_code == 200
        assert r.json()["stop"] is False          # no record-time detection
        ev = Posting.objects.get(tenant=t, idempotency_key="k1")
        assert ev.billed_cost_micros == 8_000_000  # lands and bills
        assert Door.balance(c.id) is None
        assert not _events("stop.fired").exists()


@pytest.mark.django_db
class TestPin9AckContractIdentical:
    """Durable transitions maintain the ack-verdict flag in BOTH postures, so
    the ack schema and verdict fields are identical either way — only the
    latency profile changes."""

    def setup_method(self):
        cache.clear()

    def test_ack_verdict_identical_on_vs_off(self):
        """Preserves: the tenant-facing verdict is the same in both postures.

        This used to compare the two acks' KEY SETS, which was falsifiable
        when the lane built its own verdict dict. The surviving route answers
        through a fixed-field response schema, so an equal key set is now
        true by construction and would pin nothing. What is still falsifiable
        — and is what the pin always meant — is that the VERDICT FIELDS agree:
        the durable-maintained flag is read in both postures, so a stopped
        owner reads as stopped whether maintenance is on or off. Only the
        counter differs, which is the latency profile and nothing else."""
        on_t, off_t = _tenant(maintenance=True), _tenant(maintenance=False)
        on_c = _customer(on_t, 10_000_000, ext="a")
        off_c = _customer(off_t, 10_000_000, ext="b")
        # A durable transition both postures must surface identically.
        LiveCounter.ensure_stop_flag(on_c.id, CUSTOMER_WIDE_STOP)
        LiveCounter.ensure_stop_flag(off_c.id, CUSTOMER_WIDE_STOP)
        on_ack = _record(Client(), _auth(on_t), on_c).json()
        off_ack = _record(Client(), _auth(off_t), off_c).json()

        verdict = ("stop", "stop_reason", "stop_scope")
        assert ({k: on_ack[k] for k in verdict}
                == {k: off_ack[k] for k in verdict}
                == {"stop": True, "stop_reason": CUSTOMER_WIDE_STOP,
                    "stop_scope": "customer"})
        # ... and the only difference is the live counter itself.
        assert Door.balance(on_c.id) is not None
        assert Door.balance(off_c.id) is None

    def test_acks_carry_verdict_from_the_durable_maintained_flag(self):
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=10_000_000)
        # The durable lane set the flag (as its winning transition does in
        # both postures); the recording path surfaces it — a READ, not a write.
        LiveCounter.ensure_stop_flag(c.id, CUSTOMER_WIDE_STOP)
        ack = _record(Client(), _auth(t), c).json()
        assert ack["stop"] is True
        assert ack["stop_reason"] == CUSTOMER_WIDE_STOP
        assert ack["stop_scope"] == "customer"
        assert Door.balance(c.id) is None  # still no counter


@pytest.mark.django_db
class TestPin9CrossingSignalsAtDurableLaneLatency:
    def setup_method(self):
        cache.clear()

    def test_durable_lane_detects_the_crossing_and_next_ack_shows_it(self):
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=5_000_000)
        client, auth = Client(), _auth(t)
        r = _record(client, auth, c, billed=8_000_000)
        assert r.json()["stop"] is False            # nothing at record time
        assert not _events("stop.fired").exists()
        # Durable-lane latency: the drawdown lane processes the event and
        # detects the floor crossing — signal + flag, never an ack change.
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            tenant_id=t.id, customer_id=c.id,
            event_id=str(uuid.uuid4()), cost_micros=8_000_000)))
        assert _events("stop.fired").count() == 1
        assert LiveCounter.read(c.id, t)["stop"] is True
        nxt = _record(client, auth, c, billed=1_000).json()
        assert nxt["stop"] is True                  # verdict via the flag
        assert nxt["stop_reason"] == CUSTOMER_WIDE_STOP


@pytest.mark.django_db
class TestPin9ToggleChoreography:
    def setup_method(self):
        cache.clear()

    def _patch(self, t, value, django_capture_on_commit_callbacks):
        with mock.patch(
                "apps.billing.gating.tasks.reconcile_tenant_live_counters.delay"
        ) as delay:
            with django_capture_on_commit_callbacks(execute=True):
                resp = Client().patch(
                    "/api/v1/tenant/config",
                    data=json.dumps({"live_counter_maintenance_enabled": value}),
                    content_type="application/json", **_auth(t))
        return resp, delay

    def test_flip_either_way_enqueues_the_immediate_reconcile(
            self, django_capture_on_commit_callbacks):
        t = _tenant(maintenance=False)
        resp, delay = self._patch(t, True, django_capture_on_commit_callbacks)
        assert resp.status_code == 200
        assert resp.json()["live_counter_maintenance_enabled"] is True
        assert delay.call_args == mock.call(str(t.id))
        t.refresh_from_db()
        resp, delay = self._patch(t, False, django_capture_on_commit_callbacks)
        assert resp.json()["live_counter_maintenance_enabled"] is False
        assert delay.call_args == mock.call(str(t.id))

    def test_no_flip_no_enqueue(self, django_capture_on_commit_callbacks):
        t = _tenant(maintenance=True)
        resp, delay = self._patch(t, True, django_capture_on_commit_callbacks)
        assert resp.status_code == 200
        assert delay.call_count == 0

    def test_off_to_on_reseeds_the_counter_from_durable_truth(self):
        # While OFF, accept wrote nothing — no counter exists. The immediate
        # reconcile after the flip seeds it from the durable balance, so the
        # maintenance restarts honest within minutes, not at first-use luck.
        t = _tenant(maintenance=True)   # post-flip state
        c = _customer(t, balance_micros=7_000_000)
        assert Door.balance(c.id) is None
        reconcile_tenant_live_counters(str(t.id))
        assert Door.balance(c.id) == 7_000_000

    def test_reconcile_with_maintenance_off_drives_signals_but_no_counter(self):
        # The same per-tenant pass in the OFF posture: counter jobs skip
        # (real-time maintenance) while the durable-basis signal catch-up —
        # the lane that never switches off — still stops a durably crossed
        # owner and re-aligns the verdict flag.
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=-1_000_000)  # past the (default 0) floor
        reconcile_tenant_live_counters(str(t.id))
        assert Door.balance(c.id) is None                     # no seed
        assert _events("stop.fired").count() == 1             # durable lane
        assert LiveCounter.read(c.id, t)["stop"] is True


@pytest.mark.django_db
class TestRepairInertWithLaneOff:
    def test_injected_deficit_never_candidates_with_maintenance_off(self):
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=20_000_000)
        # A deficit the repair would candidate if maintenance were on.
        Door.set_balance(c.id, 5_000_000)
        counts = repair.repair_live_balances(t)
        assert not any(counts.values())
        assert not LiveBalanceRepair.objects.exists()

    def test_same_deficit_candidates_with_the_lane_on(self):
        t = _tenant(maintenance=True)
        c = _customer(t, balance_micros=20_000_000)
        Door.set_balance(c.id, 5_000_000)
        repair.repair_live_balances(t)
        assert LiveBalanceRepair.objects.filter(
            owner_id=c.id, status=repair.STATUS_CANDIDATE).exists()


@pytest.mark.django_db
class TestPatrolUnaffectedByTheSwitch:
    """Patrol jobs 1–4 are the durable lane: with maintenance off they run
    identically on the hourly beat — re-mint, sweep, missed-transition
    drive, flag re-alignment."""

    def test_dead_lettered_stop_is_reminted_with_maintenance_off(self):
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=-1_000_000)  # durably crossed: no
        StopSignalService.drive_stop(                # clearing interference
            c.id, t, reason=CUSTOMER_WIDE_STOP, balance_micros=-1_000_000)
        row = StopSignalState.objects.get(owner=c)
        OutboxEvent.objects.filter(id=row.announce_outbox_id).update(status="failed")
        reconcile_live_ledgers()
        fired = _events("stop.fired")
        assert fired.count() == 2
        assert fired.last().payload["re_announcement"] is True

    def test_over_limit_task_is_swept_with_maintenance_off(self):
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=10_000_000)
        task = Task.objects.create(
            tenant=t, customer=c, status="active", balance_snapshot_micros=0,
            provider_cost_limit_micros=100, total_provider_cost_micros=150,
            billing_owner_id=c.id, metadata={})
        reconcile_live_ledgers()
        task.refresh_from_db()
        assert task.status == "killed"


@pytest.mark.django_db
class TestOnToOffNeedsNoDrain:
    """Preserves: the ON→OFF flip leaves the live counter CONVERGED with
    durable truth, rather than wedged away from it until the TTL.

    Convergence is the proposition; only the threat to it changed. It used to
    be threatened by a reservation caught mid-flight by the flip — an
    estimate held while ON that only a later settle would true up — so the
    pin drove that settle and watched the counter close the gap. The
    recording path debits the EXACT cost as it records, so the counter is
    already equal to durable truth at the moment of the flip and there is
    nothing outstanding to drain. The assertion below is therefore the
    agreement itself, checked across the flip, rather than the closing of a
    gap that can no longer open."""

    def setup_method(self):
        cache.clear()

    def test_counter_agrees_with_durable_truth_across_the_flip(self):
        t = _tenant(maintenance=True)
        c = _customer(t, balance_micros=20_000_000)
        client, auth = Client(), _auth(t)
        assert _record(client, auth, c, billed=1_500_000).status_code == 200
        assert Door.balance(c.id) == 18_500_000
        t.live_counter_maintenance_enabled = False
        t.save(update_fields=["live_counter_maintenance_enabled"])

        # Durable truth catches up on the drawdown lane, which never switches
        # off. The counter written while ON must already agree with it — that
        # agreement is what "the flip needs nothing" means.
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            tenant_id=t.id, customer_id=c.id,
            event_id=str(uuid.uuid4()), cost_micros=1_500_000)))
        wallet = Wallet.objects.get(customer=c)
        assert wallet.balance_micros == 18_500_000
        assert Door.balance(c.id) == wallet.balance_micros


@pytest.mark.django_db
class TestLaneOffWritesNoCounterOnTheRecordingPath:
    """Preserves: a maintenance-off recording must not create or move a live
    counter.

    The hazard is asymmetric, which is why both modes are pinned. For
    postpaid the debit is an INCRBY, so a maintenance-off write would BIRTH the
    livespend key and quietly maintain a counter whose MAX-merge is switched
    off. For prepaid the key may already exist — left over from before an
    ON→OFF flip — and a maintenance-off write must leave it exactly as it found it
    rather than debiting it."""

    def setup_method(self):
        cache.clear()

    def test_postpaid_recording_births_no_livespend(self):
        t = _tenant(mode="postpaid", maintenance=False)
        c = _customer(t)
        assert _record(Client(), _auth(t), c, billed=5_000_000).status_code == 200
        assert Door.spend(c.id) is None

    def test_prepaid_recording_leaves_a_present_counter_untouched(self):
        t = _tenant(maintenance=False)
        c = _customer(t, balance_micros=20_000_000)
        # A leftover counter from before the ON→OFF flip: a maintenance-off record
        # must not debit it (that would be real-time maintenance).
        Door.set_balance(c.id, 10_000_000)
        assert _record(Client(), _auth(t), c, billed=1_500_000).status_code == 200
        assert Door.balance(c.id) == 10_000_000


PLATFORM_ROOT = Path(__file__).resolve().parents[4]

# The ONLY sanctioned attribute-access sites for the column outside the flags
# module's getattr: the tenant-config endpoint (the write path + config echo).
# Everything else must ask flags.live_counter_maintenance_on — the single read
# point.
ALLOWED_ATTRIBUTE_SITES = {
    Path("api") / "v1" / "tenant_endpoints.py",
}


def _attribute_sites():
    hits = set()
    for base in ("apps", "api", "core"):
        for path in (PLATFORM_ROOT / base).rglob("*.py"):
            rel = path.relative_to(PLATFORM_ROOT)
            if "tests" in rel.parts or "migrations" in rel.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute)
                        and node.attr == "live_counter_maintenance_enabled"):
                    hits.add(rel)
    return hits


class TestFlagReadOnlyThroughFlagsModule:
    def test_no_attribute_access_outside_the_allowlist(self):
        # Pin 9's doctrine leg, AST-enforced like ADR-001:
        # `x.live_counter_maintenance_enabled` anywhere outside the allowlist
        # is a second read point waiting to diverge from
        # `flags.live_counter_maintenance_on` (which itself uses getattr — no
        # Attribute node, deliberately).
        assert _attribute_sites() == ALLOWED_ATTRIBUTE_SITES
