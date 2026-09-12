"""Every terminal path releases the prepaid reservation, through the kernel's
terminal-transition listener, and the backstop sweep releases what a failed
listener left behind (#461, slice 6 §5 — ticket 10 of 20).

⚠ NO CASE HERE CALLS THE RELEASE. Each drives a real terminal path — the
tenant's close in its three outcomes, the recording lane's kill, the pool's
kill, the patrol's kill, both windows of the announcing sweeper, the crash
sweeper, and the three cascades onto contained work — and asserts that the reservation the unit's
start took is released afterwards, by the listener (`released_by` says so).
A case that released by hand would prove the release function works and
nothing about whether the close reaches it; the whole claim is the paths.

WHY THIS MODULE IS THE COMPOSITION LAYER'S. The reservation is taken by the
start route and released by a billing listener the kernel calls, and the
paths that end a unit are a route (the close), a route's commit (the
recording lane's kill), two of billing's beats (the patrol; the backstop) and
two of the kernel's (the reapers). A module in any one product could not drive
them all without importing another product's test helpers — the boundary
`apps/billing/gating/tests/test_patrol_pins.py` names — so the release is
proved where the assembled surface is (`docs/conventions/testing.md`).

⚠ THE TICKET SAYS "KILLED (TENANT AND PATROL)", AND THERE IS NO TENANT KILL:
since #408 nothing a tenant declares writes `killed`. The kill a tenant's own
action causes is the recording lane's — the tenant's usage report trips the
ceiling — and that is the case here, driven through `POST /metering/usage`
for real, exactly as #460 read the same words for the listener registry.

⚠ CONTAINED WORK NEVER RESERVES (a whole-work price on contained work is
refused, #415), so the three cascade cases carry two claims: the parent's
reservation is released on the parent's own transition, and the cascade's
own call onto the contained piece reaches the release — proved on a row
PLANTED on the contained piece, a shape no production path writes, because a
case that only watched the parent would leave the cascade seam unproven.
"""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from api.v1.tests._helpers import (
    SOLD_PER_EVENT, THE_AGREED_PRICE, a_tenant_selling_whole_work)
from apps.billing.gating.models import CustomerSpendPool
from apps.billing.gating.tasks import reconcile_live_ledgers
from apps.billing.wallets.models import (
    RELEASED_BY_BACKSTOP_SWEEP, RELEASED_BY_TERMINAL_TRANSITION,
    WalletReservation)
from apps.billing.wallets.reservations import open_reservations_micros
from apps.billing.wallets.tasks import (
    release_reservations_left_open_on_terminal_work)
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, what_it_bills)
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.work import reasons
from apps.platform.work.models import Task
from apps.platform.work.services import (
    STOP_CAUSE_KEY, TaskService, ceiling_control_id)
from apps.platform.work.tasks import close_abandoned_tasks, reap_stale_tasks
from core.vocabulary import (
    OUTCOME_REASON_CUSTOMER_CANCELLED, OUTCOME_REASON_TIMEOUT,
    SPEND_POOL_ENFORCE_MODE_BLOCKING, TASK_OUTCOME_CANCELLED,
    TASK_OUTCOME_DELIVERED, TASK_OUTCOME_FAILED, TASK_STATUS_ACTIVE,
    TASK_STATUS_CANCELLED, TASK_STATUS_COMPLETED, TASK_STATUS_EXPIRED,
    TASK_STATUS_FAILED, TASK_STATUS_KILLED, TRIGGER_SOURCE_STALE_REAPER)

#: A ceiling one usage report trips, so the recording lane's kill and the
#: patrol's sweep each have something to fire on.
A_LOW_CEILING = 1_000
#: Where the outbox doorbell rings; patched so executed on-commit callbacks
#: never reach Celery (the pool module's own arrangement).
DOORBELL = "apps.platform.events.tasks.process_single_event"


class ReleaseTestBase(TestCase):
    """One enforcing tenant that bills on the wallet lane (the reapers reap
    for enforcing tenants only), one customer, and the routes."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.fixture = a_tenant_selling_whole_work(
            enforcement_mode="enforcing", balance_micros=100_000_000)
        self.tenant = self.fixture.tenant
        self.customer = self.fixture.customer
        declares_a_caller_supplied_cost(self.tenant, DECLARED)
        a_rule_that_prices_what_it_measures(self.tenant)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return self.fixture.auth()

    def _started(self, **body):
        response = self.client.post(
            "/api/v1/tasks", data=json.dumps(self.fixture.start_body(**body)),
            content_type="application/json", **self._auth())
        self.assertEqual(response.status_code, 200, response.content)
        return Task.objects.get(id=response.json()["task_id"])

    def _reserved_unit(self, **body):
        unit = self._started(**body)
        self.assertTrue(self._reservation(unit).released_at is None)
        return unit

    def _a_parent_and_its_contained_work(self, **parent_body):
        parent = self._reserved_unit(**parent_body)
        contained = self._started(parent_task_id=str(parent.id))
        self.assertIsNone(contained.agreed_price_micros)
        # THE PLANTED ROW — see the module docstring.
        WalletReservation.objects.create(
            tenant=self.tenant, owner=self.customer, task=contained,
            amount_micros=1)
        return parent, contained

    def _close(self, unit, outcome=TASK_OUTCOME_DELIVERED, **declaration):
        declaration["outcome"] = outcome
        response = self.client.post(
            f"/api/v1/tasks/{unit.id}/close", data=json.dumps(declaration),
            content_type="application/json", **self._auth())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _record(self, *, bills=None, **extra):
        """A usage report through the recording route; the ceiling's and the
        pool's kills are registered on the recording transaction's commit,
        which a `TestCase` never performs, so the callbacks are run here with
        the doorbell silenced."""
        data = {"customer_id": str(self.customer.id),
                "idempotency_key": f"idem-{uuid.uuid4()}",
                "event_type": DECLARED, "provider_cost_micros": 1_000}
        if bills is not None:
            data.update(what_it_bills({"bills": bills}))
        data.update(extra)
        with patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/metering/usage", data=json.dumps(data),
                content_type="application/json", **self._auth())
        self.assertEqual(response.status_code, 200, response.json())
        return response.json()

    @staticmethod
    def _backdate(unit, *, created, last_event=None):
        Task.objects.filter(id=unit.id).update(
            created_at=timezone.now() - created,
            last_event_at=None if last_event is None
            else timezone.now() - last_event)

    def _reservation(self, unit):
        return WalletReservation.objects.get(task_id=unit.id)

    def assert_released_by_the_transition(self, unit, status):
        unit.refresh_from_db()
        self.assertEqual(unit.status, status)
        row = self._reservation(unit)
        self.assertIsNotNone(row.released_at)
        self.assertEqual(row.released_by, RELEASED_BY_TERMINAL_TRANSITION)

    def assert_nothing_is_reserved(self):
        self.assertEqual(open_reservations_micros(self.customer.id), 0)


class TheTenantsCloseReleasesTest(ReleaseTestBase):
    """One case per declarable outcome — the three states a close enters."""

    def test_a_declared_delivery(self):
        unit = self._reserved_unit()
        self.assertTrue(self._close(unit)["charge_created"])
        self.assert_released_by_the_transition(unit, TASK_STATUS_COMPLETED)
        self.assert_nothing_is_reserved()

    def test_a_declared_failure(self):
        unit = self._reserved_unit()
        self._close(unit, TASK_OUTCOME_FAILED,
                    outcome_reason=OUTCOME_REASON_TIMEOUT)
        self.assert_released_by_the_transition(unit, TASK_STATUS_FAILED)
        self.assert_nothing_is_reserved()

    def test_a_declared_cancellation(self):
        unit = self._reserved_unit()
        self._close(unit, TASK_OUTCOME_CANCELLED,
                    outcome_reason=OUTCOME_REASON_CUSTOMER_CANCELLED)
        self.assert_released_by_the_transition(unit, TASK_STATUS_CANCELLED)
        self.assert_nothing_is_reserved()

    def test_a_repeated_close_releases_nothing_twice(self):
        unit = self._reserved_unit()
        self._close(unit)
        first = self._reservation(unit).released_at
        self._close(unit)
        self.assertEqual(self._reservation(unit).released_at, first)


class UbbsOwnStopsReleaseTest(ReleaseTestBase):
    """The three kills and the three expiries, each through the lane that
    applies it."""

    def test_the_recording_lanes_kill(self):
        unit = self._reserved_unit(task_cogs_ceiling_micros=A_LOW_CEILING)
        ack = self._record(task_id=str(unit.id), provider_cost_micros=5_000_000)
        self.assertTrue(ack["stop"])
        self.assert_released_by_the_transition(unit, TASK_STATUS_KILLED)
        self.assert_nothing_is_reserved()

    def test_the_pools_kill(self):
        # The third caller of the kernel's kill seam: a blocking pool crossed
        # by one usage report, whose winning transition kills the customer's
        # active work on commit (`CustomerSpendPoolService.stop_active_work`)
        # — the lane #460 held by the structural pin alone.
        unit = self._reserved_unit()
        CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer, cap_micros=5_000_000,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        # The crossing report sits under no unit: a metered posting under
        # work sold at one agreed price bills nothing (#418), so it could not
        # move the pool. The pool's kill reaches every active unit of the
        # customer, the reserved one included.
        ack = self._record(bills=5_000_000)
        self.assertTrue(ack["stop"])
        self.assertEqual(ack["stop_reason"], reasons.CUSTOMER_SPEND_POOL)
        self.assert_released_by_the_transition(unit, TASK_STATUS_KILLED)
        self.assert_nothing_is_reserved()

    def test_the_patrols_kill(self):
        # A unit sitting at its ceiling that no usage report stopped — the
        # crashed-kill corner the hourly patrol sweeps.
        unit = self._reserved_unit(task_cogs_ceiling_micros=A_LOW_CEILING)
        Task.objects.filter(id=unit.id).update(
            total_provider_cost_micros=A_LOW_CEILING)
        reconcile_live_ledgers()
        self.assert_released_by_the_transition(unit, TASK_STATUS_KILLED)
        self.assert_nothing_is_reserved()

    def test_an_expiry_on_the_silence_window(self):
        unit = self._reserved_unit()
        self._backdate(unit, created=timedelta(hours=2),
                       last_event=timedelta(hours=1))
        self.assertEqual(reap_stale_tasks(), 1)
        self.assert_released_by_the_transition(unit, TASK_STATUS_EXPIRED)
        self.assert_nothing_is_reserved()

    def test_an_expiry_on_the_absolute_deadline(self):
        unit = self._reserved_unit()
        self._backdate(unit, created=timedelta(hours=7),
                       last_event=timedelta(minutes=1))
        self.assertEqual(reap_stale_tasks(), 1)
        self.assert_released_by_the_transition(unit, TASK_STATUS_EXPIRED)
        self.assert_nothing_is_reserved()

    def test_the_crash_sweepers_unannounced_expiry(self):
        # The one terminal path the ticket's list does not name: a unit that
        # never reported, expired unannounced. A reservation it left would be
        # exactly the row the backstop exists for; the listener hears it.
        unit = self._reserved_unit()
        self._backdate(unit, created=timedelta(hours=2))
        self.assertEqual(close_abandoned_tasks(), 1)
        self.assert_released_by_the_transition(unit, TASK_STATUS_EXPIRED)
        self.assert_nothing_is_reserved()


class AParentsEndReleasesTheContainedWorksTooTest(ReleaseTestBase):
    """The three cascades: the parent's own reservation on the parent's
    transition, and the planted row on the contained piece through the
    cascade's own call."""

    def test_a_close_withdraws_the_contained_work(self):
        parent, contained = self._a_parent_and_its_contained_work()
        self._close(parent)
        self.assert_released_by_the_transition(parent, TASK_STATUS_COMPLETED)
        self.assert_released_by_the_transition(contained, TASK_STATUS_CANCELLED)
        self.assert_nothing_is_reserved()

    def test_a_kill_reaches_down(self):
        parent, contained = self._a_parent_and_its_contained_work(
            task_cogs_ceiling_micros=A_LOW_CEILING)
        self._record(task_id=str(parent.id), provider_cost_micros=5_000_000)
        self.assert_released_by_the_transition(parent, TASK_STATUS_KILLED)
        self.assert_released_by_the_transition(contained, TASK_STATUS_KILLED)
        contained.refresh_from_db()
        self.assertEqual(contained.metadata[STOP_CAUSE_KEY], reasons.PARENT_KILLED)
        self.assert_nothing_is_reserved()

    def test_an_expiry_reaches_down(self):
        parent, contained = self._a_parent_and_its_contained_work()
        self.assertTrue(TaskService.expire_and_announce(
            parent.id, reasons.SILENCE_WINDOW,
            tenant_id=self.tenant.id, customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_STALE_REAPER,
            control_id=ceiling_control_id(parent)))
        self.assert_released_by_the_transition(parent, TASK_STATUS_EXPIRED)
        self.assert_released_by_the_transition(contained, TASK_STATUS_EXPIRED)
        self.assert_nothing_is_reserved()


class TheBackstopSweepTest(ReleaseTestBase):
    """A sweep over terminal work holding an open reservation — the trivial
    backstop #139 named: a beat, idempotent, releasing and logging."""

    LOGGER = "ubb.billing"

    def _a_terminal_unit_still_holding_a_reservation(self):
        # An event-priced unit reserved nothing, so the listener released
        # nothing when it closed; the row planted on it afterwards is exactly
        # the shape a failed listener leaves — open, on terminal work.
        unit = self._started(task_type=SOLD_PER_EVENT)
        self._close(unit)
        return WalletReservation.objects.create(
            tenant=self.tenant, owner=self.customer, task=unit,
            amount_micros=THE_AGREED_PRICE)

    def test_the_sweep_releases_what_was_left_open_and_says_so(self):
        row = self._a_terminal_unit_still_holding_a_reservation()
        self.assertEqual(open_reservations_micros(self.customer.id),
                         THE_AGREED_PRICE)

        with self.assertLogs(self.LOGGER, level="WARNING") as logged:
            self.assertEqual(release_reservations_left_open_on_terminal_work(), 1)

        row.refresh_from_db()
        self.assertIsNotNone(row.released_at)
        self.assertEqual(row.released_by, RELEASED_BY_BACKSTOP_SWEEP)
        self.assert_nothing_is_reserved()
        self.assertEqual(len(logged.output), 1)
        self.assertIn("wallet.reservation_released_by_backstop", logged.output[0])

    def test_a_second_run_releases_nothing(self):
        row = self._a_terminal_unit_still_holding_a_reservation()
        self.assertEqual(release_reservations_left_open_on_terminal_work(), 1)
        first = WalletReservation.objects.get(id=row.id).released_at

        self.assertEqual(release_reservations_left_open_on_terminal_work(), 0)

        self.assertEqual(WalletReservation.objects.get(id=row.id).released_at,
                         first)

    def test_the_sweep_leaves_running_work_alone(self):
        unit = self._reserved_unit()
        self.assertEqual(release_reservations_left_open_on_terminal_work(), 0)
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_ACTIVE)
        self.assertIsNone(self._reservation(unit).released_at)

    def test_a_listener_that_failed_is_repaired_by_the_sweep(self):
        """END TO END: the listener's failure vetoes nothing (the close
        stands, the charge is created, the registry logs it), the row is
        left open, and the next sweep releases it."""
        unit = self._reserved_unit()
        with patch("apps.billing.wallets.reservations._release",
                   side_effect=RuntimeError("a product's bug")):
            with self.assertLogs("apps.platform.work.hooks", level="ERROR"):
                self.assertTrue(self._close(unit)["charge_created"])
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_COMPLETED)
        self.assertIsNone(self._reservation(unit).released_at)

        self.assertEqual(release_reservations_left_open_on_terminal_work(), 1)

        row = self._reservation(unit)
        self.assertIsNotNone(row.released_at)
        self.assertEqual(row.released_by, RELEASED_BY_BACKSTOP_SWEEP)

    def test_the_sweep_is_a_scheduled_beat(self):
        # `apps/platform/tests/test_beat_schedule.py` proves every entry
        # resolves; this pins that the backstop HAS an entry.
        scheduled = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
        self.assertIn(release_reservations_left_open_on_terminal_work.name,
                      scheduled)
