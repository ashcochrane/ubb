"""Every terminal path tells the listeners, exactly once, and none of them
can veto it (#460, slice 6 §5 — the platform-hooks channel of ADR-001 rule
3, the fourth in `CLAUDE.md`'s list).

The registry in `work/hooks.py` is a prefactor: nothing registers on it yet.
What this module proves is the surface the reservation's release will stand
on — that a listener hears EVERY way a unit of work reaches a terminal state,
hears each exactly once, hears nothing for a transition that is not terminal,
and cannot take the transition down by raising.

⚠ EVERY CASE DRIVES A REAL ENTRY POINT AND NONE DRIVES THE NOTIFY FUNCTION.
The claim is about the paths, not the registry: a case that called
`notify_terminal_transition` by hand would prove the registry works and
nothing about whether `close_task` reaches it. The paths here are the
tenant's close in each of its three outcomes, the recording lane's kill, both
windows of the announcing sweeper, the crash sweeper, and the three cascades.
The patrol's kill — the other lane the ticket names — is billing's sweep and
is proved where billing's other patrol pins are
(`apps.billing.gating.tests.test_patrol_pins.TestPin6TaskSweep`), because a
kernel test importing a product is the boundary ADR-001 draws, read in the
other direction.

⚠ THE TICKET SAYS "KILLED (TENANT-INITIATED AND BY THE PATROL)", AND THERE
IS NO TENANT-INITIATED KILL: since #408 nothing a tenant declares writes
`killed` (I2). The kill a tenant's own action causes is the recording
lane's — the tenant's usage report trips the ceiling, and the ingest lane
calls `kill_and_announce` under `TRIGGER_SOURCE_USAGE_INGEST` — so that is
the case here, driven through the kernel's kill entry point exactly as the
ingest lane drives it. The third caller of that entry point, the pool's
stop of a customer's active work, has no case of its own in this module
or billing's: it reaches the listeners through the same seam, and the
structural pin at the bottom is what holds that.

⚠ THE CRASH SWEEPER IS HERE THOUGH THE TICKET'S LIST DID NOT NAME IT. It is
a terminal path — the unannounced expiry of work that never reported — and
a listener that missed it would leave exactly the row the reservation's
backstop sweep exists to find. Its transition carries no stop cause, which
is the honest record of a sweep that names no window.

The recorder keeps what each listener call received — the row's id, the
row's status AS THE LISTENER SAW IT, and the `TerminalTransition` — so
"exactly once" is a count of one under the unit, and the row being written
before the listener is called is asserted beside the transition's fields.
"""
import ast
import inspect
from datetime import timedelta

from django.db import connection

from apps.platform.events.schemas import TaskKilled
from apps.platform.tenants.models import Tenant
from apps.platform.work import hooks, reasons, services
from apps.platform.work.hooks import TerminalTransition
from apps.platform.work.models import Task
from apps.platform.work.services import (
    CloseDeclaration, TaskService, ceiling_control_id)
from apps.platform.work.tasks import close_abandoned_tasks, reap_stale_tasks
from apps.platform.work.tests._helpers import WorkTestBase, backdate
from core.vocabulary import (
    OUTCOME_REASON_CUSTOMER_CANCELLED, OUTCOME_REASON_PARENT_CLOSED,
    OUTCOME_REASON_TIMEOUT, TASK_OUTCOME_CANCELLED, TASK_OUTCOME_DELIVERED,
    TASK_OUTCOME_FAILED, TASK_STATUS_ACTIVE, TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED, TASK_STATUS_EXPIRED, TASK_STATUS_FAILED,
    TASK_STATUS_KILLED, TRIGGER_SOURCE_STALE_REAPER,
    TRIGGER_SOURCE_USAGE_INGEST)


class TerminalListenersTestBase(WorkTestBase):
    def setUp(self):
        super().setUp()
        # The announcing sweeper reaps for enforcing tenants only; the crash
        # sweeper visits every tenant. One posture serves every case here.
        Tenant.objects.filter(id=self.tenant.id).update(
            enforcement_mode="enforcing")
        self.tenant.refresh_from_db()
        # Isolate the registry exactly as the roster registry's test does:
        # whatever app loading registered is set aside and restored.
        self._saved = list(hooks._listeners)
        hooks._listeners[:] = []
        self.heard = []
        hooks.register_terminal_transition_listener(self._record)

    def tearDown(self):
        hooks._listeners[:] = self._saved
        super().tearDown()

    def _record(self, task, transition):
        self.heard.append((task.id, task.status, transition))

    def _heard_for(self, task):
        return [(status, transition) for task_id, status, transition
                in self.heard if task_id == task.id]

    def assert_heard_once(self, task, **transition):
        """`task` reached the listener exactly once, already in the state the
        transition names, with exactly this `TerminalTransition`."""
        expected = TerminalTransition(**transition)
        heard = self._heard_for(task)
        self.assertEqual(
            len(heard), 1,
            f"heard {len(heard)} times, expected once: {heard}")
        status_as_seen, received = heard[0]
        self.assertEqual(received, expected)
        self.assertEqual(status_as_seen, expected.status,
                         "the row must already be written when the "
                         "listener is called")
        task.refresh_from_db()
        self.assertEqual(task.status, expected.status)

    def _kill(self, task, **kwargs):
        return TaskService.kill_and_announce(
            task.id, reasons.TASK_COGS_CEILING,
            tenant_id=self.tenant.id, customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_USAGE_INGEST,
            control_id=ceiling_control_id(task), **kwargs)


class TheTenantsCloseReachesTheListenersTest(TerminalListenersTestBase):
    """One case per declarable outcome — the three states a close enters."""

    def test_a_declared_delivery(self):
        task = self._task()
        TaskService.close_task(
            task.id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        self.assert_heard_once(task, status=TASK_STATUS_COMPLETED)

    def test_a_declared_failure_carries_its_reason(self):
        task = self._task()
        TaskService.close_task(task.id, CloseDeclaration.declared(
            TASK_OUTCOME_FAILED, OUTCOME_REASON_TIMEOUT))
        self.assert_heard_once(task, status=TASK_STATUS_FAILED,
                               outcome_reason=OUTCOME_REASON_TIMEOUT)

    def test_a_declared_cancellation(self):
        task = self._task()
        TaskService.close_task(task.id, CloseDeclaration.declared(
            TASK_OUTCOME_CANCELLED, OUTCOME_REASON_CUSTOMER_CANCELLED))
        self.assert_heard_once(
            task, status=TASK_STATUS_CANCELLED,
            outcome_reason=OUTCOME_REASON_CUSTOMER_CANCELLED)


class UbbsOwnStopsReachTheListenersTest(TerminalListenersTestBase):
    """The kill and both expiries, each through the lane that applies it."""

    def test_the_recording_lanes_kill(self):
        task = self._task(limit=1_000)
        self.assertTrue(self._kill(task))
        self.assert_heard_once(task, status=TASK_STATUS_KILLED,
                               stop_reason=reasons.TASK_COGS_CEILING)

    def test_an_expiry_on_the_silence_window(self):
        task = backdate(self._task(), created=timedelta(hours=2),
                        last_event=timedelta(hours=1))
        self.assertEqual(reap_stale_tasks(), 1)
        self.assert_heard_once(task, status=TASK_STATUS_EXPIRED,
                               stop_reason=reasons.SILENCE_WINDOW)

    def test_an_expiry_on_the_absolute_deadline(self):
        # Past UBB's six-hour backstop deadline while still reporting: the
        # deadline is the window that ran out, and the reaper says so.
        task = backdate(self._task(), created=timedelta(hours=7),
                        last_event=timedelta(minutes=1))
        self.assertEqual(reap_stale_tasks(), 1)
        self.assert_heard_once(task, status=TASK_STATUS_EXPIRED,
                               stop_reason=reasons.ABSOLUTE_DEADLINE)

    def test_the_crash_sweepers_unannounced_expiry(self):
        task = backdate(self._task(), created=timedelta(hours=2))
        self.assertEqual(close_abandoned_tasks(), 1)
        self.assert_heard_once(task, status=TASK_STATUS_EXPIRED)


class AParentsEndReachesTheListenersForItsContainedWorkTest(
        TerminalListenersTestBase):
    """The three cascades, each marked as one and each recording what its
    `CascadeRecord` says — and the parent's own transition beside it, so a
    parent's end is heard once for the parent and once per piece inside it,
    parent first."""

    def test_a_close_withdraws_the_contained_work(self):
        parent, child = self._a_parent_and_its_contained_work()
        TaskService.close_task(
            parent.id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        self.assert_heard_once(parent, status=TASK_STATUS_COMPLETED)
        self.assert_heard_once(
            child, status=TASK_STATUS_CANCELLED,
            outcome_reason=OUTCOME_REASON_PARENT_CLOSED, cascaded=True)
        self.assertEqual([task_id for task_id, _, _ in self.heard],
                         [parent.id, child.id])

    def test_a_kill_reaches_down(self):
        parent, child = self._a_parent_and_its_contained_work(limit=1_000)
        self.assertTrue(self._kill(parent))
        self.assert_heard_once(parent, status=TASK_STATUS_KILLED,
                               stop_reason=reasons.TASK_COGS_CEILING)
        self.assert_heard_once(child, status=TASK_STATUS_KILLED,
                               stop_reason=reasons.PARENT_KILLED,
                               cascaded=True)

    def test_an_expiry_reaches_down(self):
        parent, child = self._a_parent_and_its_contained_work()
        self.assertTrue(TaskService.expire_and_announce(
            parent.id, reasons.SILENCE_WINDOW,
            tenant_id=self.tenant.id, customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_STALE_REAPER,
            control_id=ceiling_control_id(parent)))
        self.assert_heard_once(parent, status=TASK_STATUS_EXPIRED,
                               stop_reason=reasons.SILENCE_WINDOW)
        self.assert_heard_once(child, status=TASK_STATUS_EXPIRED,
                               stop_reason=reasons.PARENT_EXPIRED,
                               cascaded=True)

    def test_contained_work_already_terminal_is_not_heard_again(self):
        # The cascade only ever touches work still running, and the
        # listeners hear exactly what the cascade wrote — nothing for a
        # piece that had closed on its own before the parent ended.
        parent, child = self._a_parent_and_its_contained_work()
        TaskService.close_task(
            child.id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        TaskService.close_task(
            parent.id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        self.assert_heard_once(child, status=TASK_STATUS_COMPLETED)
        self.assert_heard_once(parent, status=TASK_STATUS_COMPLETED)


class ANonTerminalTransitionReachesNobodyTest(TerminalListenersTestBase):
    """Only a transition OUT OF `active` is announced: not a report, not a
    start, not a replay of either, and not a second arrival at a terminal
    state a unit is already in."""

    def test_a_usage_report_on_active_work(self):
        task = self._task(limit=1_000_000)
        TaskService.accumulate_cost(
            task.id, billed_cost_micros=5, provider_cost_micros=5)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)
        self.assertEqual(self.heard, [])

    def test_a_start_and_its_replay(self):
        started = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=1,
            billing_owner_id=self.customer.id, idempotency_key="attempt-1")
        replayed = TaskService.claimed_by(
            self.tenant, self.customer, "attempt-1")
        self.assertEqual(replayed.id, started.id)
        self.assertEqual(self.heard, [])

    def test_a_repeated_close_is_heard_once(self):
        task = self._task()
        delivered = CloseDeclaration.declared(TASK_OUTCOME_DELIVERED)
        TaskService.close_task(task.id, delivered)
        _, transitioned = TaskService.close_task(task.id, delivered)
        self.assertFalse(transitioned)
        self.assert_heard_once(task, status=TASK_STATUS_COMPLETED)

    def test_a_repeated_kill_is_heard_once(self):
        task = self._task(limit=1_000)
        self.assertTrue(self._kill(task))
        self.assertFalse(self._kill(task))
        self.assert_heard_once(task, status=TASK_STATUS_KILLED,
                               stop_reason=reasons.TASK_COGS_CEILING)

    def test_a_late_report_on_terminal_work_is_not_a_transition(self):
        task = self._task()
        TaskService.close_task(
            task.id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        TaskService.accumulate_cost(
            task.id, billed_cost_micros=5, provider_cost_micros=5)
        self.assert_heard_once(task, status=TASK_STATUS_COMPLETED)


class AListenerThatRaisesVetoesNothingTest(TerminalListenersTestBase):
    """A listener is a notification, never a veto (#141 §6.4). The module
    docstring in `work/hooks.py` argues the handling; these cases hold it:
    the transition stands, the announcement is written, the next listener
    still runs, the failure is logged loudly, and the savepoint each listener
    runs under is what makes all four true at once."""

    LOGGER = "apps.platform.work.hooks"

    def _with_a_broken_listener_first(self, broken):
        hooks._listeners[:] = []
        hooks.register_terminal_transition_listener(broken)
        hooks.register_terminal_transition_listener(self._record)

    def _assert_the_kill_stood(self, task, logged):
        self.assert_heard_once(task, status=TASK_STATUS_KILLED,
                               stop_reason=reasons.TASK_COGS_CEILING)
        self.assertEqual(self._events(TaskKilled.EVENT_TYPE).count(), 1)
        self.assertEqual(len(logged.output), 1)
        self.assertIn("work.terminal_listener_failed", logged.output[0])

    def test_an_exception_does_not_un_terminate_the_unit(self):
        def broken(task, transition):
            raise RuntimeError("a product's bug")
        self._with_a_broken_listener_first(broken)
        task = self._task(limit=1_000)
        with self.assertLogs(self.LOGGER, level="ERROR") as logged:
            self.assertTrue(self._kill(task))
        self._assert_the_kill_stood(task, logged)

    def test_a_database_error_leaves_the_transaction_usable(self):
        # Without a savepoint this poisons the enclosing transaction, and the
        # announcement — an INSERT after the listener, in the same
        # transaction — could not be written; the kill flow would then roll
        # the whole transition back and answer False.
        def broken(task, transition):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1/0")
        self._with_a_broken_listener_first(broken)
        task = self._task(limit=1_000)
        with self.assertLogs(self.LOGGER, level="ERROR") as logged:
            self.assertTrue(self._kill(task))
        self._assert_the_kill_stood(task, logged)

    def test_a_listeners_half_written_work_rolls_back_with_it(self):
        def broken(task, transition):
            Task.objects.filter(id=task.id).update(
                external_task_id="written before the listener failed")
            raise RuntimeError("...and then it failed")
        self._with_a_broken_listener_first(broken)
        task = self._task(limit=1_000)
        with self.assertLogs(self.LOGGER, level="ERROR") as logged:
            self.assertTrue(self._kill(task))
        self._assert_the_kill_stood(task, logged)
        self.assertEqual(task.external_task_id, "")


class TheRegistryHasTheRosterShapeTest(TerminalListenersTestBase):
    """The mechanics the seat-roster registry's own test pins, on this one:
    idempotent registration, registration order, a no-op with nobody
    registered — and, because this ticket is a prefactor, that nothing has
    registered yet. The last case is built to go red on the day billing's
    reservation release registers, and that ticket inverts it into the
    roster test's wiring assertion at this address."""

    def test_registration_is_idempotent(self):
        hooks._listeners[:] = []
        hooks.register_terminal_transition_listener(self._record)
        hooks.register_terminal_transition_listener(self._record)
        task = self._task()
        TaskService.close_task(
            task.id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        self.assert_heard_once(task, status=TASK_STATUS_COMPLETED)

    def test_listeners_are_called_in_registration_order(self):
        order = []
        hooks._listeners[:] = []
        hooks.register_terminal_transition_listener(
            lambda task, transition: order.append("first"))
        hooks.register_terminal_transition_listener(
            lambda task, transition: order.append("second"))
        TaskService.close_task(
            self._task().id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        self.assertEqual(order, ["first", "second"])

    def test_no_listener_registered_is_a_no_op(self):
        hooks._listeners[:] = []
        task = self._task()
        _, transitioned = TaskService.close_task(
            task.id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        self.assertTrue(transitioned)

    def test_nothing_is_registered_at_app_ready(self):
        # `self._saved` is the registry exactly as app loading left it.
        self.assertEqual(self._saved, [])


class EveryWriterOfATerminalStateTellsTheListenersTest(
        TerminalListenersTestBase):
    """The structural half of the whole-set claim above. The behavioural
    cases prove the paths that exist today; this one holds the rule that
    made them exhaustive — a status is written in the service module by the
    flip and the cascade and nowhere else, and every function that writes
    one calls the registry — so a third writer arriving without the call
    goes red here rather than on the day a reservation is left open.

    A WRITER IS ANY OF THE WAYS PYTHON OR THE ORM SPELLS ONE: an assignment
    to a `.status` attribute (plain, annotated or augmented), a `setattr`
    naming it, and a queryset `update(...)` or `bulk_update(...)` carrying it
    as a keyword — the door a writer would take to slip past an attribute
    check. It reads the module's source, so a writer outside the service
    module is not its subject; the behavioural cases are."""

    @staticmethod
    def _writes_a_status(node):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            return any(isinstance(t, ast.Attribute) and t.attr == "status"
                       for t in targets)
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Name) and node.func.id == "setattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value == "status"):
                return True
            if (isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"update", "bulk_update"}):
                # `update(status=...)` names it as a keyword; `bulk_update`
                # names it inside its list of fields.
                return (any(kw.arg == "status" for kw in node.keywords)
                        or any(isinstance(n, ast.Constant)
                               and n.value == "status"
                               for arg in node.args for n in ast.walk(arg)))
        return False

    def test_every_function_that_writes_a_status_notifies(self):
        tree = ast.parse(inspect.getsource(services))
        writers, notifying = set(), set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if self._writes_a_status(inner):
                    writers.add(node.name)
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == "notify_terminal_transition"):
                    notifying.add(node.name)
        self.assertEqual(writers, {"_flip", "_cascade"})
        self.assertEqual(writers - notifying, set())

    def test_the_writer_check_sees_each_way_a_status_is_written(self):
        # The vacuity guard on the check above: each spelling it claims to
        # catch, parsed and recognised, and a read of `.status` not.
        for spelling in ("row.status = x", "row.status: str = x",
                         "row.status += x", "setattr(row, 'status', x)",
                         "qs.update(status=x)",
                         "Task.objects.bulk_update(rows, ['status'])"):
            with self.subTest(spelling=spelling):
                statement = ast.parse(spelling).body[0]
                node = (statement.value if isinstance(statement, ast.Expr)
                        else statement)
                self.assertTrue(self._writes_a_status(node))
        read = ast.parse("if row.status == x: pass").body[0].test
        self.assertFalse(self._writes_a_status(read))
