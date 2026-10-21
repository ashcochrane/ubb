"""A delivered unit's Charge reaches its billed total exactly once (#553 A9,
ADR-0021 §3).

The close that wins the transition into the delivered state writes the Charge,
and the Charge's projection writes its posting and moves the unit's
`total_billed_cost_micros` — two writes, which must never become two
independently durable facts. That is the owner's standard from the review of
#614 (ADR-0020 §7), held here on the Charge as the late-resolution door holds
it on a posting (`apps/metering/pricing/tests/
test_a_late_resolution_reaches_its_unit_once.py`):

* **a replayed close adds nothing** — only the winning transition writes a
  Charge, and only a Charge reaches the total;
* **a failure after the posting is written leaves neither** — the projection
  takes the adjustment up and writes its posting (in that order, the canonical
  lock order's) in one transaction of its own, inside the close's `atomic`, so
  an exception raised after both — at the outbox write that follows the
  posting — takes the adjustment, the posting, the Charge and the transition
  back together;
* **a caller holding no transaction is no exception** — in autocommit the
  projection's own transaction is what keeps the two together;
* **two racing closes add once** — one wins the transition, the other replays.

And the totals the Charge never reaches — provider cost, event count, the
unpriced count — are asserted beside the one it does, on every path.
"""
import json
import threading
from unittest.mock import patch

from django.db import connection, transaction
from django.test import Client, TestCase, TransactionTestCase

from api.v1.schemas import CloseTaskRequest
from api.v1.task_endpoints import close
from api.v1.tests._helpers import THE_AGREED_PRICE, a_tenant_selling_whole_work
from apps.metering.pricing.models import Charge
from apps.metering.pricing.services import charge_projection
from apps.metering.pricing.services.charge_service import (
    charge_for_delivered_work)
from apps.metering.usage.models import Posting
from apps.platform.work.models import Task
from apps.platform.work.services import CloseDeclaration, TaskService
from core.vocabulary import (
    TASK_OUTCOME_DELIVERED, TASK_STATUS_ACTIVE, USAGE_EVENT_KIND_TASK_CHARGE)

DELIVERED = CloseTaskRequest(outcome=TASK_OUTCOME_DELIVERED)

#: The billed total holding the Charge and nothing else moved: no supplier
#: work, no event, nothing left unpriced — `(billed, provider, events,
#: unpriced)`, as `_totals` reads them.
CHARGED_ALONE = (THE_AGREED_PRICE, 0, 0, 0)


def _after_the_posting():
    """A failure raised AFTER both writes: at the outbox write that follows
    the posting, once the adjustment is taken up and the posting is written."""
    return patch.object(charge_projection, "write_event",
                        side_effect=RuntimeError("after the posting"))


class _ADeliverableUnit:
    """A billing tenant's unit of work sold at one agreed price, started
    through the route and not yet closed. Postpaid, so the start reserves
    nothing and no wallet is in play."""

    def _arrange(self):
        self.selling = a_tenant_selling_whole_work(billing_mode="postpaid")
        response = Client().post(
            "/api/v1/tasks", data=json.dumps(self.selling.start_body()),
            content_type="application/json", **self.selling.auth())
        assert response.status_code == 200, response.content
        return response.json()["task_id"]

    def _close(self, task_id):
        return close(self.selling.tenant, task_id, DELIVERED)

    def _the_unit(self, task_id):
        unit = Task.objects.get(id=task_id)
        return {"status": unit.status,
                "billed": unit.total_billed_cost_micros,
                "provider": unit.total_provider_cost_micros,
                "events": unit.event_count,
                "unpriced": unit.unpriced_event_count}

    def _charge_postings(self, task_id):
        return Posting.objects.filter(task_id=task_id,
                                      kind=USAGE_EVENT_KIND_TASK_CHARGE)

    def _totals(self, task_id):
        unit = self._the_unit(task_id)
        return (unit["billed"], unit["provider"], unit["events"],
                unit["unpriced"])


class AReplayedCloseAddsNothingTest(_ADeliverableUnit, TestCase):

    def test_the_close_that_creates_the_charge_includes_it(self):
        task_id = self._arrange()

        closed = self._close(task_id)

        self.assertTrue(closed["charge_created"])
        self.assertEqual(closed["total_billed_cost_micros"], THE_AGREED_PRICE)
        self.assertEqual(closed["total_provider_cost_micros"], 0)
        self.assertEqual(closed["event_count"], 0)
        self.assertEqual(closed["unpriced_event_count"], 0)

    def test_a_replay_adds_nothing(self):
        task_id = self._arrange()
        self._close(task_id)

        replayed = self._close(task_id)

        self.assertTrue(replayed["replayed"])
        self.assertEqual(replayed["total_billed_cost_micros"], THE_AGREED_PRICE)
        self.assertEqual(self._totals(task_id), CHARGED_ALONE)
        self.assertEqual(Charge.objects.filter(task_id=task_id).count(), 1)
        self.assertEqual(self._charge_postings(task_id).count(), 1)


class AFailureAfterThePostingLeavesNeitherTest(_ADeliverableUnit, TestCase):

    def test_a_failure_after_the_posting_takes_both_writes_back(self):
        """The adjustment is taken up and the posting written, and then the
        close fails: nothing of it survives — no total, no posting, no
        Charge, no transition — so a retry finds the unit exactly as it was
        and charges it once."""
        task_id = self._arrange()

        with _after_the_posting():
            with self.assertRaisesRegex(RuntimeError, "after the posting"):
                self._close(task_id)

        self.assertEqual(self._charge_postings(task_id).count(), 0)
        self.assertEqual(Charge.objects.filter(task_id=task_id).count(), 0)
        unit = self._the_unit(task_id)
        self.assertEqual(unit["status"], TASK_STATUS_ACTIVE)
        self.assertEqual(unit["billed"], 0)

    def test_a_failure_in_the_adjustment_writes_no_posting(self):
        """The adjustment comes first, so its failure stops the projection
        before any posting exists."""
        task_id = self._arrange()

        with patch.object(TaskService, "take_up_a_charge",
                          side_effect=RuntimeError("the adjustment failed")):
            with self.assertRaisesRegex(RuntimeError, "adjustment failed"):
                self._close(task_id)

        self.assertEqual(self._charge_postings(task_id).count(), 0)
        self.assertEqual(Charge.objects.filter(task_id=task_id).count(), 0)
        self.assertEqual(self._the_unit(task_id)["billed"], 0)

    def test_the_retry_then_charges_it_once(self):
        task_id = self._arrange()
        with _after_the_posting():
            with self.assertRaises(RuntimeError):
                self._close(task_id)

        self._close(task_id)

        self.assertEqual(self._totals(task_id), CHARGED_ALONE)
        self.assertEqual(self._charge_postings(task_id).count(), 1)


class WithNoTransactionOfItsOwnTest(_ADeliverableUnit, TransactionTestCase):
    """In autocommit each statement commits on its own, so a posting written
    by a projection holding no transaction would be durable before the
    adjustment ran. The projection's own `atomic` is what keeps them one."""

    def _delivered_without_a_charge(self):
        """Delivered by the kernel's close alone, so no Charge exists yet. In
        a transaction of the fixture's own: the close takes a row lock, and
        a red from the fixture would not be the projection's."""
        task_id = self._arrange()
        with transaction.atomic():
            closed, _ = TaskService.close_task(
                task_id, CloseDeclaration.declared(TASK_OUTCOME_DELIVERED))
        return closed

    def test_the_posting_and_the_total_land_together(self):
        closed = self._delivered_without_a_charge()

        charge_for_delivered_work(closed)

        self.assertEqual(self._charge_postings(closed.id).count(), 1)
        self.assertEqual(self._totals(closed.id), CHARGED_ALONE)

    def test_a_failure_leaves_neither_write_committed(self):
        """Both writes made, then a failure: the projection's own transaction
        takes both back though nobody else holds one. (The Charge row itself
        is the CALLER's to keep with its projection — `project_the_charge`
        says so — and this caller holds no transaction, so it is not asked
        about here.)"""
        closed = self._delivered_without_a_charge()

        with _after_the_posting():
            with self.assertRaises(RuntimeError):
                charge_for_delivered_work(closed)

        self.assertEqual(self._charge_postings(closed.id).count(), 0)
        self.assertEqual(self._the_unit(closed.id)["billed"], 0)


class TwoRacingClosesTest(_ADeliverableUnit, TransactionTestCase):
    """Two threads, real Postgres row locking: both inside the close at once,
    one wins the transition and the other replays."""

    def test_two_racing_closes_add_the_charge_once(self):
        task_id = self._arrange()
        barrier = threading.Barrier(2)
        answers, failures = [], []

        def run():
            try:
                barrier.wait(timeout=10)
                answers.append(self._close(task_id))
            except Exception as error:            # pragma: no cover - reported
                failures.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(failures, [])
        self.assertEqual(sorted(answer["replayed"] for answer in answers),
                         [False, True])
        self.assertEqual(self._totals(task_id), CHARGED_ALONE)
        self.assertEqual(Charge.objects.filter(task_id=task_id).count(), 1)

