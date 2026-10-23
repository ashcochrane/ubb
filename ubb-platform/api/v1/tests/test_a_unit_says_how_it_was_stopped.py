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

This module says "a unit of work", "contained work" and "the work" throughout,
on the retired-sense rule the registry records for the plural.
"""
from datetime import timedelta

from apps.billing.gating.models import CustomerSpendPool
from apps.platform.work import reasons
from apps.platform.work.services import CloseDeclaration, TaskService
from apps.platform.work.tasks import reap_stale_tasks
from api.v1.tests.test_every_stop_names_the_control_that_fired import (
    EveryStopNamesItsControlTestBase)
from core.vocabulary import (
    CONTROL_FAMILY_CEILING, CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    OUTCOME_REASON_TIMEOUT, TASK_OUTCOME_FAILED, TASK_TYPE_KIND_SUBTASK,
    TRIGGER_SOURCE_PARENT_CASCADE, TRIGGER_SOURCE_POOL_CROSSING,
    TRIGGER_SOURCE_STALE_REAPER, TRIGGER_SOURCE_USAGE_INGEST)

STOP_FIELDS = ("reason_code", "trigger_source", "control_family")


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


class AStoppedUnitSaysHowTest(AUnitReadTestBase):

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


class AUnitUBBDidNotStopSaysNoneTest(AUnitReadTestBase):
    """Null, with the keys present: required and nullable, never absent."""

    def test_running_work(self):
        unit = self._unit()

        body = self._detail(unit)
        self.assertEqual(self._stop(body), dict.fromkeys(STOP_FIELDS))

    def test_keys_the_caller_wrote_into_its_own_metadata_are_not_ubbs(self):
        """`metadata` is also the caller's own bag, carried from the start, so
        a key UBB writes on a stop is one a caller can write first — and the
        read answers only for a unit UBB stopped."""
        response = self.http_client.post(
            "/api/v1/tasks", content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
            data={"customer_id": str(self.customer.id),
                  "idempotency_key": "planted",
                  "metadata": {"reason_code": "made_up",
                               "trigger_source": "made_up",
                               "control_family": "made_up"}})
        self.assertEqual(response.status_code, 200, response.content)

        body = self._read(f"/api/v1/tasks/{response.json()['task_id']}")
        self.assertEqual(self._stop(body), dict.fromkeys(STOP_FIELDS))

    def test_contained_work_its_parents_close_withdrew(self):
        """UBB stamps the cascade's mechanism on every row it withdraws, and
        the close is still the caller's ending: the piece's word is
        `parent_closed`, as an outcome reason, and no stop cause."""
        parent = self._unit()
        contained = self._unit(parent=parent)
        TaskService.close_task(parent.id, CloseDeclaration("delivered"))

        [inside] = self._detail(parent)["subtasks"]
        self.assertEqual(inside["task_id"], str(contained.id))
        self.assertEqual(self._stop(inside), dict.fromkeys(STOP_FIELDS))
        self.assertEqual(inside["outcome_reason"], "parent_closed")

    def test_work_its_own_caller_ended(self):
        """The caller's reason is `outcome_reason`, a different concept from
        UBB's stop cause, and it stays the only one on a closed unit."""
        unit = self._unit()
        TaskService.close_task(unit.id, CloseDeclaration(
            TASK_OUTCOME_FAILED, OUTCOME_REASON_TIMEOUT))

        body = self._detail(unit)
        self.assertEqual(self._stop(body), dict.fromkeys(STOP_FIELDS))
        self.assertEqual(body["outcome_reason"], OUTCOME_REASON_TIMEOUT)
