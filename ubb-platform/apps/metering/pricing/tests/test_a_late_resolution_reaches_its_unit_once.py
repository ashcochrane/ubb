"""A late resolution reaches its unit of work exactly once (#603, ADR-0020 §7).

A posting counted as unresolved by its unit of work — and by the unit's parent,
for a subtask — is completed later through one of the two settlement doors
(`cost_settlement.settle_provider_cost`, `price_resolution.resolve_customer_price`),
and the door hands the amount to `TaskService.take_up_a_late_resolution`, which
adds it to the totals of the unit and its parent and stops counting it.

That makes "the posting became known" and "the unit's total moved" two writes,
and the owner's review of #614 asked for the one invariant that keeps them
from becoming two independently durable facts:

    The unknown→known transition and the unit's total/count adjustment cannot
    be separated by a crash or a replay in a way that loses the adjustment or
    applies it twice.

Each half is held here, on both doors:

* **a replay adds nothing** — the door's conditional `UPDATE` admits exactly
  one completion, and only a completion reaches the unit;
* **a failure after the posting resolves leaves neither written** — the door
  runs its completion and the unit's adjustment in ONE transaction of its own
  (a savepoint under a caller's), so an exception anywhere in it, a crash in
  the middle of the subtask → parent roll-up included, rolls the posting back
  too;
* **a caller holding no transaction is no exception** — the same holds in
  autocommit, where the posting's write would otherwise commit on its own;
* **concurrent completions cannot both win** — of two racing resolutions one
  completes and the other finds the row already known, and a resolution racing
  a new recording on the same unit loses neither amount.
"""
import threading
from unittest.mock import patch

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase

from apps.metering.pricing.services.cost_settlement import (
    Settlement, settle_provider_cost)
from apps.metering.pricing.services.price_resolution import (
    PriceResolution, resolve_customer_price)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from apps.platform.work.services import TaskService
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

#: What each door completes, how, what it answers when it does, and the unit's
#: total and count it moves. One table, so a case written once covers both.
DOORS = {
    "cost": (settle_provider_cost, "provider_cost_micros", Settlement.SETTLED,
             Settlement.ALREADY_SETTLED, "total_provider_cost_micros",
             "unresolved_event_count"),
    "price": (resolve_customer_price, "billed_cost_micros",
              PriceResolution.RESOLVED, PriceResolution.ALREADY_RESOLVED,
              "total_billed_cost_micros", "unpriced_event_count"),
}


class _AUnitWithAnOpenPosting:
    """A top-level unit, a subtask under it, and one posting on the subtask
    whose cost AND price are open — counted, as the recording path counts
    them, on the subtask and rolled up to its parent."""

    def _arrange(self, *, already=0):
        tenant = Tenant.objects.create(name="T")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        parent = TaskService.create_task(tenant, customer,
                                         balance_snapshot_micros=0)
        subtask = TaskService.create_task(tenant, customer,
                                          balance_snapshot_micros=0,
                                          parent=parent)
        # Inside a transaction, as the recording path calls it: the
        # accumulate primitive locks the unit's rows and asks for its caller's.
        with transaction.atomic():
            if already:
                TaskService.accumulate_cost(
                    subtask.id, billed_cost_micros=already,
                    provider_cost_micros=already)
            TaskService.accumulate_cost(
                subtask.id, billed_cost_micros=None, provider_cost_micros=None,
                costing_status=COSTING_STATUS_UNRESOLVED,
                pricing_status=PRICING_STATUS_UNKNOWN)
        posting = Posting.objects.create(
            tenant=tenant, customer=customer, idempotency_key="late",
            task_id=subtask.id, provider_cost_micros=None,
            costing_status=COSTING_STATUS_UNRESOLVED,
            unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING,
            billed_cost_micros=None, pricing_status=PRICING_STATUS_UNKNOWN)
        return parent, subtask, posting

    def _units(self, parent, subtask, total, count):
        return [Task.objects.values_list(total, count).get(pk=unit.pk)
                for unit in (subtask, parent)]


class AReplayAddsNothingTest(_AUnitWithAnOpenPosting, TestCase):

    def test_the_second_completion_moves_neither_unit(self):
        for side, (door, amount, done, again, total, count) in DOORS.items():
            with self.subTest(door=side):
                parent, subtask, posting = self._arrange()
                self.assertIs(door(posting_id=posting.pk, **{amount: 700}), done)
                once = self._units(parent, subtask, total, count)
                self.assertEqual(once, [(700, 0), (700, 0)])

                self.assertIs(door(posting_id=posting.pk, **{amount: 700}),
                              again)
                self.assertEqual(self._units(parent, subtask, total, count),
                                 once)


class AFailureLeavesNeitherWrittenTest(_AUnitWithAnOpenPosting, TestCase):

    def test_a_failure_in_the_units_adjustment_leaves_the_posting_open(self):
        for side, (door, amount, done, _, total, count) in DOORS.items():
            with self.subTest(door=side):
                parent, subtask, posting = self._arrange()
                with patch.object(TaskService, "take_up_a_late_resolution",
                                  side_effect=RuntimeError("crash")):
                    with self.assertRaises(RuntimeError):
                        door(posting_id=posting.pk, **{amount: 700})
                posting.refresh_from_db()
                self.assertIsNone(getattr(posting, amount))
                self.assertEqual(self._units(parent, subtask, total, count),
                                 [(0, 1), (0, 1)])

                # And the completion is still there to be made, once.
                self.assertIs(door(posting_id=posting.pk, **{amount: 700}), done)
                self.assertEqual(self._units(parent, subtask, total, count),
                                 [(700, 0), (700, 0)])

    def test_a_crash_between_the_parent_and_the_subtask_moves_neither(self):
        """The roll-up is inside the same guarantee: the parent's row is
        written first (the lock order), and a failure saving the subtask's
        takes the parent's write and the posting's back with it."""
        real_save = Task.save
        saved = []

        def save_then_crash(task, *args, **kwargs):
            saved.append(task.pk)
            if len(saved) == 2:
                raise RuntimeError("crash between the parent and the subtask")
            return real_save(task, *args, **kwargs)

        for side, (door, amount, _, _, total, count) in DOORS.items():
            with self.subTest(door=side):
                saved.clear()
                parent, subtask, posting = self._arrange()
                with patch.object(Task, "save", save_then_crash):
                    with self.assertRaises(RuntimeError):
                        door(posting_id=posting.pk, **{amount: 700})
                self.assertEqual(saved, [parent.pk, subtask.pk])
                posting.refresh_from_db()
                self.assertIsNone(getattr(posting, amount))
                self.assertEqual(self._units(parent, subtask, total, count),
                                 [(0, 1), (0, 1)])


class WithNoTransactionOfItsOwnTest(_AUnitWithAnOpenPosting,
                                    TransactionTestCase):
    """A caller in autocommit: every statement commits on its own unless the
    door opens a transaction. Without one, the posting's completion would be
    durable before the unit's adjustment ran — and the adjustment's row locks
    cannot even be taken outside a transaction."""

    def test_a_completion_reaches_both_units(self):
        for side, (door, amount, done, _, total, count) in DOORS.items():
            with self.subTest(door=side):
                parent, subtask, posting = self._arrange()
                self.assertIs(door(posting_id=posting.pk, **{amount: 700}), done)
                self.assertEqual(self._units(parent, subtask, total, count),
                                 [(700, 0), (700, 0)])

    def test_a_failure_leaves_the_committed_posting_open(self):
        for side, (door, amount, _, _, total, count) in DOORS.items():
            with self.subTest(door=side):
                parent, subtask, posting = self._arrange()
                with patch.object(TaskService, "take_up_a_late_resolution",
                                  side_effect=RuntimeError("crash")):
                    with self.assertRaises(RuntimeError):
                        door(posting_id=posting.pk, **{amount: 700})
                posting.refresh_from_db()
                self.assertIsNone(getattr(posting, amount))
                self.assertEqual(self._units(parent, subtask, total, count),
                                 [(0, 1), (0, 1)])


class ConcurrentCompletionsTest(_AUnitWithAnOpenPosting, TransactionTestCase):
    """Two threads, real Postgres row locking — the pattern of
    `test_cost_settlement.ASecondSettlementLosesCleanlyTest`: the fixture is
    committed before the workers start, a `Barrier` puts both inside the
    critical section at once, and each worker closes its connection."""

    def _race(self, *work):
        barrier = threading.Barrier(len(work))
        failures = []

        def run(act):
            try:
                barrier.wait(timeout=10)
                act()
            except Exception as error:            # pragma: no cover - reported
                failures.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(act,)) for act in work]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(failures, [])

    def test_of_two_racing_resolutions_one_reaches_the_units(self):
        for side, (door, amount, done, again, total, count) in DOORS.items():
            with self.subTest(door=side):
                parent, subtask, posting = self._arrange()
                answers = []
                self._race(*[lambda: answers.append(
                    door(posting_id=posting.pk, **{amount: 700}))] * 2)
                self.assertEqual(sorted(a.value for a in answers),
                                 sorted([done.value, again.value]))
                self.assertEqual(self._units(parent, subtask, total, count),
                                 [(700, 0), (700, 0)])

    def test_a_resolution_racing_a_recording_loses_neither_amount(self):
        """The unit's row is read and written under its lock on both paths, so
        neither total overwrites the other — and the resolution, which takes
        the posting before the unit (the reverse of `core/locking.py`'s
        order), meets no cycle: the recording path holds the unit and writes
        only the posting it is creating, which no resolution can hold."""
        parent, subtask, posting = self._arrange(already=50)

        def record():
            with transaction.atomic():
                TaskService.accumulate_cost(
                    subtask.id, billed_cost_micros=30, provider_cost_micros=30)

        self._race(
            lambda: settle_provider_cost(posting_id=posting.pk,
                                         provider_cost_micros=700),
            record)
        self.assertEqual(
            self._units(parent, subtask, "total_provider_cost_micros",
                        "unresolved_event_count"),
            [(780, 0), (780, 0)])
