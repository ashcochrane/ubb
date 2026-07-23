"""#46 acceptance pins — the arrival-signals switch (delivery spec §E).

One switch, two honest postures: ``Tenant.arrival_signals_enabled`` (default
ON, read only through ``flags.arrival_signals_on``) governs the whole
arrival-time fast lane as ONE unit — accept-time holds, live counters,
arrival-moment floor detection, and the upward repair. OFF is the honest
degraded posture: accept writes no live-counter Redis keys and detection
happens at settle, at settle latency. The durable lane — settle-time
detection, the signal ledger, the patrol jobs, webhook delivery, ack
verdicts — never switches off, and maintains the ack-verdict flag in both
postures, so the tenant-facing contract is identical either way.

Pin 9 — switch OFF: accept writes no Redis counter keys (both accept paths,
        both billing modes); acks keep the identical schema with verdicts
        from the durable-maintained flag; a floor crossing signals at settle
        latency; OFF→ON re-seeds via the immediate reconcile; the flag is
        read only through the flags module; default is ON.
Plus  — the upward repair is inert with the lane off; patrol jobs 1–4
        (missed-transition drive, flag re-alignment, re-mint, sweep) run
        identically with the lane off; outstanding holds still drain at
        settle after ON→OFF (the "needs nothing" flip direction).
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
from apps.metering.usage.models import RawIngestEvent, UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import UsageRecorded
from apps.platform.tasks.models import Task
from apps.platform.tasks.reasons import CUSTOMER_WIDE_STOP
from apps.platform.tenants.flags import arrival_signals_on
from apps.platform.tenants.models import Tenant, TenantApiKey


def _tenant(mode="prepaid", arrival=True, enf="enforcing"):
    return Tenant.objects.create(
        name="T", products=["metering", "billing", "metering_async"],
        billing_mode=mode, enforcement_mode=enf,
        arrival_signals_enabled=arrival)


def _customer(t, balance_micros=0, ext="c1"):
    c = Customer.objects.create(tenant=t, external_id=ext)
    Wallet.objects.create(customer=c, balance_micros=balance_micros)
    return c


def _auth(t):
    _k, raw = TenantApiKey.create_key(t, label="t")
    return {"HTTP_AUTHORIZATION": f"Bearer {raw}"}


def _ingest(client, auth, events):
    return client.post("/api/v1/metering/usage/ingest",
                       data=json.dumps({"events": events}),
                       content_type="application/json", **auth)


def _event(c, billed=1_000_000):
    return {"customer_id": str(c.id), "request_id": f"req-{uuid.uuid4()}",
            "idempotency_key": f"idem-{uuid.uuid4()}",
            "billed_cost_micros": billed}


def _record_sync(client, auth, c, billed, key=None):
    key = key or f"k-{uuid.uuid4()}"
    return client.post("/api/v1/metering/usage", data=json.dumps({
        "customer_id": str(c.id), "request_id": key, "idempotency_key": key,
        "billed_cost_micros": billed}),
        content_type="application/json", **auth)


def _events(event_type):
    return OutboxEvent.objects.filter(event_type=event_type).order_by("created_at")


@pytest.mark.django_db
class TestDefaultAndAccessor:
    def test_default_is_on_including_a_plain_new_tenant(self):
        t = Tenant.objects.create(name="fresh", products=["metering"])
        assert t.arrival_signals_enabled is True

    def test_accessor_truth_table(self):
        # The flag is a posture WITHIN enforcing — meaningless outside it.
        assert arrival_signals_on(_tenant(arrival=True)) is True
        assert arrival_signals_on(_tenant(arrival=False)) is False
        assert arrival_signals_on(_tenant(arrival=True, enf="off")) is False


@pytest.mark.django_db
class TestPin9AcceptWritesNoRedisKeys:
    """Switch OFF: the fast lane is off as one unit at accept — no hold, no
    live counter, no arrival crossing detection — on both accept paths and
    both billing modes. (Idempotency SETNX keys are ingest dedup plumbing,
    not part of the arrival-signals lane, and are out of scope here.)"""

    def setup_method(self):
        cache.clear()

    def test_async_accept_prepaid_no_hold_no_counter_no_flag(self):
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=1_000_000)
        # Would cross the (default 0) floor if the arrival lane were on.
        r = _ingest(Client(), _auth(t), [_event(c, billed=900_000),
                                         _event(c, billed=200_000)])
        assert r.status_code == 200
        results = r.json()["results"]
        assert all(x["accepted"] for x in results)
        # No arrival-moment detection: the crossing is real but undetected
        # until settle — the honest degraded posture.
        assert all(x["stop"] is False for x in results)
        assert results[0]["estimated_cost_micros"] == 900_000  # ack unchanged
        assert Door.balance(c.id) is None                      # no counter
        assert Door.stop_reason(c.id) is None                  # no flag
        for raw in RawIngestEvent.objects.all():
            assert raw.held is False                           # no hold taken
            assert raw.estimate_micros > 0                     # estimate kept

    def test_async_accept_postpaid_no_livespend(self):
        t = _tenant(mode="postpaid", arrival=False)
        c = _customer(t)
        r = _ingest(Client(), _auth(t), [_event(c, billed=5_000_000)])
        assert r.status_code == 200
        assert Door.spend(c.id) is None

    def test_sync_accept_no_counter_and_event_still_lands_and_bills(self):
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=5_000_000)
        r = _record_sync(Client(), _auth(t), c, billed=8_000_000, key="k1")
        assert r.status_code == 200
        assert r.json()["stop"] is False          # no arrival detection
        ev = UsageEvent.objects.get(tenant=t, idempotency_key="k1")
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

    def test_async_ack_schema_identical_on_vs_off(self):
        on_t = _tenant(arrival=True)
        off_t = _tenant(arrival=False)
        on_r = _ingest(Client(), _auth(on_t),
                       [_event(_customer(on_t, 10_000_000, ext="a"))])
        off_r = _ingest(Client(), _auth(off_t),
                        [_event(_customer(off_t, 10_000_000, ext="b"))])
        on_item, off_item = on_r.json()["results"][0], off_r.json()["results"][0]
        assert set(on_item.keys()) == set(off_item.keys())

    def test_acks_carry_verdict_from_the_durable_maintained_flag(self):
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=10_000_000)
        # The durable lane set the flag (as its winning transition does in
        # both postures); both accept paths surface it — a READ, not a write.
        LiveCounter.ensure_stop_flag(c.id, CUSTOMER_WIDE_STOP)
        client, auth = Client(), _auth(t)
        item = _ingest(client, auth, [_event(c)]).json()["results"][0]
        assert item["stop"] is True
        assert item["stop_reason"] == CUSTOMER_WIDE_STOP
        assert item["stop_scope"] == "customer"
        sync = _record_sync(client, auth, c, billed=1_000).json()
        assert sync["stop"] is True
        assert sync["stop_reason"] == CUSTOMER_WIDE_STOP
        assert Door.balance(c.id) is None  # still no counter


@pytest.mark.django_db
class TestPin9CrossingSignalsAtSettleLatency:
    def setup_method(self):
        cache.clear()

    def test_durable_lane_detects_at_settle_and_next_ack_shows_it(self):
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=5_000_000)
        client, auth = Client(), _auth(t)
        r = _record_sync(client, auth, c, billed=8_000_000)
        assert r.json()["stop"] is False            # nothing at arrival
        assert not _events("stop.fired").exists()
        # Settle latency: the durable drawdown lane processes the event and
        # detects the floor crossing — signal + flag, never an ack change.
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            tenant_id=t.id, customer_id=c.id,
            event_id=str(uuid.uuid4()), cost_micros=8_000_000)))
        assert _events("stop.fired").count() == 1
        assert LiveCounter.read(c.id, t)["stop"] is True
        nxt = _record_sync(client, auth, c, billed=1_000).json()
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
                    data=json.dumps({"arrival_signals_enabled": value}),
                    content_type="application/json", **_auth(t))
        return resp, delay

    def test_flip_either_way_enqueues_the_immediate_reconcile(
            self, django_capture_on_commit_callbacks):
        t = _tenant(arrival=False)
        resp, delay = self._patch(t, True, django_capture_on_commit_callbacks)
        assert resp.status_code == 200
        assert resp.json()["arrival_signals_enabled"] is True
        assert delay.call_args == mock.call(str(t.id))
        t.refresh_from_db()
        resp, delay = self._patch(t, False, django_capture_on_commit_callbacks)
        assert resp.json()["arrival_signals_enabled"] is False
        assert delay.call_args == mock.call(str(t.id))

    def test_no_flip_no_enqueue(self, django_capture_on_commit_callbacks):
        t = _tenant(arrival=True)
        resp, delay = self._patch(t, True, django_capture_on_commit_callbacks)
        assert resp.status_code == 200
        assert delay.call_count == 0

    def test_off_to_on_reseeds_the_counter_from_durable_truth(self):
        # While OFF, accept wrote nothing — no counter exists. The immediate
        # reconcile after the flip seeds it from the durable balance, so the
        # fast lane restarts honest within minutes, not at first-use luck.
        t = _tenant(arrival=True)   # post-flip state
        c = _customer(t, balance_micros=7_000_000)
        assert Door.balance(c.id) is None
        reconcile_tenant_live_counters(str(t.id))
        assert Door.balance(c.id) == 7_000_000

    def test_reconcile_with_lane_off_drives_signals_but_no_counter(self):
        # The same per-tenant pass in the OFF posture: counter jobs skip
        # (part of the fast lane) while the durable-basis signal catch-up —
        # the lane that never switches off — still stops a durably crossed
        # owner and re-aligns the verdict flag.
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=-1_000_000)  # past the (default 0) floor
        reconcile_tenant_live_counters(str(t.id))
        assert Door.balance(c.id) is None                     # no seed
        assert _events("stop.fired").count() == 1             # durable lane
        assert LiveCounter.read(c.id, t)["stop"] is True


@pytest.mark.django_db
class TestRepairInertWithLaneOff:
    def test_injected_deficit_never_candidates_with_the_lane_off(self):
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=20_000_000)
        # A deficit the repair would candidate if the lane were on.
        Door.set_balance(c.id, 5_000_000)
        counts = repair.repair_live_balances(t)
        assert not any(counts.values())
        assert not LiveBalanceRepair.objects.exists()

    def test_same_deficit_candidates_with_the_lane_on(self):
        t = _tenant(arrival=True)
        c = _customer(t, balance_micros=20_000_000)
        Door.set_balance(c.id, 5_000_000)
        repair.repair_live_balances(t)
        assert LiveBalanceRepair.objects.filter(
            owner_id=c.id, status=repair.STATUS_CANDIDATE).exists()


@pytest.mark.django_db
class TestPatrolUnaffectedByTheSwitch:
    """Patrol jobs 1–4 are the durable lane: with the lane off they run
    identically on the hourly beat — re-mint, sweep, missed-transition
    drive, flag re-alignment."""

    def test_dead_lettered_stop_is_reminted_with_the_lane_off(self):
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=-1_000_000)  # durably crossed: no
        StopSignalService.drive_stop(                # clearing interference
            c.id, t, reason=CUSTOMER_WIDE_STOP, balance_micros=-1_000_000)
        row = StopSignalState.objects.get(owner=c)
        OutboxEvent.objects.filter(id=row.announce_outbox_id).update(status="failed")
        reconcile_live_ledgers()
        fired = _events("stop.fired")
        assert fired.count() == 2
        assert fired.last().payload["re_announcement"] is True

    def test_over_limit_task_is_swept_with_the_lane_off(self):
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=10_000_000)
        task = Task.objects.create(
            tenant=t, customer=c, status="active", balance_snapshot_micros=0,
            provider_cost_limit_micros=100, total_provider_cost_micros=150,
            billing_owner_id=c.id, metadata={})
        reconcile_live_ledgers()
        task.refresh_from_db()
        assert task.status == "killed"


@pytest.mark.django_db
class TestOnToOffHoldsDrainAtSettle:
    def setup_method(self):
        cache.clear()

    def test_outstanding_hold_still_trues_up_after_the_flip(self):
        # ON→OFF needs nothing: a hold acquired while ON drains at settle
        # even though the lane is now off — the counter converges instead of
        # being wedged low until the TTL.
        t = _tenant(arrival=True)
        c = _customer(t, balance_micros=20_000_000)
        r = _ingest(Client(), _auth(t), [_event(c, billed=1_500_000)])
        assert r.status_code == 200
        assert Door.balance(c.id) == 18_500_000
        t.arrival_signals_enabled = False
        t.save(update_fields=["arrival_signals_enabled"])
        raw = RawIngestEvent.objects.get()
        assert raw.held is True
        # Widen the recorded estimate so the settle delta (estimate − exact)
        # is a visible +500_000 credit-back.
        raw.estimate_micros = 2_000_000
        raw.save(update_fields=["estimate_micros"])
        from apps.metering.usage.services.usage_service import UsageService
        assert UsageService.settle_raw(raw) == "settled"
        assert Door.balance(c.id) == 19_000_000


@pytest.mark.django_db
class TestSettleWritesNothingWithLaneOff:
    """Off as one unit, at settle too: a row accepted with the lane off
    (held=False) must not have its full-debit true-up create or move a
    fast-lane counter while the lane is still off — for postpaid that INCRBY
    would BIRTH the livespend key and quietly maintain a counter whose
    MAX-merge is switched off. (A genuinely held row still drains — see
    TestOnToOffHoldsDrainAtSettle.)"""

    def setup_method(self):
        cache.clear()

    def test_postpaid_settle_births_no_livespend(self):
        from apps.metering.usage.services.usage_service import UsageService
        t = _tenant(mode="postpaid", arrival=False)
        c = _customer(t)
        assert _ingest(Client(), _auth(t),
                       [_event(c, billed=5_000_000)]).status_code == 200
        raw = RawIngestEvent.objects.get()
        assert raw.held is False
        assert UsageService.settle_raw(raw) == "settled"
        assert Door.spend(c.id) is None

    def test_prepaid_settle_leaves_a_present_counter_untouched(self):
        from apps.metering.usage.services.usage_service import UsageService
        t = _tenant(arrival=False)
        c = _customer(t, balance_micros=20_000_000)
        assert _ingest(Client(), _auth(t),
                       [_event(c, billed=1_500_000)]).status_code == 200
        # A leftover counter from before the ON→OFF flip: the lane-off
        # settle must not debit it (that would be fast-lane maintenance).
        Door.set_balance(c.id, 10_000_000)
        raw = RawIngestEvent.objects.get()
        assert raw.held is False
        assert UsageService.settle_raw(raw) == "settled"
        assert Door.balance(c.id) == 10_000_000


PLATFORM_ROOT = Path(__file__).resolve().parents[4]

# The ONLY sanctioned attribute-access sites for the column outside the flags
# module's getattr: the tenant-config endpoint (the write path + config echo).
# Everything else must ask flags.arrival_signals_on — the single read point.
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
                        and node.attr == "arrival_signals_enabled"):
                    hits.add(rel)
    return hits


class TestFlagReadOnlyThroughFlagsModule:
    def test_no_attribute_access_outside_the_allowlist(self):
        # Pin 9's doctrine leg, AST-enforced like ADR-001: `x.arrival_
        # signals_enabled` anywhere outside the allowlist is a second read
        # point waiting to diverge from `flags.arrival_signals_on` (which
        # itself uses getattr — no Attribute node, deliberately).
        assert _attribute_sites() == ALLOWED_ATTRIBUTE_SITES
