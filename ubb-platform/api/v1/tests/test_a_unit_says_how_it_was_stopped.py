"""The unit-of-work read says why, how and under which control UBB stopped the
work (#551).

A stopped unit's row has carried its stop cause (`reason_code`), the mechanism
that applied it (`trigger_source`) and the control family it belongs to
(`control_family`) since #457–#458, and the four terminal webhooks publish all
three. The unit read published none of them — only `outcome_reason`, which is
the CALLER's word for why work did not deliver and a different concept — so the
first question an integrator asks of a stopped unit, *why?*, had no answer on
`GET /api/v1/tasks/{id}` and the run page could not show one.

They are three fields because they answer three questions (ADR-0006 §5), each
REQUIRED and NULLABLE (#569's rule for a new response fact): null where UBB did
not stop the unit — it is still running, or its own caller ended it — and never
a key that comes and goes. Each case below stops a unit through a real lane
and reads it back through the public routes.

⚠ **THEY ARE UBB'S OWN RECORD, AND THE CALLER'S BAG IS NEVER THEIR SOURCE.**
These facts were keys of `metadata` until R10-W2 — the bag a caller fills at
the start — so a caller could plant every one of them, and only each stop
path's scrub stood between the plant and the read. They are UBB's own columns
now, which nothing a caller sends reaches, held write-once by the database
(`trg_task_declared_transitions`). The last class below plants every
stop-looking key through the public start and drives each path a unit can
take: a real stop answers UBB's facts, every other path answers null, and the
caller's bag is kept exactly as written.

This module says "a unit of work", "contained work" and "the work" throughout,
on the retired-sense rule the registry records for the plural.
"""
from datetime import timedelta

from apps.billing.gating.models import CustomerSpendPool
from apps.platform.events.schemas import TaskKilled
from apps.platform.work import reasons
from apps.platform.work.models import Task
from apps.platform.work.services import (
    CloseDeclaration, TaskService, ceiling_control_id)
from apps.platform.work.tasks import close_abandoned_tasks, reap_stale_tasks
from api.v1.tests.test_every_stop_names_the_control_that_fired import (
    EveryStopNamesItsControlTestBase)
from core.vocabulary import (
    CONTROL_FAMILY_CEILING, CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    OUTCOME_REASON_PARENT_CLOSED, OUTCOME_REASON_TIMEOUT,
    TASK_OUTCOME_DELIVERED, TASK_OUTCOME_FAILED, TASK_STATUS_EXPIRED,
    TASK_TYPE_KIND_SUBTASK,
    TRIGGER_SOURCE_PARENT_CASCADE, TRIGGER_SOURCE_POOL_CROSSING,
    TRIGGER_SOURCE_STALE_REAPER, TRIGGER_SOURCE_USAGE_INGEST)
from apps.platform.tenants.tests._rails import RailActivated

STOP_FIELDS = ("reason_code", "trigger_source", "control_family")

#: Every key of a spelling UBB's stop facts use — the three the read publishes
#: and the control's identity beside them — planted by a caller, with one key
#: that is plainly the caller's own.
PLANTED = {"reason_code": "made_up", "trigger_source": "made_up",
           "control_family": "made_up", "control_id": "made_up",
           "kept": "the caller's own key"}


class AUnitReadTestBase(EveryStopNamesItsControlTestBase):

    def _read(self, path):
        response = self.http_client.get(
            path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _detail(self, unit):
        return self._read(f"/api/v1/tasks/{unit.id}")

    def _stop(self, body):
        return {field: body[field] for field in STOP_FIELDS}


class AStoppedUnitSaysHowTest(RailActivated, AUnitReadTestBase):

    def test_a_ceiling_stop(self):
        unit = self._unit(ceiling=5_000_000)
        self._record(task_id=str(unit.id), provider_cost_micros=5_000_000)

        self.assertEqual(self._stop(self._detail(unit)), {
            "reason_code": reasons.TASK_COGS_CEILING,
            "trigger_source": TRIGGER_SOURCE_USAGE_INGEST,
            "control_family": CONTROL_FAMILY_CEILING})

    def test_a_window_stop(self):
        self._kind("quiet", silence_window_seconds=60,
                   absolute_deadline_seconds=86_400)
        unit = self._unit(task_type="quiet")
        self._age(unit, created=timedelta(minutes=5),
                  reported=timedelta(minutes=2))
        reap_stale_tasks()

        self.assertEqual(self._stop(self._detail(unit)), {
            "reason_code": reasons.SILENCE_WINDOW,
            "trigger_source": TRIGGER_SOURCE_STALE_REAPER,
            "control_family": CONTROL_FAMILY_CEILING})

    def test_a_customer_wide_stop_reaching_the_work(self):
        CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer,
            cap_micros=1_000_000, enforce_mode="blocking")
        unit = self._unit()
        self._record(provider_cost_micros=1_000, bills=2_000_000)

        self.assertEqual(self._stop(self._detail(unit)), {
            "reason_code": reasons.CUSTOMER_SPEND_POOL,
            "trigger_source": TRIGGER_SOURCE_POOL_CROSSING,
            "control_family": CONTROL_FAMILY_CUSTOMER_SPEND_POOL})

    def test_contained_work_stopped_by_its_parent_says_so_on_every_read(self):
        """A cascade announces nothing, so its row is the only place the
        stop is recorded — and the reads are now where that becomes
        visible: the parent's detail, and the contained-work collection."""
        self._kind("pipeline", ceiling=5_000_000)
        self._kind("piece", kind=TASK_TYPE_KIND_SUBTASK)
        parent = self._unit(ceiling=5_000_000, task_type="pipeline")
        contained = self._unit(task_type="piece", parent=parent)
        self._record(task_id=str(contained.id), provider_cost_micros=5_000_000)

        cascaded = {"reason_code": reasons.PARENT_KILLED,
                    "trigger_source": TRIGGER_SOURCE_PARENT_CASCADE,
                    "control_family": CONTROL_FAMILY_CEILING}
        [inside] = self._detail(parent)["subtasks"]
        self.assertEqual(self._stop(inside), cascaded)
        [listed] = self._read(f"/api/v1/tasks/{parent.id}/subtasks")["data"]
        self.assertEqual(self._stop(listed), cascaded)

    def test_the_listing_carries_it_too(self):
        unit = self._unit(ceiling=5_000_000)
        self._record(task_id=str(unit.id), provider_cost_micros=5_000_000)

        [row] = self._read("/api/v1/tasks")["data"]
        self.assertEqual(row["reason_code"], reasons.TASK_COGS_CEILING)


class AUnitUBBDidNotStopSaysNoneTest(RailActivated, AUnitReadTestBase):
    """Null, with the keys present: required and nullable, never absent."""

    def test_running_work(self):
        unit = self._unit()

        body = self._detail(unit)
        self.assertEqual(self._stop(body), dict.fromkeys(STOP_FIELDS))

    def test_contained_work_its_parents_close_withdrew(self):
        """UBB stamps the cascade's mechanism on every row it withdraws, and
        the close is still the caller's ending: the piece's word is
        `parent_closed`, as an outcome reason, and no stop cause."""
        parent = self._unit()
        contained = self._unit(parent=parent)
        TaskService.close_task(parent.id,
                               CloseDeclaration(TASK_OUTCOME_DELIVERED))

        [inside] = self._detail(parent)["subtasks"]
        self.assertEqual(inside["task_id"], str(contained.id))
        self.assertEqual(self._stop(inside), dict.fromkeys(STOP_FIELDS))
        self.assertEqual(inside["outcome_reason"], OUTCOME_REASON_PARENT_CLOSED)

    def test_work_its_own_caller_ended(self):
        """The caller's reason is `outcome_reason`, a different concept from
        UBB's stop cause, and it stays the only one on a closed unit."""
        unit = self._unit()
        TaskService.close_task(unit.id, CloseDeclaration(
            TASK_OUTCOME_FAILED, OUTCOME_REASON_TIMEOUT))

        body = self._detail(unit)
        self.assertEqual(self._stop(body), dict.fromkeys(STOP_FIELDS))
        self.assertEqual(body["outcome_reason"], OUTCOME_REASON_TIMEOUT)


class KeysACallerPlantedAreNeverUBBsStopTest(RailActivated, AUnitReadTestBase):
    """A caller plants every stop-looking key at the start; whichever path the
    unit then takes, the read answers only what UBB recorded — and the
    caller's bag comes through every path exactly as the caller wrote it,
    because no path has to scrub it any more."""

    def _start_planted(self, key, **fields):
        response = self.http_client.post(
            "/api/v1/tasks", content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
            data={"customer_id": str(self.customer.id),
                  "idempotency_key": key, "metadata": PLANTED, **fields})
        self.assertEqual(response.status_code, 200, response.content)
        return Task.objects.get(id=response.json()["task_id"])

    def _keeps_the_callers_bag(self, unit):
        unit.refresh_from_db()
        self.assertEqual(unit.metadata, PLANTED)

    def test_a_real_stop_answers_with_ubbs_own_facts(self):
        unit = self._start_planted("planted-then-killed",
                                   task_cogs_ceiling_micros=5_000_000)
        self._record(task_id=str(unit.id), provider_cost_micros=5_000_000)

        self.assertEqual(self._stop(self._detail(unit)), {
            "reason_code": reasons.TASK_COGS_CEILING,
            "trigger_source": TRIGGER_SOURCE_USAGE_INGEST,
            "control_family": CONTROL_FAMILY_CEILING})
        # The control's identity is not on the read; the announcement reads it
        # off the same row, and it is UBB's too.
        self.assertEqual(self._the_one(TaskKilled)["control_id"],
                         ceiling_control_id(unit))
        self._keeps_the_callers_bag(unit)

    def test_a_silent_expiry_answers_null(self):
        """The hourly safety net expires work nobody reported on and records no
        cause: the unit is `expired`, so the read DOES consult its stop — and
        finds nothing of UBB's, whatever the caller planted."""
        unit = self._start_planted("planted-then-abandoned")
        self._age(unit, created=timedelta(hours=2))

        self.assertEqual(close_abandoned_tasks(), 1)

        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_EXPIRED)
        self.assertEqual(self._stop(self._detail(unit)),
                         dict.fromkeys(STOP_FIELDS))
        self._keeps_the_callers_bag(unit)

    def test_contained_work_its_parents_close_withdrew_answers_null(self):
        """UBB records the cascade's mechanism on the piece it withdraws; the
        close is still the caller's ending, so the read publishes no stop —
        neither UBB's recorded mechanism nor the planted one — on any read."""
        parent = self._unit()
        contained = self._start_planted("planted-then-withdrawn",
                                        parent_task_id=str(parent.id))
        TaskService.close_task(parent.id,
                               CloseDeclaration(TASK_OUTCOME_DELIVERED))

        contained.refresh_from_db()
        self.assertEqual(contained.trigger_source, TRIGGER_SOURCE_PARENT_CASCADE)
        [inside] = self._detail(parent)["subtasks"]
        [listed] = self._read(f"/api/v1/tasks/{parent.id}/subtasks")["data"]
        for read in (inside, listed, self._detail(contained)):
            self.assertEqual(self._stop(read), dict.fromkeys(STOP_FIELDS))
        self._keeps_the_callers_bag(contained)

    def test_running_work_answers_null(self):
        unit = self._start_planted("planted-and-running")

        self.assertEqual(self._stop(self._detail(unit)),
                         dict.fromkeys(STOP_FIELDS))
        [row] = self._read("/api/v1/tasks")["data"]
        self.assertEqual(self._stop(row), dict.fromkeys(STOP_FIELDS))
        self._keeps_the_callers_bag(unit)

    def test_work_its_own_caller_ended_answers_null(self):
        unit = self._start_planted("planted-then-closed")
        TaskService.close_task(unit.id, CloseDeclaration(
            TASK_OUTCOME_FAILED, OUTCOME_REASON_TIMEOUT))

        self.assertEqual(self._stop(self._detail(unit)),
                         dict.fromkeys(STOP_FIELDS))
        self._keeps_the_callers_bag(unit)
