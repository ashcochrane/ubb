"""#44 acceptance pins — the hourly patrol (delivery spec §C/§F).

Late, never lost, independent of traffic: the patrol jobs join the hourly
reconcile pass (no new scheduled task, enforcing tenants only) and guarantee
that a real crossing always eventually produces its signal (missed-transition
drive, both families), the fast Redis flag matches durable truth, unannounced
signal rows are re-minted as fresh current-state events
(``re_announcement: true``, bottom-line only), and active tasks sitting
at-or-past their provider-cost limit are swept into the idempotent kill flow.
Patrol outcomes land as counters on the ops/ingest-health surface; the shared
outbox retry policy and dead-letter alerting are untouched.

Pin 1  — ambient-rollback corner: orphaned Redis flag re-aligned; a durably
         crossed position signals on the next pass.
Pin 2  — (completes #43's half) after an emit-failure rollback the patrol
         fires the signal within one interval.
Pin 3  — dead-lettered stop.fired → fresh current-state announcement (same
         episode, stamp updated); in-flight rows left alone; announced-by-
         skipped never re-mints.
Pin 4  — stop + clear during a blind window → recovery delivers the current
         bottom line only (one cleared announcement).
Pin 5  — the soft pair rides the same rails; families stay independent.
Pin 6  — a task whose kill transaction crashed is killed and announced by the
         sweep; a subtask likewise, alone, parent unaffected.
"""
import pytest
from unittest.mock import patch

from apps.billing.gating import patrol
from apps.billing.gating.models import PatrolOutcome, StopSignalState
from apps.billing.gating.services.live_ledger_service import (
    LiveLedgerService,
    _client,
    _stop_key,
)
from apps.billing.gating.services.stop_signal_service import (
    FAMILY_FLOOR_STOP,
    FAMILY_SOFT_FLOOR,
    StopSignalService,
)
from apps.billing.gating.tasks import reconcile_live_ledgers
from apps.billing.queries import get_patrol_stats
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.models import Task
from apps.platform.tenants.models import Tenant


def _tenant(enf="enforcing", mode="prepaid"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


def _customer(t, balance_micros=0, hard=None, soft=None, ext="c1"):
    c = Customer.objects.create(tenant=t, external_id=ext)
    Wallet.objects.create(customer=c, balance_micros=balance_micros)
    if hard is not None or soft is not None:
        CustomerBillingProfile.objects.create(
            customer=c, min_balance_micros=hard or 0,
            soft_min_balance_micros=soft)
    return c


def _events(event_type):
    return OutboxEvent.objects.filter(event_type=event_type).order_by("created_at")


def _set_status(outbox_id, status):
    OutboxEvent.objects.filter(id=outbox_id).update(status=status)


def _stamp_of(owner, family):
    return StopSignalState.objects.get(owner=owner, family=family).announce_outbox_id


def _task(t, c, limit=None, total=0, status="active", parent=None,
          stamp=None, meta=None):
    return Task.objects.create(
        tenant=t, customer=c, parent=parent, status=status,
        balance_snapshot_micros=0, provider_cost_limit_micros=limit,
        total_provider_cost_micros=total, billing_owner_id=c.id,
        announce_outbox_id=stamp, metadata=meta or {})


@pytest.mark.django_db
class TestPin1AmbientRollback:
    def test_orphan_flag_against_recovered_durable_truth_is_realigned(self):
        # The fast lane SET the flag, then the ambient transaction died:
        # transition + emit vanished together, the flag survived. Durable
        # truth says not-crossed -> the patrol deletes the orphan; nothing
        # is emitted (there is no state to announce).
        t = _tenant()
        c = _customer(t, balance_micros=5_000_000)
        _client().set(_stop_key(c.id), "customer_wide_stop")
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is True
        out = LiveLedgerService.reconcile_prepaid(c.id, t)
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is False
        assert out["flag_realigned"] is True
        assert not OutboxEvent.objects.filter(
            event_type__in=["stop.fired", "stop.cleared"]).exists()
        assert not StopSignalState.objects.filter(owner=c).exists()

    def test_durably_crossed_position_signals_on_the_next_pass(self):
        # The rollback took the transition and the event, but the crossing is
        # real (the durable balance is past the floor): the next patrol pass
        # drives the stop and emits — late, never lost.
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)  # floor defaults to 0
        _client().set(_stop_key(c.id), "customer_wide_stop")  # survived flag
        LiveLedgerService.reconcile_prepaid(c.id, t)
        fired = _events("stop.fired")
        assert fired.count() == 1
        assert fired.get().payload["episode_seq"] == 1
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is True

    def test_missing_flag_for_a_durably_stopped_owner_is_realigned(self):
        # The inverse orphan: durable truth says stopped, the flag is gone
        # (Redis flush). The patrol re-sets it from the durable family state.
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        assert _client().get(_stop_key(c.id)) is None  # durable lane, no flag
        out = LiveLedgerService.reconcile_prepaid(c.id, t)
        assert LiveLedgerService.read_stop(c.id, t)["stop"] is True
        assert out["flag_realigned"] is True
        assert _events("stop.fired").count() == 1  # no re-emission


@pytest.mark.django_db
class TestPin2EmitFailureCompletes:
    @patch("apps.platform.events.tasks.process_single_event")
    def test_patrol_fires_the_signal_within_one_interval(self, _m, monkeypatch):
        # #43 pinned the rollback half (usage lands, state untransitioned);
        # this completes it: the patrol fires the missed signal on its next
        # pass, from durable truth alone.
        from django.db import connection
        from apps.metering.usage.services.usage_service import UsageService

        orig_create = OutboxEvent.objects.create

        def _create(**kwargs):
            if kwargs.get("event_type") == "stop.fired":
                with connection.cursor() as cur:
                    cur.execute("SELECT 1/0")  # DataError; savepoint rollback
            return orig_create(**kwargs)

        monkeypatch.setattr(OutboxEvent.objects, "create", _create)
        t = _tenant()
        c = _customer(t, balance_micros=5_000_000)
        UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            billed_cost_micros=6_000_000)  # crossing; stop.fired insert dies
        assert not StopSignalState.objects.filter(owner=c).exists()
        monkeypatch.setattr(OutboxEvent.objects, "create", orig_create)

        LiveLedgerService.reconcile_prepaid(c.id, t)
        fired = _events("stop.fired")
        assert fired.count() == 1
        assert fired.get().payload["episode_seq"] == 1
        assert fired.get().payload["re_announcement"] is False  # a fresh drive


@pytest.mark.django_db
class TestPin3RemintUnannounced:
    def test_dead_lettered_stop_fired_is_reminted_with_the_same_episode(self):
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        first = _stamp_of(c, FAMILY_FLOOR_STOP)
        _set_status(first, "failed")  # dead-lettered past the retry horizon

        assert patrol.remint_unannounced_signals(t) == 1
        fired = _events("stop.fired")
        assert fired.count() == 2
        fresh = fired.exclude(id=first).get()
        assert fresh.payload["re_announcement"] is True
        assert fresh.payload["episode_seq"] == 1  # same episode, not a new one
        assert fresh.payload["reason"] == "customer_wide_stop"
        assert _stamp_of(c, FAMILY_FLOOR_STOP) == fresh.id  # stamp updated
        # The dead-lettered row itself is untouched (alerting stays as is).
        assert OutboxEvent.objects.get(id=first).status == "failed"

    def test_no_mint_while_an_announcement_is_in_flight(self):
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        # Stamp is pending (in flight) -> the patrol leaves the row alone.
        assert patrol.remint_unannounced_signals(t) == 0
        assert _events("stop.fired").count() == 1
        # A re-mint's own stamp is also in flight: after one repair, the next
        # pass mints nothing — at most one live announcement per row.
        _set_status(_stamp_of(c, FAMILY_FLOOR_STOP), "failed")
        assert patrol.remint_unannounced_signals(t) == 1
        assert patrol.remint_unannounced_signals(t) == 0
        assert _events("stop.fired").count() == 2

    def test_announced_by_skipped_never_remints(self):
        # A tenant with no webhook config has chosen no push channel —
        # vacuous success, not a delivery failure.
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        _set_status(_stamp_of(c, FAMILY_FLOOR_STOP), "skipped")
        assert patrol.remint_unannounced_signals(t) == 0
        assert _events("stop.fired").count() == 1

    def test_processed_rows_are_left_alone(self):
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        _set_status(_stamp_of(c, FAMILY_FLOOR_STOP), "processed")
        assert patrol.remint_unannounced_signals(t) == 0


@pytest.mark.django_db
class TestPin4BottomLineOnly:
    def test_recovery_delivers_the_current_bottom_line_only(self):
        # Endpoint down for the whole cycle: the stop dead-letters, then the
        # clear (which moved the stamp) dead-letters too. The patrol mints
        # ONE cleared announcement — the current state — never the stale
        # intermediate stop.
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        stop_ev = _stamp_of(c, FAMILY_FLOOR_STOP)
        _set_status(stop_ev, "failed")
        Wallet.objects.filter(customer=c).update(balance_micros=2_000_000)
        StopSignalService.drive_clear(c.id, t, reason="balance_recovered",
                                      balance_micros=2_000_000)
        clear_ev = _stamp_of(c, FAMILY_FLOOR_STOP)
        _set_status(clear_ev, "failed")

        assert patrol.remint_unannounced_signals(t) == 1
        assert _events("stop.fired").count() == 1     # never replayed
        cleared = _events("stop.cleared")
        assert cleared.count() == 2
        fresh = cleared.exclude(id=clear_ev).get()
        assert fresh.payload["re_announcement"] is True
        assert fresh.payload["episode_seq"] == 1


@pytest.mark.django_db
class TestPin5SoftFamilyRidesTheSameRails:
    def test_dead_lettered_soft_crossed_remints(self):
        t = _tenant()
        c = _customer(t, balance_micros=-3_000_000, hard=5_000_000,
                      soft=2_000_000)
        StopSignalService.drive_soft_crossed(c.id, t,
                                             balance_micros=-3_000_000,
                                             soft_min_balance_micros=2_000_000)
        _set_status(_stamp_of(c, FAMILY_SOFT_FLOOR), "failed")
        assert patrol.remint_unannounced_signals(t) == 1
        crossed = _events("soft_floor.crossed")
        assert crossed.count() == 2
        fresh = crossed.order_by("created_at").last()
        assert fresh.payload["re_announcement"] is True
        assert fresh.payload["episode_seq"] == 1
        # The hard family was never touched.
        assert not StopSignalState.objects.filter(
            owner=c, family=FAMILY_FLOOR_STOP).exists()

    def test_families_remint_independently(self):
        t = _tenant()
        c = _customer(t, balance_micros=-6_000_000, hard=5_000_000,
                      soft=2_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        StopSignalService.drive_soft_crossed(c.id, t)
        _set_status(_stamp_of(c, FAMILY_FLOOR_STOP), "failed")
        _set_status(_stamp_of(c, FAMILY_SOFT_FLOOR), "failed")
        assert patrol.remint_unannounced_signals(t) == 2
        assert _events("stop.fired").count() == 2
        assert _events("soft_floor.crossed").count() == 2


@pytest.mark.django_db
class TestPin6TaskSweep:
    def test_crashed_kill_is_swept_and_announced_within_one_interval(self):
        # The kill transaction crashed after the tipping accumulate
        # committed: the task sits active, at-or-past its limit, with no
        # further traffic coming. The sweep drives the idempotent kill flow.
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        task = _task(t, c, limit=1_000, total=1_000)  # at the limit counts
        assert patrol.sweep_over_limit_tasks(t) == 1
        task.refresh_from_db()
        assert task.status == "killed"
        assert task.metadata["kill_reason"] == "task_limit"
        ev = _events("task.limit_exceeded").get()
        assert ev.payload["task_id"] == str(task.id)
        assert ev.payload["reason"] == "task_limit"
        assert ev.payload["re_announcement"] is False  # a fresh kill signal
        assert task.announce_outbox_id == ev.id
        # Idempotent: the next pass finds nothing active.
        assert patrol.sweep_over_limit_tasks(t) == 0
        assert _events("task.limit_exceeded").count() == 1

    def test_subtask_is_swept_alone_parent_unaffected(self):
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        parent = _task(t, c, limit=1_000_000, total=5_000)
        child = _task(t, c, limit=2_000, total=3_000, parent=parent)
        assert patrol.sweep_over_limit_tasks(t) == 1
        child.refresh_from_db()
        parent.refresh_from_db()
        assert child.status == "killed"
        assert parent.status == "active"
        ev = _events("subtask.limit_exceeded").get()
        assert ev.payload["subtask_id"] == str(child.id)
        assert ev.payload["parent_task_id"] == str(parent.id)
        assert ev.payload["reason"] == "subtask_limit"
        assert not _events("task.limit_exceeded").exists()

    def test_under_limit_and_unlimited_tasks_are_left_alone(self):
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        under = _task(t, c, limit=10_000, total=9_999)
        uncapped = _task(t, c, limit=None, total=10**9)
        assert patrol.sweep_over_limit_tasks(t) == 0
        under.refresh_from_db()
        uncapped.refresh_from_db()
        assert under.status == "active"
        assert uncapped.status == "active"

    def test_killed_but_unannounced_task_is_reminted(self):
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        dead = OutboxEvent.objects.create(
            event_type="task.limit_exceeded", payload={}, tenant_id=t.id,
            status="failed")
        task = _task(t, c, limit=1_000, total=2_000, status="killed",
                     stamp=dead.id, meta={"kill_reason": "task_limit"})
        assert patrol.remint_unannounced_kills(t) == 1
        ev = _events("task.limit_exceeded").exclude(id=dead.id).get()
        assert ev.payload["re_announcement"] is True
        assert ev.payload["task_id"] == str(task.id)
        assert ev.payload["reason"] == "task_limit"
        assert ev.payload["total_provider_cost_micros"] == 2_000
        task.refresh_from_db()
        assert task.announce_outbox_id == ev.id
        # The fresh stamp is in flight: the next pass mints nothing.
        assert patrol.remint_unannounced_kills(t) == 0

    def test_killed_subtask_remints_the_subtask_event(self):
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        parent = _task(t, c, limit=1_000_000)
        dead = OutboxEvent.objects.create(
            event_type="subtask.limit_exceeded", payload={}, tenant_id=t.id,
            status="failed")
        child = _task(t, c, limit=2_000, total=3_000, status="killed",
                      parent=parent, stamp=dead.id,
                      meta={"kill_reason": "subtask_limit"})
        assert patrol.remint_unannounced_kills(t) == 1
        ev = _events("subtask.limit_exceeded").exclude(id=dead.id).get()
        assert ev.payload["re_announcement"] is True
        assert ev.payload["subtask_id"] == str(child.id)
        assert ev.payload["parent_task_id"] == str(parent.id)

    def test_silent_cascaded_kills_are_never_reminted(self):
        # A cascade-killed child carries no stamp by design — the parent's
        # event was the one signal. Null stamp on a killed task = silent,
        # not unannounced.
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        parent = _task(t, c, limit=1_000_000, status="killed",
                       meta={"kill_reason": "task_limit"})
        _task(t, c, status="killed", parent=parent,
              meta={"kill_reason": "parent_killed"})
        assert patrol.remint_unannounced_kills(t) == 0
        assert not _events("subtask.limit_exceeded").exists()
        assert not _events("task.limit_exceeded").exists()


@pytest.mark.django_db
class TestPatrolBeatAndCounters:
    def test_patrol_rides_the_hourly_reconcile_and_records_outcomes(self):
        t = _tenant()
        # Owner A: orphaned flag, healthy balance -> one flag re-alignment.
        a = _customer(t, balance_micros=5_000_000, ext="a")
        _client().set(_stop_key(a.id), "customer_wide_stop")
        # Owner B: durably stopped, announcement dead-lettered -> one re-mint.
        b = _customer(t, balance_micros=-1_000_000, ext="b")
        StopSignalService.drive_stop(b.id, t, reason="customer_wide_stop")
        LiveLedgerService.ensure_stop_flag(b.id, "customer_wide_stop")
        _set_status(_stamp_of(b, FAMILY_FLOOR_STOP), "failed")
        # Owner C: an over-limit task the kill flow never reached -> one sweep.
        c = _customer(t, balance_micros=1_000_000, ext="c")
        _task(t, c, limit=1_000, total=5_000)

        reconcile_live_ledgers()

        stats = get_patrol_stats(tenant_id=t.id)
        assert stats == {"patrol_reminted_7d": 1,
                         "patrol_flag_realigned_7d": 1,
                         "patrol_sweep_killed_7d": 1}
        assert PatrolOutcome.objects.filter(tenant=t).count() == 3
        # Global (no tenant filter) sums the same rows.
        assert get_patrol_stats()["patrol_reminted_7d"] == 1

    def test_off_tenants_are_never_patrolled(self):
        t = _tenant(enf="off")
        c = _customer(t, balance_micros=1_000_000)
        task = _task(t, c, limit=1_000, total=5_000)
        reconcile_live_ledgers()
        task.refresh_from_db()
        assert task.status == "active"
        assert not PatrolOutcome.objects.filter(tenant=t).exists()

    def test_stats_shape_is_zeroed_when_quiet(self):
        assert get_patrol_stats() == {"patrol_reminted_7d": 0,
                                      "patrol_flag_realigned_7d": 0,
                                      "patrol_sweep_killed_7d": 0}
