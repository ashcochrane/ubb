"""A pooled seat's own Pool stop reaches its recording acknowledgements
(#609; the precedence rule was CONFIRMED by the owner and consultant on
2026-10-08).

A customer Pool has two levels (#459). The billing owner's is counted live,
by the recording's debit. A pooled seat's own is counted on the drawdown and
driven on the SEAT: its ledger line, its suspension, its flag. Until #609 an
acknowledgement read the billing owner's stops alone, so a seat stopped at
its own level was told nothing. Now every acknowledgement (fresh and
replayed, single route and batch item) and its `stop_context` read every
customer-wide stop that applies to the recording's customer, and the
acknowledgement names ONE of them by scope precedence:

    business stop + seat stop -> the business-level stop
    business stop only        -> the business-level stop
    seat stop only            -> the seat-level stop
    neither                   -> no Pool stop

The business stop is the broader constraint: it would block the event
whatever the seat's own state. It is acknowledgement precedence ONLY. The
seat's own ledger row, suspension and flag are left as they stand, and
`stop_context` itemises every standing line, the business's first.

Two Pool stops carry the same three acknowledgement fields, so precedence
is visible on the wire where the business's stop is its wallet floor; the
Pool-and-Pool case pins what the wire can show (the stop, and both lines
itemised).

Every case runs on both recording routes: the shape is a mixin, bound twice
by naming the route. The replay is pinned as it stands before #569: it reads
the stops standing NOW. #569's snapshot will freeze what the original
acknowledgement named, and inverts the one pin here that says otherwise.
"""
import json
import uuid
from unittest import mock

from apps.billing.gating.models import CustomerSpendPool, StopSignalState
from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.gating.tests.test_a_blocking_pool_stops_prepaid_work_as_it_stops_postpaid import (
    DOORBELL, PoolTestBase)
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.tests._helpers import what_it_bills
from apps.platform.event_types.tests._helpers import DECLARED
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons
from apps.platform.work.models import Task
from core.vocabulary import (SPEND_POOL_ENFORCE_MODE_BLOCKING,
                             TASK_STATUS_KILLED)

SINGLE = "single"
BATCH = "batch"

#: The seat level's line: the tenant default, which reaches every seat and
#: never a business, so each seat has a Pool of its own at this figure.
SEAT_LINE = 3_000_000
#: The business level's line, above the seat's, so one report tips the seat
#: level (on the drawdown) before the business level (on the live debit).
BUSINESS_LINE = 5_000_000


class ThePooledSeatsStopsOnItsAcknowledgements:
    """The shared shape. Each route below runs every case; the class that
    binds it says which route it is about by naming it."""

    ROUTE = None

    def setUp(self):
        super().setUp()
        self.biz = self._customer("biz", wallet=self.WALLET,
                                  account_type="business",
                                  billing_topology="pooled")
        self.seat1 = self._customer("s1", account_type="seat", parent=self.biz)
        self.seat2 = self._customer("s2", account_type="seat", parent=self.biz)

    # -- the levels ---------------------------------------------------------

    def _seat_level(self):
        return CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=None, cap_micros=SEAT_LINE,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)

    def _business_level(self):
        return self._pool(self.biz, BUSINESS_LINE)

    # -- one recording, through this class's route --------------------------

    def _ack(self, customer, *, key=None, bills=1_000_000, task_id=None):
        """One usage report for `customer` under `key` (a new one by default),
        through this class's route: the acknowledgement as a caller reads it.
        The kills a stop registers run on commit, as `_record` runs them."""
        item = {"customer_id": str(customer.id),
                "idempotency_key": key or f"idem-{uuid.uuid4()}",
                "event_type": DECLARED, "provider_cost_micros": 1_000,
                "task_id": task_id, **what_it_bills({"bills": bills})}
        path, body = (("/api/v1/metering/usage", item) if self.ROUTE == SINGLE
                      else ("/api/v1/metering/usage/batch", {"events": [item]}))
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            response = self.http.post(path, data=json.dumps(body),
                                      **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        if self.ROUTE == SINGLE:
            return response.json()
        [result] = response.json()["results"]
        self.assertTrue(result["accepted"], result)
        return result

    def _fresh_and_replayed(self, customer):
        """A new report's acknowledgement, then the same key sent again."""
        key = f"idem-{uuid.uuid4()}"
        fresh = self._ack(customer, key=key)
        replayed = self._ack(customer, key=key)
        self.assertEqual(replayed["event_id"], fresh["event_id"])
        return fresh, replayed

    def _stop_the_seat_at_its_own_level(self, seat):
        """The seat level is counted on the drawdown, so the report that
        reaches it is acknowledged un-stopped (correctly: nothing has
        detected it yet) and the drain drives the seat's own line. Returns
        that report's key."""
        key = f"idem-{uuid.uuid4()}"
        tipping = self._ack(seat, key=key, bills=SEAT_LINE)
        self.assertFalse(tipping["stop"])
        self._drain()
        seat.refresh_from_db()
        self.assertEqual(seat.status, "suspended")
        self.assertEqual(seat.suspension_reason, reasons.CUSTOMER_SPEND_POOL)
        return key

    # -- what an acknowledgement says ---------------------------------------

    def _assert_stopped(self, ack, word):
        self.assertTrue(ack["stop"], ack)
        self.assertEqual(ack["stop_reason"], word)
        self.assertEqual(ack["stop_scope"], "customer")

    def _assert_not_stopped(self, ack):
        self.assertFalse(ack["stop"], ack)
        self.assertIsNone(ack["stop_reason"])
        self.assertIsNone(ack["stop_scope"])
        self.assertIsNone(ack["stop_context"])

    def _line(self, owner, word):
        """The standing ledger line of `owner` (a business or a seat) on
        `word`, as `stop_context` itemises it."""
        row = StopSignalState.objects.get(owner=owner, reason=word,
                                          state="stopped")
        return {"limit": word, "stop_scope": "customer",
                "tripped_at": row.transitioned_at.isoformat(),
                "episode_seq": row.episode_seq}

    def _customer_lines(self, ack):
        return [{key: entry[key] for key in
                 ("limit", "stop_scope", "tripped_at", "episode_seq")}
                for entry in ack["stop_context"] or []
                if entry["stop_scope"] == "customer"]

    # -- the four cases -----------------------------------------------------

    def test_business_and_seat_stops_name_the_business_stop_and_itemise_both(self):
        """Case 1, Pool and Pool. Both lines are the Pool's, so the scalar
        fields read alike at either level; `stop_context` carries both lines,
        the business's first, and the seat's line is late."""
        self._seat_level()
        self._business_level()
        self._stop_the_seat_at_its_own_level(self.seat1)
        tipping = self._ack(self.seat1, bills=2_000_000)   # the business's line
        self._assert_stopped(tipping, reasons.CUSTOMER_SPEND_POOL)

        for ack in self._fresh_and_replayed(self.seat1):
            self._assert_stopped(ack, reasons.CUSTOMER_SPEND_POOL)
            self.assertEqual(self._customer_lines(ack), [
                self._line(self.biz, reasons.CUSTOMER_SPEND_POOL),
                self._line(self.seat1, reasons.CUSTOMER_SPEND_POOL)])
            self.assertTrue(all(entry["arrived_after"]
                                for entry in ack["stop_context"]))

    def test_the_business_floor_is_named_over_the_seats_own_pool_stop(self):
        """Case 1, where the wire can tell the two apart: the business's
        stop is its wallet floor, the seat's is its own Pool. The
        acknowledgement names the business's."""
        Wallet.objects.filter(customer=self.biz).update(balance_micros=4_000_000)
        self._seat_level()
        self._stop_the_seat_at_its_own_level(self.seat1)
        tipping = self._ack(self.seat1, bills=2_000_000)   # the wallet goes below
        self._assert_stopped(tipping, reasons.HARD_FLOOR)

        for ack in self._fresh_and_replayed(self.seat1):
            self._assert_stopped(ack, reasons.HARD_FLOOR)
            self.assertEqual(self._customer_lines(ack), [
                self._line(self.biz, reasons.HARD_FLOOR),
                self._line(self.seat1, reasons.CUSTOMER_SPEND_POOL)])

    def test_the_business_stop_alone_is_named(self):
        """Case 2: the business is past its Pool and no seat has a level of
        its own."""
        self._business_level()
        tipping = self._ack(self.seat1, bills=BUSINESS_LINE)
        self._assert_stopped(tipping, reasons.CUSTOMER_SPEND_POOL)

        for seat in (self.seat1, self.seat2):
            for ack in self._fresh_and_replayed(seat):
                self._assert_stopped(ack, reasons.CUSTOMER_SPEND_POOL)
                self.assertEqual(self._customer_lines(ack), [
                    self._line(self.biz, reasons.CUSTOMER_SPEND_POOL)])
        self.assertFalse(StopSignalState.objects.filter(
            owner__in=[self.seat1, self.seat2]).exists())

    def test_the_seats_own_stop_alone_is_named_and_stops_no_sibling(self):
        """Case 3: the seat is past its own Pool and the business is past
        nothing. Every later acknowledgement for the seat says so; its
        sibling, whose own Pool stands at nothing, is not stopped by it."""
        self._seat_level()
        self._stop_the_seat_at_its_own_level(self.seat1)

        for ack in self._fresh_and_replayed(self.seat1):
            self._assert_stopped(ack, reasons.CUSTOMER_SPEND_POOL)
            self.assertEqual(self._customer_lines(ack), [
                self._line(self.seat1, reasons.CUSTOMER_SPEND_POOL)])
            self.assertTrue(ack["stop_context"][0]["arrived_after"])
        for ack in self._fresh_and_replayed(self.seat2):
            self._assert_not_stopped(ack)
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, "active")

    def test_neither_stop_names_no_stop(self):
        """Case 4: both levels declared, neither reached."""
        self._seat_level()
        self._business_level()

        for seat in (self.seat1, self.seat2):
            for ack in self._fresh_and_replayed(seat):
                self._assert_not_stopped(ack)

    def test_a_customer_that_is_its_own_billing_owner_is_unchanged(self):
        """The two levels coincide for a customer that is its own billing
        owner: one line, one flag, read once and itemised once."""
        self._pool(self.customer, BUSINESS_LINE)
        tipping = self._ack(self.customer, bills=BUSINESS_LINE)
        self._assert_stopped(tipping, reasons.CUSTOMER_SPEND_POOL)

        for ack in self._fresh_and_replayed(self.customer):
            self._assert_stopped(ack, reasons.CUSTOMER_SPEND_POOL)
            self.assertEqual(self._customer_lines(ack), [
                self._line(self.customer, reasons.CUSTOMER_SPEND_POOL)])

    # -- what precedence does not do ----------------------------------------

    def test_precedence_leaves_the_seats_own_stop_as_it_stands(self):
        """Acknowledgement precedence only: naming the business's stop moves
        nothing the seat's own level holds — its ledger line, its suspension
        and its flag are exactly as they were before the business stopped."""
        self._seat_level()
        self._business_level()
        self._stop_the_seat_at_its_own_level(self.seat1)
        before = StopSignalState.objects.filter(owner=self.seat1).values(
            "reason", "state", "episode_seq", "transitioned_at", "control_id",
            "announce_outbox_id")
        before = list(before)

        self._assert_stopped(self._ack(self.seat1, bills=2_000_000),
                             reasons.CUSTOMER_SPEND_POOL)
        self._ack(self.seat1)

        self.assertEqual(list(StopSignalState.objects.filter(owner=self.seat1).values(
            "reason", "state", "episode_seq", "transitioned_at", "control_id",
            "announce_outbox_id")), before)
        self.seat1.refresh_from_db()
        self.assertEqual(self.seat1.status, "suspended")
        self.assertEqual(self.seat1.suspension_reason, reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(LiveCounter.read(self.seat1.id, self.tenant)["stop_reason"],
                         reasons.CUSTOMER_SPEND_POOL)

    def test_a_unit_verdict_still_takes_the_scalar_slot_first(self):
        """The seat's own stop killed its work; a late report on that work
        is `task_not_active` in the scalar slot, and the seat's line is still
        itemised beside it."""
        self._seat_level()
        unit = self._unit(self.seat1)
        tipping = self._ack(self.seat1, bills=SEAT_LINE, task_id=unit)
        self.assertFalse(tipping["stop"])
        self._drain()
        self.assertEqual(Task.objects.get(id=unit).status, TASK_STATUS_KILLED)

        late = self._ack(self.seat1, task_id=unit)

        self.assertTrue(late["stop"])
        self.assertEqual(late["stop_reason"], reasons.TASK_NOT_ACTIVE)
        self.assertEqual(late["stop_scope"], "task")
        self.assertEqual(self._customer_lines(late), [
            self._line(self.seat1, reasons.CUSTOMER_SPEND_POOL)])

    # -- the seat's stop clears ---------------------------------------------

    def test_once_the_seats_stop_clears_its_acknowledgements_say_not_stopped(self):
        from apps.billing.gating.tasks import reconcile_customer_spend_pool_counters
        self._seat_level()
        self._stop_the_seat_at_its_own_level(self.seat1)
        stopped_key = f"idem-{uuid.uuid4()}"
        self._assert_stopped(self._ack(self.seat1, key=stopped_key),
                             reasons.CUSTOMER_SPEND_POOL)

        # The tenant raises the seat level; the seat-level beat lifts the line.
        CustomerSpendPool.objects.filter(tenant=self.tenant).update(
            cap_micros=100_000_000)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            reconcile_customer_spend_pool_counters()
        self.seat1.refresh_from_db()
        self.assertEqual(self.seat1.status, "active")

        for ack in self._fresh_and_replayed(self.seat1):
            self._assert_not_stopped(ack)
        # Before #569 a replay reads the stops standing now.
        self.assertFalse(self._ack(self.seat1, key=stopped_key)["stop"])

    # -- the replay, as it stands before #569 -------------------------------

    def test_before_569_a_replay_reads_the_seats_stop_standing_now(self):
        """The report that reached the seat's level was acknowledged
        un-stopped; replayed after the drawdown drove the seat's line, it
        carries the seat's stop, because a replay reads the stops standing
        now. #569's snapshot answers the original instead, and inverts this
        pin."""
        self._seat_level()
        tipping_key = self._stop_the_seat_at_its_own_level(self.seat1)

        replayed = self._ack(self.seat1, key=tipping_key)

        self._assert_stopped(replayed, reasons.CUSTOMER_SPEND_POOL)

    # -- fail-open, and a tenant that does not enforce ----------------------

    def test_a_blind_read_is_not_stopped(self):
        """Redis cannot answer: the acknowledgement fails open, fresh and
        replayed, and the report is still recorded."""
        self._seat_level()
        self._stop_the_seat_at_its_own_level(self.seat1)
        key = f"idem-{uuid.uuid4()}"
        blind = mock.patch(
            "apps.billing.gating.services.live_counter._client",
            side_effect=ConnectionError("redis is down"))

        with blind:
            fresh = self._ack(self.seat1, key=key)
            replayed = self._ack(self.seat1, key=key)

        for ack in (fresh, replayed):
            self.assertFalse(ack["stop"], ack)
        self.assertEqual(replayed["event_id"], fresh["event_id"])

    def test_a_tenant_that_does_not_enforce_reads_no_customer_wide_stop(self):
        self._seat_level()
        self._stop_the_seat_at_its_own_level(self.seat1)
        Tenant.objects.filter(id=self.tenant.id).update(enforcement_mode="off")

        for ack in self._fresh_and_replayed(self.seat1):
            self._assert_not_stopped(ack)


class ThePooledSeatsStopsOnTheSingleRouteTest(
        ThePooledSeatsStopsOnItsAcknowledgements, PoolTestBase):
    ROUTE = SINGLE


class ThePooledSeatsStopsOnABatchItemTest(
        ThePooledSeatsStopsOnItsAcknowledgements, PoolTestBase):
    """The other route, owed by name: one batch item is one single report."""
    ROUTE = BATCH
