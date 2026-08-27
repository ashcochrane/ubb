"""Six lifecycle states, and the two invariants they buy (#408, spec §2/§5/§7).

`active` is the only non-terminal state; terminal to anything is never
permitted. The other five are told apart by WHO WROTE THEM, and that is the
whole point of the set:

  * `completed` — the tenant declared delivery, and nothing else writes it (I1).
  * `failed`    — the tenant declared the work could not be delivered.
  * `cancelled` — deliberately stopped or withdrawn, including by a parent's
                  close cascade.
  * `killed`    — UBB stopped it on a spend signal, and nothing tenant-declared
                  lands here (I2).
  * `expired`   — nobody ever told UBB how it ended. Both sweepers write it.

⚠ EVERY ASSERTION HERE NAMES A CONSTANT, NEVER A STRING VALUE. The identity is
the claim: a test spelling `"completed"` would still pass against a model that
had stopped importing the registry, which is the exact debt this ticket pays.

⚠ THE TERMINAL SET IS DERIVED, NOT LISTED. `TERMINAL_TASK_STATUSES` is the
registry's whole set less `active`, so a seventh state arriving is covered by
every loop below on the day it is declared rather than on the day somebody
remembers to extend a list here.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons
from apps.platform.work.models import (
    TASK_STATUS_CHOICES, TERMINAL_TASK_STATUSES, Task)
from apps.platform.work.services import TaskService
from apps.platform.work.tasks import close_abandoned_tasks, reap_stale_tasks
from core.vocabulary import (
    TASK_STATUS_ACTIVE, TASK_STATUS_CANCELLED, TASK_STATUS_COMPLETED,
    TASK_STATUS_EXPIRED, TASK_STATUS_KILLED, TASK_STATUS_VALUES)


class LifecycleTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Lifecycle", products=["metering", "billing"],
            enforcement_mode="enforcing", task_stale_seconds=900)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1")

    def _task(self, parent=None, limit=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=100_000_000,
            provider_cost_limit_micros=limit,
            billing_owner_id=self.customer.id, parent=parent)

    def _force(self, task, status):
        """Put a row into a state without going through a transition, so a
        terminal-state fixture cannot be built out of the very method under
        test."""
        Task.objects.filter(id=task.id).update(
            status=status, completed_at=timezone.now())
        task.refresh_from_db()
        return task

    def _backdate(self, task, *, created, last_event=None):
        Task.objects.filter(id=task.id).update(
            created_at=timezone.now() - created,
            last_event_at=None if last_event is None
            else timezone.now() - last_event)
        task.refresh_from_db()
        return task


class TheStatusSetIsTheRegistrysTest(LifecycleTestBase):
    """G2: the model holds the concept by reference, not as its own list."""

    def test_the_choices_carry_every_declared_value_and_no_other(self):
        self.assertEqual({value for value, _ in TASK_STATUS_CHOICES},
                         set(TASK_STATUS_VALUES))

    def test_the_choices_hold_each_value_once(self):
        values = [value for value, _ in TASK_STATUS_CHOICES]
        self.assertEqual(len(values), len(set(values)))

    def test_active_is_the_only_non_terminal_state(self):
        self.assertEqual(TERMINAL_TASK_STATUSES,
                         set(TASK_STATUS_VALUES) - {TASK_STATUS_ACTIVE})
        self.assertNotIn(TASK_STATUS_ACTIVE, TERMINAL_TASK_STATUSES)

    def test_a_new_row_starts_active(self):
        self.assertEqual(self._task().status, TASK_STATUS_ACTIVE)


class TerminalToAnythingIsNeverPermittedTest(LifecycleTestBase):
    """Every terminal state, against every transition this service offers."""

    #: Every transition this service offers, so the loops below are over the
    #: whole surface rather than over the three somebody thought of.
    TRANSITIONS = ("kill_task", "complete_task", "expire_task")

    def test_each_terminal_state_refuses_each_transition(self):
        for terminal in sorted(TERMINAL_TASK_STATUSES):
            for name in self.TRANSITIONS:
                with self.subTest(terminal=terminal, transition=name):
                    task = self._force(self._task(), terminal)
                    _, transitioned = getattr(TaskService, name)(task.id)
                    task.refresh_from_db()
                    self.assertFalse(transitioned)
                    self.assertEqual(task.status, terminal)

    def test_a_parents_cascade_never_reopens_terminal_contained_work(self):
        for terminal in sorted(TERMINAL_TASK_STATUSES):
            with self.subTest(terminal=terminal):
                parent = self._task()
                child = self._force(self._task(parent=parent), terminal)
                TaskService.complete_task(parent.id)
                child.refresh_from_db()
                self.assertEqual(child.status, terminal)


class CompletedMeansTheTenantDeclaredDeliveryTest(LifecycleTestBase):
    """I1 — nothing but a tenant declaration writes `completed`."""

    def test_an_explicit_close_writes_it(self):
        task = self._task()
        closed, transitioned = TaskService.complete_task(task.id)
        self.assertTrue(transitioned)
        self.assertEqual(closed.status, TASK_STATUS_COMPLETED)

    def test_a_spend_kill_does_not_write_it(self):
        task = self._task()
        killed, _ = TaskService.kill_task(task.id, reason=reasons.TASK_LIMIT)
        self.assertNotEqual(killed.status, TASK_STATUS_COMPLETED)

    def test_the_crash_sweeper_does_not_write_it(self):
        task = self._backdate(self._task(), created=timedelta(hours=2))
        close_abandoned_tasks()
        task.refresh_from_db()
        self.assertNotEqual(task.status, TASK_STATUS_COMPLETED)

    def test_the_stale_reaper_does_not_write_it(self):
        task = self._backdate(self._task(), created=timedelta(hours=2),
                              last_event=timedelta(hours=1))
        reap_stale_tasks()
        task.refresh_from_db()
        self.assertNotEqual(task.status, TASK_STATUS_COMPLETED)

    def test_a_parents_close_cascade_does_not_write_it_on_contained_work(self):
        # The tenant declared delivery of the WHOLE unit. It declared nothing
        # about the contained work, so the cascade withdraws it rather than
        # claiming a delivery nobody made.
        parent = self._task()
        child = self._task(parent=parent)
        TaskService.complete_task(parent.id)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_COMPLETED)
        self.assertEqual(child.status, TASK_STATUS_CANCELLED)

    def test_no_writer_in_this_service_reaches_it_but_the_close(self):
        # The whole-set claim, one level up from the four above: drive every
        # non-close transition against a fresh row and prove none lands here.
        for name, call in (
                ("kill_task", lambda t: TaskService.kill_task(t.id)),
                ("expire_task", lambda t: TaskService.expire_task(t.id))):
            with self.subTest(transition=name):
                task = self._task()
                call(task)
                task.refresh_from_db()
                self.assertNotEqual(task.status, TASK_STATUS_COMPLETED)


class KilledMeansUbbStoppedItOnASpendSignalTest(LifecycleTestBase):
    """I2 — nothing tenant-declared lands in `killed`."""

    def test_a_ceiling_crossing_writes_it(self):
        task = self._task(limit=1_000)
        killed, transitioned = TaskService.kill_task(
            task.id, reason=reasons.TASK_LIMIT)
        self.assertTrue(transitioned)
        self.assertEqual(killed.status, TASK_STATUS_KILLED)

    def test_a_parents_kill_cascade_writes_it_on_contained_work(self):
        parent = self._task()
        child = self._task(parent=parent)
        TaskService.kill_task(parent.id, reason=reasons.TASK_LIMIT)
        child.refresh_from_db()
        self.assertEqual(child.status, TASK_STATUS_KILLED)

    def test_an_explicit_close_never_writes_it(self):
        task = self._task()
        closed, _ = TaskService.complete_task(task.id)
        self.assertNotEqual(closed.status, TASK_STATUS_KILLED)

    def test_a_parents_close_cascade_never_writes_it(self):
        parent = self._task()
        child = self._task(parent=parent)
        TaskService.complete_task(parent.id)
        child.refresh_from_db()
        self.assertNotEqual(child.status, TASK_STATUS_KILLED)

    def test_neither_sweeper_writes_it(self):
        crashed = self._backdate(self._task(), created=timedelta(hours=2))
        close_abandoned_tasks()
        crashed.refresh_from_db()
        self.assertNotEqual(crashed.status, TASK_STATUS_KILLED)

        silent = self._backdate(self._task(), created=timedelta(hours=2),
                                last_event=timedelta(hours=1))
        reap_stale_tasks()
        silent.refresh_from_db()
        self.assertNotEqual(silent.status, TASK_STATUS_KILLED)


class BothSweepersWriteExpiredTest(LifecycleTestBase):
    """§7 — `expired` means exactly *nobody ever told UBB how this ended*."""

    def test_the_crash_sweeper_writes_expired(self):
        task = self._backdate(self._task(), created=timedelta(hours=2))
        self.assertEqual(close_abandoned_tasks(), 1)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_EXPIRED)
        self.assertIsNotNone(task.completed_at)

    def test_the_crash_sweeper_stamps_no_marker(self):
        # The marker said "we gave up waiting" beside a state that claimed a
        # delivery. The state says it now, so the marker is gone.
        task = self._backdate(self._task(), created=timedelta(hours=2))
        close_abandoned_tasks()
        task.refresh_from_db()
        self.assertEqual(task.metadata, {})

    def test_the_stale_reaper_writes_expired(self):
        task = self._backdate(self._task(), created=timedelta(hours=2),
                              last_event=timedelta(hours=1))
        self.assertEqual(reap_stale_tasks(), 1)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_EXPIRED)

    def test_the_stale_reaper_stamps_no_marker(self):
        task = self._backdate(self._task(), created=timedelta(hours=2),
                              last_event=timedelta(hours=1))
        reap_stale_tasks()
        task.refresh_from_db()
        self.assertNotIn("auto_closed", task.metadata)

    def test_the_stale_reaper_still_announces(self):
        # The state changes; the signal does not. A worker whose sibling went
        # silent is told, exactly as before — §19 renames the event later.
        task = self._backdate(self._task(), created=timedelta(hours=2),
                              last_event=timedelta(hours=1))
        reap_stale_tasks()
        task.refresh_from_db()
        self.assertIsNotNone(task.announce_outbox_id)
        self.assertEqual(OutboxEvent.objects.filter(
            id=task.announce_outbox_id).count(), 1)

    def test_an_expiring_parent_expires_its_contained_work(self):
        parent = self._task()
        child = self._task(parent=parent)
        self._backdate(parent, created=timedelta(hours=2))
        close_abandoned_tasks()
        child.refresh_from_db()
        self.assertEqual(child.status, TASK_STATUS_EXPIRED)


class ALateReportOnATerminalUnitStillLandsTest(LifecycleTestBase):
    """The regression guard the acceptance criteria ask for by name.

    Everything else in this slice is about terminality; this is the one thing
    terminality must not touch. COGS is independent of chargeability, so a
    report arriving after the end still costs, still rolls up, and comes back
    with a verdict rather than a refusal.
    """

    def test_every_terminal_state_still_takes_a_late_report(self):
        for terminal in sorted(TERMINAL_TASK_STATUSES):
            with self.subTest(terminal=terminal):
                task = self._force(self._task(), terminal)
                unit, verdicts = TaskService.accumulate_cost(
                    task.id, billed_cost_micros=3_000_000,
                    provider_cost_micros=2_000_000)
                self.assertTrue(verdicts["task_not_active"])
                self.assertFalse(verdicts["crossed_task_limit"])
                self.assertEqual(unit.total_billed_cost_micros, 3_000_000)
                self.assertEqual(unit.total_provider_cost_micros, 2_000_000)
                self.assertEqual(unit.event_count, 1)

    def test_a_late_report_on_terminal_contained_work_rolls_up(self):
        for terminal in sorted(TERMINAL_TASK_STATUSES):
            with self.subTest(terminal=terminal):
                parent = self._task()
                child = self._force(self._task(parent=parent), terminal)
                TaskService.accumulate_cost(
                    child.id, billed_cost_micros=1_000_000,
                    provider_cost_micros=500_000)
                parent.refresh_from_db()
                self.assertEqual(parent.total_billed_cost_micros, 1_000_000)
                self.assertEqual(parent.total_provider_cost_micros, 500_000)
                self.assertEqual(parent.event_count, 1)

    def test_a_terminal_state_does_not_become_a_refusal(self):
        task = self._force(self._task(), TASK_STATUS_EXPIRED)
        unit, _ = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1, provider_cost_micros=1)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_EXPIRED)
        self.assertEqual(unit.event_count, 1)
