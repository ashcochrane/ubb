"""#39 — the StopSignalState transition guard (spec §D/§E).

Unit pins for the single emission choke point: winning transitions emit
exactly one stop.fired / stop.cleared per episode, episode ids increment and
pair up, and the suspension fold rides the winning stop transition with the
mode gates intact (prepaid = Tier-1 baseline in every enforcement-on mode,
postpaid = enforcing only).
"""
import pytest
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing.gating.models import CustomerSpendPool, StopSignalState
from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.gating.services.stop_signal_service import (
    CLEAR_BALANCE_RECOVERED,
    CLEAR_RECONCILED,
    LINE_SOFT_FLOOR,
    StopSignalService,
    control_id_of,
    family_of_line,
)
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons
from apps.billing.gating.tests._helpers import drive_a_stop, stop_line
from core.vocabulary import (
    CONTROL_FAMILY_CUSTOMER_SPEND_POOL, CONTROL_FAMILY_WALLET_POLICY)


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
        won = drive_a_stop(c.id, t,
                                           balance_micros=-6_000_000)
        assert won == 1
        row = StopSignalState.objects.get(owner=c, reason=stop_line(t))
        assert row.state == "stopped" and row.episode_seq == 1
        assert row.reason == stop_line(t)
        fired = _events("stop.fired", owner_id=c.id)
        assert fired.count() == 1
        assert fired.get().payload["episode_seq"] == 1

    def test_repeat_stop_loses_and_emits_nothing(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        drive_a_stop(c.id, t)
        assert drive_a_stop(c.id, t) is None
        assert _events("stop.fired", owner_id=c.id).count() == 1
        assert _events("customer.suspended", "customer_id", c.id).count() == 1

    def test_clear_wins_once_and_carries_the_closed_episode(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        drive_a_stop(c.id, t)
        closed = StopSignalService.drive_clear(c.id, t, line=stop_line(t), clear_reason=CLEAR_BALANCE_RECOVERED,
                                               balance_micros=2_000_000)
        assert closed == 1
        cleared = _events("stop.cleared", owner_id=c.id)
        assert cleared.count() == 1
        payload = cleared.get().payload
        assert payload["episode_seq"] == 1
        assert payload["balance_micros"] == 2_000_000
        # The pair says WHICH stop lifted (#458); why it lifted is the
        # ledger row's own bookkeeping.
        assert payload["reason_code"] == stop_line(t)
        assert StopSignalState.objects.get(
            owner=c, reason=stop_line(t)).clear_reason == CLEAR_BALANCE_RECOVERED
        # A clear that didn't win the transition emits nothing (spec §E).
        assert StopSignalService.drive_clear(c.id, t, line=stop_line(t), clear_reason=CLEAR_RECONCILED) is None
        assert _events("stop.cleared", owner_id=c.id).count() == 1

    def test_clear_without_any_stop_history_is_a_silent_no_op(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert StopSignalService.drive_clear(c.id, t, line=stop_line(t), clear_reason=CLEAR_RECONCILED) is None
        assert not StopSignalState.objects.filter(owner=c).exists()
        assert _events("stop.cleared", owner_id=c.id).count() == 0

    def test_stop_clear_stop_increments_the_episode(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert drive_a_stop(c.id, t) == 1
        assert StopSignalService.drive_clear(c.id, t, line=stop_line(t), clear_reason=CLEAR_BALANCE_RECOVERED) == 1
        assert drive_a_stop(c.id, t) == 2
        seqs = [e.payload["episode_seq"] for e in _events("stop.fired", owner_id=c.id).order_by("created_at")]
        assert seqs == [1, 2]

    def test_families_have_independent_state_and_episodes(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        drive_a_stop(c.id, t)
        # soft_floor (#40) has its own transitions — they must not share
        # state or episode sequence with floor_stop.
        won = StopSignalService.drive_soft_crossed(c.id, t, balance_micros=-1)
        assert won == 1
        states = {r.reason: r.state for r in StopSignalState.objects.filter(owner=c)}
        assert states == {stop_line(t): "stopped", LINE_SOFT_FLOOR: "stopped"}
        assert StopSignalService.drive_soft_cleared(c.id, t, reason=CLEAR_RECONCILED) == 1
        assert StopSignalState.objects.get(owner=c, reason=stop_line(t)).state == "stopped"


@pytest.mark.django_db
class TestSuspensionFold:
    def test_prepaid_winner_suspends_with_the_hard_floors_word(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        drive_a_stop(c.id, t,
                                     balance_micros=-6_000_000)
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == reasons.HARD_FLOOR
        suspended = _events("customer.suspended", "customer_id", c.id)
        assert suspended.count() == 1
        assert suspended.get().payload["balance_micros"] == -6_000_000

    def test_postpaid_enforcing_suspends_with_the_pools_word(self):
        t = _tenant(mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        drive_a_stop(c.id, t)
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == reasons.CUSTOMER_SPEND_POOL

    def test_non_active_owner_gets_the_signal_but_no_status_flip(self):
        # An admin/fraud suspension is never overwritten by the money path —
        # the stop signal still fires (the crossing is real).
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1", status="suspended",
                                    suspension_reason="fraud")
        assert drive_a_stop(c.id, t) == 1
        c.refresh_from_db()
        assert c.suspension_reason == "fraud"
        assert _events("stop.fired", owner_id=c.id).count() == 1
        assert _events("customer.suspended", "customer_id", c.id).count() == 0


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
        drive_a_stop(c.id, t)
        row = StopSignalState.objects.get(owner=c, reason=stop_line(t))
        fired = _events("stop.fired", owner_id=c.id).get()
        assert row.announce_outbox_id == fired.id
        assert fired.payload["re_announcement"] is False

    def test_losing_stop_leaves_the_stamp_alone(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        drive_a_stop(c.id, t)
        stamp = StopSignalState.objects.get(
            owner=c, reason=stop_line(t)).announce_outbox_id
        assert drive_a_stop(c.id, t) is None
        assert StopSignalState.objects.get(
            owner=c, reason=stop_line(t)).announce_outbox_id == stamp

    def test_clear_moves_the_stamp_to_the_cleared_event(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        drive_a_stop(c.id, t)
        fired_id = _events("stop.fired", owner_id=c.id).get().id
        StopSignalService.drive_clear(c.id, t, line=stop_line(t), clear_reason=CLEAR_BALANCE_RECOVERED)
        row = StopSignalState.objects.get(owner=c, reason=stop_line(t))
        cleared = _events("stop.cleared", owner_id=c.id).get()
        assert row.announce_outbox_id == cleared.id
        assert row.announce_outbox_id != fired_id
        assert cleared.payload["re_announcement"] is False

    def test_soft_pair_stamps_its_own_family_row(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        drive_a_stop(c.id, t)
        hard_stamp = StopSignalState.objects.get(
            owner=c, reason=stop_line(t)).announce_outbox_id
        StopSignalService.drive_soft_crossed(c.id, t, balance_micros=-1)
        soft = StopSignalState.objects.get(owner=c, reason=LINE_SOFT_FLOOR)
        crossed = _events("soft_floor.crossed", owner_id=c.id).get()
        assert soft.announce_outbox_id == crossed.id
        assert crossed.payload["re_announcement"] is False
        StopSignalService.drive_soft_cleared(c.id, t, reason=CLEAR_RECONCILED)
        soft.refresh_from_db()
        assert soft.announce_outbox_id == _events(
            "soft_floor.cleared", owner_id=c.id).get().id
        # The hard family's stamp never moved.
        assert StopSignalState.objects.get(
            owner=c, reason=stop_line(t)).announce_outbox_id == hard_stamp


@pytest.mark.django_db
class TestTwoStopLinesAtOnce:
    """Slice 6 §9, Testing Decisions claim 6 (#458): a customer stopped by
    its pool and by its floor at once holds two open episodes, each announced
    once with its own family and id, and the stop lifts only when both
    clear. Through the stop-signal service and the live counter's lifting
    trio; ticket 8 repeats it end to end once the pool blocks prepaid."""

    def setup_method(self):
        cache.clear()

    def _both(self, t, c):
        pool = CustomerSpendPool.objects.create(
            tenant=t, customer=c, cap_micros=1, enforce_mode="blocking")
        floor = StopSignalService.drive_stop(
            c.id, t, line=reasons.HARD_FLOOR,
            control_id=control_id_of(reasons.HARD_FLOOR, c.id, t),
            balance_micros=-1)
        pooled = StopSignalService.drive_stop(
            c.id, t, line=reasons.CUSTOMER_SPEND_POOL,
            control_id=control_id_of(reasons.CUSTOMER_SPEND_POOL, c.id, t))
        return pool, floor, pooled

    def test_each_line_opens_its_own_episode_and_announces_once(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        pool, floor, pooled = self._both(t, c)
        assert (floor, pooled) == (1, 1)  # two sequences, each at its first

        fired = {e.payload["reason_code"]: e.payload
                 for e in _events("stop.fired", owner_id=c.id)}
        assert set(fired) == {reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL}
        assert fired[reasons.HARD_FLOOR]["control_family"] == CONTROL_FAMILY_WALLET_POLICY
        assert fired[reasons.HARD_FLOOR]["control_id"] == str(
            control_id_of(reasons.HARD_FLOOR, c.id, t))
        assert fired[reasons.CUSTOMER_SPEND_POOL]["control_family"] \
            == CONTROL_FAMILY_CUSTOMER_SPEND_POOL
        assert fired[reasons.CUSTOMER_SPEND_POOL]["control_id"] == str(pool.id)
        assert [line for line, _, _ in StopSignalService.open_stop_lines(c.id)] \
            == [reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL]
        # The suspension records the stop that opened it — the first line —
        # and the second line's winning stop suspends nothing twice.
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == reasons.HARD_FLOOR
        assert _events("customer.suspended", "customer_id", c.id).count() == 1

    def test_the_stop_flag_lifts_only_when_both_lines_have_cleared(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        self._both(t, c)
        LiveCounter.ensure_stop_flag(c.id, reasons.HARD_FLOOR)

        # The wallet recovers: the floor's line clears, the pool still holds.
        assert LiveCounter.resume(
            c.id, t, line=reasons.HARD_FLOOR,
            clear_reason=CLEAR_BALANCE_RECOVERED, balance_micros=0) is False
        assert [line for line, _, _ in StopSignalService.open_stop_lines(c.id)] \
            == [reasons.CUSTOMER_SPEND_POOL]
        verdict = LiveCounter.read(c.id, t)
        assert verdict["stop"] is True
        assert verdict["stop_reason"] == reasons.CUSTOMER_SPEND_POOL  # re-pointed
        c.refresh_from_db()
        assert c.status == "suspended"
        cleared = _events("stop.cleared", owner_id=c.id)
        assert cleared.count() == 1
        assert cleared.get().payload["reason_code"] == reasons.HARD_FLOOR

        # The pool clears too: nothing holds the owner, the flag lifts.
        LiveCounter.resume(c.id, t, line=reasons.CUSTOMER_SPEND_POOL,
                           clear_reason=CLEAR_RECONCILED)
        assert StopSignalService.open_stop_lines(c.id) == []
        assert LiveCounter.read(c.id, t)["stop"] is False
        c.refresh_from_db()
        assert c.status == "active"
        assert _events("stop.cleared", owner_id=c.id).count() == 2

    def test_one_row_per_line_at_the_database(self):
        """The key is (owner, control_family, reason), as a constraint."""
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        StopSignalService.drive_stop(
            c.id, t, line=reasons.HARD_FLOOR,
            control_id=control_id_of(reasons.HARD_FLOOR, c.id, t))
        row = StopSignalState.objects.get(owner=c)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                StopSignalState.objects.create(
                    tenant=t, owner=c, control_family=row.control_family,
                    reason=row.reason, state="stopped", episode_seq=9,
                    transitioned_at=timezone.now())
        assert StopSignalState.objects.filter(owner=c).count() == 1

    def test_a_line_that_is_not_a_stop_is_refused_by_the_stop_seams(self):
        t = _tenant()
        c = Customer.objects.create(tenant=t, external_id="c1")
        with pytest.raises(ValueError):
            StopSignalService.drive_stop(c.id, t, line=LINE_SOFT_FLOOR, control_id=None)
        with pytest.raises(ValueError):
            StopSignalService.drive_clear(c.id, t, line=LINE_SOFT_FLOOR,
                                          clear_reason=CLEAR_RECONCILED)

    def test_the_ledger_holds_the_four_families_by_reference(self):
        """`g2-backend-control_family`, paid at the site the registry declares
        (§1): the column's choices are the registry's four identities, and
        the two lines the ledger drives are keyed by two of them."""
        from apps.billing.gating.models import CONTROL_FAMILIES
        from core.vocabulary import CONTROL_FAMILY_VALUES

        assert {identity for identity, _ in CONTROL_FAMILIES} == CONTROL_FAMILY_VALUES
        assert StopSignalState._meta.get_field("control_family").choices == CONTROL_FAMILIES
        assert family_of_line(reasons.HARD_FLOOR) == CONTROL_FAMILY_WALLET_POLICY
        assert family_of_line(reasons.CUSTOMER_SPEND_POOL) == CONTROL_FAMILY_CUSTOMER_SPEND_POOL
        assert family_of_line(LINE_SOFT_FLOOR) == CONTROL_FAMILY_WALLET_POLICY
