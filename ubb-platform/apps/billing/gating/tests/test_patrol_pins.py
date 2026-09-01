"""#44 acceptance pins — the hourly patrol (delivery spec §C/§F).

Late, never lost, independent of traffic: the patrol jobs join the hourly
reconcile pass (no new scheduled task, enforcing tenants only) and guarantee
that a real crossing always eventually produces its signal (missed-transition
drive, both families), the fast Redis flag matches durable truth, unannounced
signal rows are re-minted as fresh current-state events
(``re_announcement: true``, bottom-line only), and active tasks sitting
at-or-past their provider-cost limit are swept into the idempotent kill flow.
Patrol outcomes land as counters read through ``get_patrol_stats``; the shared
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

⚠ A RE-MINT PUBLISHES WHAT THE ROW SAYS NOW, and since the terminal-event split
that includes WHICH of the four events it is (#140 §4.3). The patrol repairs a
delivery it did not make, so it is the one emitter with no caller to take the
name from — which makes it the only place *the name is the state entered* is
falsifiable. `TestTheRemintNamesTheStateTheRowCarries` below is that claim's
whole proof (#420): the four states at both altitudes, each stood up on a row
that disagrees with the name it already sent, and the two pins holding the
patrol to having no memory of that name. Pin 6 keeps the delivery MECHANICS —
which rows are candidates, when a stamp is left alone, where a repair reads the
mechanism from.
"""
import pytest
from unittest.mock import patch

from apps.billing.gating import patrol
from apps.billing.gating.models import PatrolOutcome, StopSignalState
from apps.billing.gating.services.live_counter import Door, LiveCounter
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
from apps.platform.events.schemas import (
    SubtaskExpired, SubtaskKilled, TaskExpired, TaskKilled)
from apps.platform.work import reasons
from apps.platform.work.models import Task
from apps.platform.work.services import STOP_CAUSE_KEY, STOP_MECHANISM_KEY
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    TASK_STATUS_EXPIRED, TASK_STATUS_KILLED,
    TRIGGER_SOURCE_ENFORCEMENT_PATROL, TRIGGER_SOURCE_STALE_REAPER,
    TRIGGER_SOURCE_USAGE_INGEST)


#: All four terminal stop events, so a case can rule out the other THREE
#: rather than a chosen rival. Both mistakes the split exists to make
#: impossible are in here: sending the other STATE at this altitude, and
#: sending this state at the other.
THE_FOUR = (TaskKilled, TaskExpired, SubtaskKilled, SubtaskExpired)


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
        Door.plant_stop(c.id, "customer_wide_stop", ttl=False)
        assert LiveCounter.read(c.id, t)["stop"] is True
        out = LiveCounter.reconcile(c.id, t)
        assert LiveCounter.read(c.id, t)["stop"] is False
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
        Door.plant_stop(c.id, "customer_wide_stop", ttl=False)  # survived flag
        LiveCounter.reconcile(c.id, t)
        fired = _events("stop.fired")
        assert fired.count() == 1
        assert fired.get().payload["episode_seq"] == 1
        assert LiveCounter.read(c.id, t)["stop"] is True

    def test_missing_flag_for_a_durably_stopped_owner_is_realigned(self):
        # The inverse orphan: durable truth says stopped, the flag is gone
        # (Redis flush). The patrol re-sets it from the durable family state.
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        assert Door.stop_reason(c.id) is None  # durable lane, no flag
        out = LiveCounter.reconcile(c.id, t)
        assert LiveCounter.read(c.id, t)["stop"] is True
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
        from apps.metering.pricing.tests._helpers import (
            a_rule_that_prices_what_it_measures, priced_at)
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
        # The crossing amount is what the tenant's rule charges (#365).
        a_rule_that_prices_what_it_measures(t)
        UsageService.record_usage(
            tenant=t, customer=c, idempotency_key="k1",
            measurements=priced_at(6_000_000))  # crossing; stop.fired insert dies
        assert not StopSignalState.objects.filter(owner=c).exists()
        monkeypatch.setattr(OutboxEvent.objects, "create", orig_create)

        LiveCounter.reconcile(c.id, t)
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

    def test_administrative_close_never_rides_the_wire(self):
        # A row silently closed by an enforcement-mode transition (#39: a
        # config flip is not a re-cross) has nothing to announce — even when
        # its last real announcement dead-lettered, the patrol skips it
        # rather than put the administrative reason on a StopCleared.
        from apps.billing.gating.services.stop_signal_service import (
            CLEAR_ENFORCEMENT_MODE_TRANSITION, STATE_CLEARED)
        t = _tenant()
        c = _customer(t, balance_micros=-1_000_000)
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        _set_status(_stamp_of(c, FAMILY_FLOOR_STOP), "failed")
        StopSignalState.objects.filter(owner=c).update(
            state=STATE_CLEARED, reason=CLEAR_ENFORCEMENT_MODE_TRANSITION)
        assert patrol.remint_unannounced_signals(t) == 0
        assert not _events("stop.cleared").exists()
        assert _events("stop.fired").count() == 1


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
        ev = _events(TaskKilled.EVENT_TYPE).get()
        assert ev.payload["task_id"] == str(task.id)
        assert ev.payload["reason_code"] == "task_limit"
        # WHICH MECHANISM APPLIED IT (#412). The sweep found a unit already
        # over its ceiling that no usage report had stopped, and saying so is
        # the only way a subscriber tells this apart from the ingest lane
        # reaching the identical reason.
        assert ev.payload["trigger_source"] == TRIGGER_SOURCE_ENFORCEMENT_PATROL
        assert ev.payload["re_announcement"] is False  # a fresh kill signal
        assert task.announce_outbox_id == ev.id
        # ...AND IT IS RECORDED ON THE ROW, which is what lets a later re-mint
        # of this same unit name the mechanism instead of going silent. Keyed
        # by the constant the writer uses, not by the word: the cases already
        # here spell `kill_reason` and are left alone, but a key this commit
        # makes load-bearing is addressed through the module that owns it.
        assert (task.metadata[STOP_MECHANISM_KEY]
                == TRIGGER_SOURCE_ENFORCEMENT_PATROL)
        # Idempotent: the next pass finds nothing active.
        assert patrol.sweep_over_limit_tasks(t) == 0
        assert _events(TaskKilled.EVENT_TYPE).count() == 1

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
        ev = _events(SubtaskKilled.EVENT_TYPE).get()
        assert ev.payload["subtask_id"] == str(child.id)
        assert ev.payload["parent_task_id"] == str(parent.id)
        assert ev.payload["reason_code"] == "subtask_limit"
        assert not _events(TaskKilled.EVENT_TYPE).exists()

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
            event_type=TaskKilled.EVENT_TYPE, payload={}, tenant_id=t.id,
            status="failed")
        task = _task(t, c, limit=1_000, total=2_000, status="killed",
                     stamp=dead.id, meta={"kill_reason": "task_limit"})
        assert patrol.remint_unannounced_kills(t) == 1
        ev = _events(TaskKilled.EVENT_TYPE).exclude(id=dead.id).get()
        assert ev.payload["re_announcement"] is True
        assert ev.payload["task_id"] == str(task.id)
        assert ev.payload["reason_code"] == "task_limit"
        # ⚠ AND IT NAMES NO MECHANISM, BECAUSE THIS ROW HOLDS NONE — which is
        # a different claim from the one this case made before the terminal
        # events split. A re-mint applies no transition; it repairs the
        # delivery of a stop some other lane made, so it READS the mechanism
        # off the row rather than naming itself. This fixture stands a row up
        # with only a cause recorded, which is what a pre-split row looks
        # like, and empty is then the honest answer. The case below is the
        # other half, and the two must differ or neither is evidence.
        assert ev.payload["trigger_source"] == ""
        assert ev.payload["total_provider_cost_micros"] == 2_000
        task.refresh_from_db()
        assert task.announce_outbox_id == ev.id
        # The fresh stamp is in flight: the next pass mints nothing.
        assert patrol.remint_unannounced_kills(t) == 0

    def test_a_remint_names_the_mechanism_the_stopping_lane_recorded(self):
        """The other half of the pair above: where the row DOES record which
        lane stopped the work, the repaired delivery says so.

        This is what the mechanism is written onto the row for. A subscriber
        receiving a re-mint learns the same thing the original announcement
        said, rather than a blank that reads as *UBB does not know* — and the
        patrol never names ITSELF here, because it stopped nothing.
        """
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        dead = OutboxEvent.objects.create(
            event_type=TaskKilled.EVENT_TYPE, payload={}, tenant_id=t.id,
            status="failed")
        _task(t, c, limit=1_000, total=2_000, status="killed", stamp=dead.id,
              meta={"kill_reason": "task_limit",
                    STOP_MECHANISM_KEY: TRIGGER_SOURCE_USAGE_INGEST})

        assert patrol.remint_unannounced_kills(t) == 1

        ev = _events(TaskKilled.EVENT_TYPE).exclude(id=dead.id).get()
        assert ev.payload["trigger_source"] == TRIGGER_SOURCE_USAGE_INGEST

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
        assert not _events(SubtaskKilled.EVENT_TYPE).exists()
        assert not _events(TaskKilled.EVENT_TYPE).exists()


@pytest.mark.django_db
class TestTheRemintNamesTheStateTheRowCarries:
    """⚠ THE ONE PLACE *THE NAME IS THE STATE ENTERED* IS FALSIFIABLE (#420).

    Every other emitter of the four terminal stop events applies the stop it
    announces, so an implementation that took the name from its CALLER would
    look exactly like one that reads it off the record. The patrol's re-mint
    has no such caller: it repairs a delivery some other lane made and applies
    no transition of its own, so the only thing it can consult is the state
    the row carries now. #140 §4.3's last sentence handed it that obligation.

    ⚠ SO EVERY CASE HERE STANDS THE ROW UP DISAGREEING WITH ITS OWN DEAD
    STAMP: the row reads `killed` while the failed announcement names the
    expiry, or the other way about. A case whose two halves agreed would be
    passed by an emitter that echoed the name it found, which is the one
    implementation this class exists to rule out.

    ⚠ AND THE DISAGREEMENT IS REACHABLE RATHER THAN CONTRIVED. Migration
    `0008` routed each queued row bearing a retired name on the REASON its own
    payload carried, defaulting to the spend stop wherever that reason was
    absent or unrecognised — it states the default and argues that it is the
    safer of the two errors. This patrol routes on the STATE. A row whose
    recorded reason and recorded state point different ways is one the two
    rules answer differently, and the state is what wins, because the marker
    this event carries claims a repaired delivery of the CURRENT state and
    nothing weaker.

    ⚠ WHAT IS NOT REACHABLE IS A SECOND TRANSITION. `TaskService._flip`
    refuses terminal-to-anything, so no lane rewrites a stopped row's state
    and the pair comes apart only the way above. These fixtures therefore
    write the state and the name already sent directly, rather than driving a
    transition that does not exist — said here because a reader who assumed
    otherwise would go looking for the lane that does it.

    The first four cases are the 2×2 — {a whole unit of work, contained work}
    × {killed, expired} — and each asserts the SET of terminal events that
    fired is exactly its own, so none can be satisfied by an emitter that
    sends every name it knows. Two of them arrive from `TestPin6TaskSweep`
    (#419's `test_an_expired_unit_remints_the_expiry_and_not_the_spend_stop`
    and `test_killed_subtask_remints_the_subtask_event`), moved here so the
    four read as the one matrix they are; what stayed behind are the pins
    about the patrol's delivery MECHANICS rather than about which name it
    sends.
    """

    def _stopped_with_a_dead_announcement(self, t, c, *, status, announced,
                                          reason, mechanism, parent=None):
        """A stopped piece of work whose announcement dead-lettered, with the
        row's state and the name that actually went on the wire stood up as
        two separate facts.

        `announced` is what was sent; `status` is what the row says now. Every
        caller here passes a pair that DISAGREE.
        """
        dead = OutboxEvent.objects.create(
            event_type=announced.EVENT_TYPE, payload={}, tenant_id=t.id,
            status="failed")
        task = _task(t, c, total=2_000, status=status, parent=parent,
                     stamp=dead.id,
                     meta={STOP_CAUSE_KEY: reason,
                           STOP_MECHANISM_KEY: mechanism})
        return task, dead

    def _assert_reminted(self, task, event, *, dead):
        """The patrol minted exactly `event`, marked it a repair, and moved
        the row's stamp onto it.

        ⚠ THE ABSENCE IS ASSERTED OVER ALL FOUR rather than over a chosen
        rival (#419's lesson): ruling out only the other ALTITUDE proves the
        containment rule and says nothing about the split, and `*.killed`
        against `*.expired` is the whole subject. The dead row is excluded by
        ID rather than by name, because it deliberately carries one of the
        four names itself.
        """
        minted = _events(event.EVENT_TYPE).exclude(id=dead.id).get()
        assert minted.payload["re_announcement"] is True
        fired = {other.EVENT_TYPE for other in THE_FOUR
                 if _events(other.EVENT_TYPE).exclude(id=dead.id).exists()}
        assert fired == {event.EVENT_TYPE}
        task.refresh_from_db()
        assert task.announce_outbox_id == minted.id
        return minted

    def test_a_whole_unit_of_work_that_was_killed_remints_the_kill(self):
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        task, dead = self._stopped_with_a_dead_announcement(
            t, c, status=TASK_STATUS_KILLED, announced=TaskExpired,
            reason=reasons.TASK_LIMIT, mechanism=TRIGGER_SOURCE_USAGE_INGEST)

        assert patrol.remint_unannounced_kills(t) == 1

        minted = self._assert_reminted(task, TaskKilled, dead=dead)
        assert minted.payload["task_id"] == str(task.id)
        # The cause and the mechanism are read back off the row too, for the
        # same reason the name is: a repair states what the record holds.
        assert minted.payload["reason_code"] == reasons.TASK_LIMIT
        assert minted.payload["trigger_source"] == TRIGGER_SOURCE_USAGE_INGEST

    def test_a_whole_unit_of_work_that_expired_remints_the_expiry(self):
        """A piece of work a sweeper expired re-announces the expiry — never
        the spend stop, which would page an on-call engineer about a ceiling
        that was never crossed. That is the split's entire point read from the
        repair side.
        """
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        task, dead = self._stopped_with_a_dead_announcement(
            t, c, status=TASK_STATUS_EXPIRED, announced=TaskKilled,
            reason=reasons.SILENCE_WINDOW,
            mechanism=TRIGGER_SOURCE_STALE_REAPER)

        assert patrol.remint_unannounced_kills(t) == 1

        minted = self._assert_reminted(task, TaskExpired, dead=dead)
        assert minted.payload["task_id"] == str(task.id)
        assert minted.payload["reason_code"] == reasons.SILENCE_WINDOW
        assert minted.payload["trigger_source"] == TRIGGER_SOURCE_STALE_REAPER

    def test_contained_work_that_was_killed_remints_the_contained_kill(self):
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        parent = _task(t, c, limit=1_000_000)
        child, dead = self._stopped_with_a_dead_announcement(
            t, c, status=TASK_STATUS_KILLED, announced=SubtaskExpired,
            reason=reasons.SUBTASK_LIMIT,
            mechanism=TRIGGER_SOURCE_USAGE_INGEST, parent=parent)

        assert patrol.remint_unannounced_kills(t) == 1

        minted = self._assert_reminted(child, SubtaskKilled, dead=dead)
        assert minted.payload["subtask_id"] == str(child.id)
        assert minted.payload["parent_task_id"] == str(parent.id)
        # A repair is not a fan-out: the piece is re-announced alone and the
        # unit containing it keeps running, so it has nothing to announce.
        parent.refresh_from_db()
        assert parent.announce_outbox_id is None

    def test_contained_work_that_expired_remints_the_contained_expiry(self):
        """The fourth cell, and the one no case reached before this ticket."""
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        parent = _task(t, c, limit=1_000_000)
        child, dead = self._stopped_with_a_dead_announcement(
            t, c, status=TASK_STATUS_EXPIRED, announced=SubtaskKilled,
            reason=reasons.SILENCE_WINDOW,
            mechanism=TRIGGER_SOURCE_STALE_REAPER, parent=parent)

        assert patrol.remint_unannounced_kills(t) == 1

        minted = self._assert_reminted(child, SubtaskExpired, dead=dead)
        assert minted.payload["subtask_id"] == str(child.id)
        assert minted.payload["parent_task_id"] == str(parent.id)
        assert minted.payload["trigger_source"] == TRIGGER_SOURCE_STALE_REAPER
        parent.refresh_from_db()
        assert parent.announce_outbox_id is None

    @pytest.mark.parametrize("announced", THE_FOUR,
                             ids=[event.EVENT_TYPE for event in THE_FOUR])
    def test_the_name_already_sent_is_not_an_input(self, announced):
        """One expired piece of work, run past the patrol once per name its
        dead stamp could possibly carry, and the answer never moves.

        An implementation that re-delivered the name it found would answer
        four different ways here and agree with the matrix above in exactly
        one of them. This is what turns *the patrol does not remember what it
        sent* into a measurement rather than a reading of the source. The
        names come from `THE_FOUR` rather than being written out again, so
        this case cannot drift from the rival set the matrix rules out.
        """
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        task, dead = self._stopped_with_a_dead_announcement(
            t, c, status=TASK_STATUS_EXPIRED, announced=announced,
            reason=reasons.SILENCE_WINDOW,
            mechanism=TRIGGER_SOURCE_STALE_REAPER)

        assert patrol.remint_unannounced_kills(t) == 1

        self._assert_reminted(task, TaskExpired, dead=dead)

    def test_a_remint_records_nothing_about_the_name_it_replaced(self):
        """The *stores* half of the same obligation, and it is checkable:
        were the patrol keeping a note of what it had sent, the note would
        have to land on this row.

        Every column but the stamp and its timestamp is unchanged across the
        repair — `metadata` included, which is where UBB's own bookkeeping
        about a stopped piece of work goes. Held to the MODEL's own field list
        rather than to a written-out set, so a column added to a stopped row
        arrives here rather than sliding past.
        """
        t = _tenant()
        c = _customer(t, balance_micros=1_000_000)
        task, _dead = self._stopped_with_a_dead_announcement(
            t, c, status=TASK_STATUS_EXPIRED, announced=TaskKilled,
            reason=reasons.SILENCE_WINDOW,
            mechanism=TRIGGER_SOURCE_STALE_REAPER)
        columns = [field.attname for field in Task._meta.concrete_fields]
        before = {name: getattr(task, name) for name in columns}

        assert patrol.remint_unannounced_kills(t) == 1

        task.refresh_from_db()
        moved = {name for name in columns
                 if getattr(task, name) != before[name]}
        assert moved == {Task._meta.get_field("announce_outbox_id").attname,
                         Task._meta.get_field("updated_at").attname}

    def test_the_remint_path_never_reads_the_name_it_already_sent(self):
        """The *reads* half, and the half no behavioural case can reach:
        there is nothing for the patrol to echo FROM.

        The parametrized case above proves the name already sent does not
        change the answer. This proves the re-mint path never so much as looks
        at it — the queued row is consulted for its delivery STATUS and for
        nothing else — which is what keeps that result from being a
        coincidence of the current code path.

        ⚠ THE FORBIDDEN NAME AND THE GUARD NAMES ARE READ OFF THE MODELS
        rather than spelled, so a column rename moves this pin instead of
        quietly emptying it. And the guard is the point: an absence asserted
        over a walk that had stopped seeing anything would pass forever, so
        the same walk must still find the two fields this path DOES consult.
        """
        import ast
        import inspect

        from apps.platform.events import announcements

        the_name_already_sent = OutboxEvent._meta.get_field("event_type").name
        consulted = {OutboxEvent._meta.get_field("status").name,
                     Task._meta.get_field("announce_outbox_id").name}
        the_path = {"remint_unannounced_kills", "_remint_kill",
                    "announcement_status"}

        walked, names = set(), set()
        for module in (patrol, announcements):
            for node in ast.walk(ast.parse(inspect.getsource(module))):
                if (not isinstance(node, ast.FunctionDef)
                        or node.name not in the_path):
                    continue
                walked.add(node.name)
                for inner in ast.walk(node):
                    # The three ways a column is named in this path: an
                    # attribute read or write, a queryset keyword (whose
                    # lookup suffix is not part of the name), and a string
                    # handed to `values_list` / `OuterRef` / `update_fields`.
                    if isinstance(inner, ast.Attribute):
                        names.add(inner.attr)
                    elif isinstance(inner, ast.keyword) and inner.arg:
                        names.add(inner.arg.split("__")[0])
                    elif isinstance(inner, ast.Constant) and isinstance(
                            inner.value, str):
                        names.add(inner.value.split("__")[0])

        assert walked == the_path      # the walk found the path...
        assert consulted <= names      # ...and can see a column when there is one
        assert the_name_already_sent not in names


@pytest.mark.django_db
class TestPatrolBeatAndCounters:
    def test_patrol_rides_the_hourly_reconcile_and_records_outcomes(self):
        t = _tenant()
        # Owner A: orphaned flag, healthy balance -> one flag re-alignment.
        a = _customer(t, balance_micros=5_000_000, ext="a")
        Door.plant_stop(a.id, "customer_wide_stop", ttl=False)
        # Owner B: durably stopped, announcement dead-lettered -> one re-mint.
        b = _customer(t, balance_micros=-1_000_000, ext="b")
        StopSignalService.drive_stop(b.id, t, reason="customer_wide_stop")
        LiveCounter.ensure_stop_flag(b.id, "customer_wide_stop")
        _set_status(_stamp_of(b, FAMILY_FLOOR_STOP), "failed")
        # Owner C: an over-limit task the kill flow never reached -> one sweep.
        c = _customer(t, balance_micros=1_000_000, ext="c")
        _task(t, c, limit=1_000, total=5_000)

        reconcile_live_ledgers()

        stats = get_patrol_stats(tenant_id=t.id)
        assert stats == {"patrol_reminted_7d": 1,
                         "patrol_flag_realigned_7d": 1,
                         "patrol_sweep_killed_7d": 1,
                         "patrol_repaired_7d": 0,
                         "patrol_repaired_micros_7d": 0,
                         "patrol_repair_lapsed_7d": 0}
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
                                      "patrol_sweep_killed_7d": 0,
                                      "patrol_repaired_7d": 0,
                                      "patrol_repaired_micros_7d": 0,
                                      "patrol_repair_lapsed_7d": 0}
