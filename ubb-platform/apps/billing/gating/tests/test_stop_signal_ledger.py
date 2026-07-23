"""#39 — the StopSignalState transition guard (spec §D/§E).

Unit pins for the single emission choke point: winning transitions emit
exactly one stop.fired / stop.cleared per episode, episode ids increment and
pair up, and the suspension fold rides the winning stop transition with the
mode gates intact (prepaid = Tier-1 baseline in every enforcement-on mode,
postpaid = enforcing only).
"""
import pytest

from apps.billing.gating.models import StopSignalState
from apps.billing.gating.services.stop_signal_service import (
    CLEAR_BALANCE_RECOVERED,
    CLEAR_RECONCILED,
    FAMILY_FLOOR_STOP,
    StopSignalService,
)
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


def _tenant(mode="prepaid", enf="enforcing"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


def _events(event_type, owner_key="owner_id", owner_id=None):
    qs = OutboxEvent.objects.filter(event_type=event_type)
    if owner_id is not None:
        qs = qs.filter(**{f"payload__{owner_key}": str(owner_id)})
    return qs


@pytest.mark.django_db
class TestStopTransition:
    def test_first_stop_wins_opens_episode_1_and_emits(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        won = StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop",
                                           balance_micros=-6_000_000)
        assert won == 1
        row = StopSignalState.objects.get(owner=c, family=FAMILY_FLOOR_STOP)
        assert row.state == "stopped" and row.episode_seq == 1
        assert row.reason == "customer_wide_stop"
        fired = _events("stop.fired", owner_id=c.id)
        assert fired.count() == 1
        assert fired.get().payload["episode_seq"] == 1

    def test_repeat_stop_loses_and_emits_nothing(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        assert StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop") is None
        assert _events("stop.fired", owner_id=c.id).count() == 1
        assert _events("billing.customer_suspended", "customer_id", c.id).count() == 1

    def test_clear_wins_once_and_carries_the_closed_episode(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        closed = StopSignalService.drive_clear(c.id, t, reason=CLEAR_BALANCE_RECOVERED,
                                               balance_micros=2_000_000)
        assert closed == 1
        cleared = _events("stop.cleared", owner_id=c.id)
        assert cleared.count() == 1
        payload = cleared.get().payload
        assert payload["episode_seq"] == 1
        assert payload["balance_micros"] == 2_000_000
        assert payload["reason"] == CLEAR_BALANCE_RECOVERED
        # A clear that didn't win the transition emits nothing (spec §E).
        assert StopSignalService.drive_clear(c.id, t, reason=CLEAR_RECONCILED) is None
        assert _events("stop.cleared", owner_id=c.id).count() == 1

    def test_clear_without_any_stop_history_is_a_silent_no_op(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert StopSignalService.drive_clear(c.id, t, reason=CLEAR_RECONCILED) is None
        assert not StopSignalState.objects.filter(owner=c).exists()
        assert _events("stop.cleared", owner_id=c.id).count() == 0

    def test_stop_clear_stop_increments_the_episode(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop") == 1
        assert StopSignalService.drive_clear(c.id, t, reason=CLEAR_BALANCE_RECOVERED) == 1
        assert StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop") == 2
        seqs = [e.payload["episode_seq"] for e in _events("stop.fired", owner_id=c.id).order_by("created_at")]
        assert seqs == [1, 2]

    def test_families_have_independent_state_and_episodes(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        # soft_floor (#40) has its own transitions — they must not share
        # state or episode sequence with floor_stop.
        won = StopSignalService.drive_soft_crossed(c.id, t, balance_micros=-1)
        assert won == 1
        states = {r.family: r.state for r in StopSignalState.objects.filter(owner=c)}
        assert states == {"floor_stop": "stopped", "soft_floor": "stopped"}
        assert StopSignalService.drive_soft_cleared(c.id, t, reason=CLEAR_RECONCILED) == 1
        assert StopSignalState.objects.get(owner=c, family=FAMILY_FLOOR_STOP).state == "stopped"


@pytest.mark.django_db
class TestSuspensionFold:
    def test_prepaid_winner_suspends_min_balance_exceeded(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop",
                                     balance_micros=-6_000_000)
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == "min_balance_exceeded"
        suspended = _events("billing.customer_suspended", "customer_id", c.id)
        assert suspended.count() == 1
        assert suspended.get().payload["balance_micros"] == -6_000_000

    def test_postpaid_enforcing_suspends_budget_exceeded(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == "budget_exceeded"

    def test_non_active_owner_gets_the_signal_but_no_status_flip(self):
        # An admin/fraud suspension is never overwritten by the money path —
        # the stop signal still fires (the crossing is real).
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1", status="suspended",
                                    suspension_reason="fraud")
        assert StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop") == 1
        c.refresh_from_db()
        assert c.suspension_reason == "fraud"
        assert _events("stop.fired", owner_id=c.id).count() == 1
        assert _events("billing.customer_suspended", "customer_id", c.id).count() == 0


@pytest.mark.django_db
class TestEmissionAtomicity:
    """#43 §A at the service seam: every family rides the same savepoint
    contract pinned for stop.fired in test_live_counter.py's pin 2 — a failed
    event INSERT takes the transition down with it (never "transitioned but
    unqueued") and leaves the ambient transaction usable for the money path.
    """

    @staticmethod
    def _fail_insert_of(monkeypatch, event_type):
        """Make the outbox INSERT for event_type fail with a REAL SQL error
        (SELECT 1/0 -> DataError) — only a genuine DB error aborts the
        ambient transaction, so only this shape catches a missing savepoint."""
        from django.db import connection
        from apps.platform.events.models import OutboxEvent

        orig_create = OutboxEvent.objects.create

        def _create(**kwargs):
            if kwargs.get("event_type") == event_type:
                with connection.cursor() as cur:
                    cur.execute("SELECT 1/0")
            return orig_create(**kwargs)

        monkeypatch.setattr(OutboxEvent.objects, "create", _create)

    def test_failed_soft_crossed_insert_rolls_the_soft_transition_back(self, monkeypatch):
        from django.db import transaction

        self._fail_insert_of(monkeypatch, "soft_floor.crossed")
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        with transaction.atomic():
            with pytest.raises(Exception):
                StopSignalService.drive_soft_crossed(c.id, t, balance_micros=-1)
            # The ambient transaction survived the savepoint rollback — the
            # caller's next statement will not hit "transaction is aborted".
            assert Customer.objects.filter(id=c.id).exists()
        assert not StopSignalState.objects.filter(owner=c).exists()
        assert _events("soft_floor.crossed", owner_id=c.id).count() == 0


@pytest.mark.django_db
class TestAnnouncementStamps:
    """#43 §B — every winning transition stamps ``announce_outbox_id`` with
    the outbox id of the event it emitted, inside the same atomic unit; a
    losing transition never touches the stamp. Fresh crossings go out with
    ``re_announcement: false`` (true is reserved for the patrol's re-mints,
    #44)."""

    def test_winning_stop_stamps_the_stop_fired_event(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        row = StopSignalState.objects.get(owner=c, family=FAMILY_FLOOR_STOP)
        fired = _events("stop.fired", owner_id=c.id).get()
        assert row.announce_outbox_id == fired.id
        assert fired.payload["re_announcement"] is False

    def test_losing_stop_leaves_the_stamp_alone(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        stamp = StopSignalState.objects.get(
            owner=c, family=FAMILY_FLOOR_STOP).announce_outbox_id
        assert StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop") is None
        assert StopSignalState.objects.get(
            owner=c, family=FAMILY_FLOOR_STOP).announce_outbox_id == stamp

    def test_clear_moves_the_stamp_to_the_cleared_event(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        fired_id = _events("stop.fired", owner_id=c.id).get().id
        StopSignalService.drive_clear(c.id, t, reason=CLEAR_BALANCE_RECOVERED)
        row = StopSignalState.objects.get(owner=c, family=FAMILY_FLOOR_STOP)
        cleared = _events("stop.cleared", owner_id=c.id).get()
        assert row.announce_outbox_id == cleared.id
        assert row.announce_outbox_id != fired_id
        assert cleared.payload["re_announcement"] is False

    def test_soft_pair_stamps_its_own_family_row(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(c.id, t, reason="customer_wide_stop")
        hard_stamp = StopSignalState.objects.get(
            owner=c, family=FAMILY_FLOOR_STOP).announce_outbox_id
        StopSignalService.drive_soft_crossed(c.id, t, balance_micros=-1)
        soft = StopSignalState.objects.get(owner=c, family="soft_floor")
        crossed = _events("soft_floor.crossed", owner_id=c.id).get()
        assert soft.announce_outbox_id == crossed.id
        assert crossed.payload["re_announcement"] is False
        StopSignalService.drive_soft_cleared(c.id, t, reason=CLEAR_RECONCILED)
        soft.refresh_from_db()
        assert soft.announce_outbox_id == _events(
            "soft_floor.cleared", owner_id=c.id).get().id
        # The hard family's stamp never moved.
        assert StopSignalState.objects.get(
            owner=c, family=FAMILY_FLOOR_STOP).announce_outbox_id == hard_stamp
