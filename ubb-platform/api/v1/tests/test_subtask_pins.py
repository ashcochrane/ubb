"""Subtasks — the #38 acceptance pins (spec §L, subtask legs).

Pin 1 (subtask leg)  — the tipping event on a sync subtask limit lands and
                       bills; async subtask limit detected at settle.
Pin 13               — subtask killed ALONE (parent keeps running and
                       counting); rollup into the parent's provider total;
                       parent trip kills the parent and cascades to active
                       subtasks.
Pin 14 (subtask leg) — only the provider total races a subtask limit; both
                       totals on the record and the response.
Start-gate           — refusals parent_task_not_active /
                       subtask_depth_exceeded; subtask default limit +
                       coverage gate; closing a parent auto-completes its
                       active subtasks.
"""
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, Client

from apps.billing.gating.models import RiskConfig
from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import RawIngestEvent, UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.models import Task
from apps.platform.tasks.services import TaskService
from apps.platform.tenants.models import Tenant, TenantApiKey


class SubtaskPinMixin:
    """Fixture + helpers, TestCase-agnostic: the batch-parity pin needs a
    TransactionTestCase (real commits — #112 kills execute on_commit), the
    rest stay on the fast wrapped-transaction TestCase."""

    def setUp(self):
        cache.clear()
        from api.v1 import metering_endpoints
        metering_endpoints._TASK_META_CACHE.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Subtasks", products=["metering", "billing", "metering_async"],
            billing_mode="prepaid",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=100_000_000)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _task(self, limit=None, parent=None, balance=100_000_000):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit,
            billing_owner_id=self.customer.id, parent=parent)

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "request_id": f"req-{uuid.uuid4()}",
            "idempotency_key": f"idem-{uuid.uuid4()}",
        }
        data.update(extra)
        return self.http_client.post(
            "/api/v1/metering/usage", data=json.dumps(data),
            content_type="application/json", **self._auth())

    def _pre_check(self, **extra):
        data = {"customer_id": str(self.customer.id), "start_task": True}
        data.update(extra)
        return self.http_client.post(
            "/api/v1/billing/pre-check", data=json.dumps(data),
            content_type="application/json", **self._auth())

    def _events(self, event_type):
        return OutboxEvent.objects.filter(event_type=event_type)


class SubtaskPinTestBase(SubtaskPinMixin, TestCase):
    pass


@patch("apps.platform.events.tasks.process_single_event")
class Pin1SubtaskTippingEventTest(SubtaskPinTestBase):
    def test_sync_subtask_tipping_event_lands_bills_and_kills_alone(self, _mock):
        parent = self._task(limit=100_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        # The kill executes on the recording transaction's on_commit (#112).
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(sub.id),
                                provider_cost_micros=6_000_000,
                                billed_cost_micros=9_000_000)

        # The tipping event answers 200 and is durably recorded + billed.
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        event = UsageEvent.objects.get(id=body["event_id"])
        self.assertEqual(event.billed_cost_micros, 9_000_000)
        self.assertEqual(event.task_id, sub.id)

        # The subtask is killed ALONE; the response says so, scoped to it.
        sub.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(sub.status, "killed")
        self.assertEqual(sub.metadata["kill_reason"], "subtask_limit")
        self.assertEqual(parent.status, "active")
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "subtask_limit")
        self.assertEqual(body["stop_scope"], "subtask")
        self.assertEqual(body["task_id"], str(sub.id))
        self.assertEqual(body["parent_task_id"], str(parent.id))

        # Exactly one subtask.limit_exceeded, ids explicit; no task-scoped one.
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 1)
        self.assertEqual(self._events("task.limit_exceeded").count(), 0)
        payload = self._events("subtask.limit_exceeded").get().payload
        self.assertEqual(payload["subtask_id"], str(sub.id))
        self.assertEqual(payload["parent_task_id"], str(parent.id))
        self.assertEqual(payload["reason"], "subtask_limit")
        self.assertEqual(payload["total_provider_cost_micros"], 6_000_000)
        self.assertEqual(payload["provider_cost_limit_micros"], 5_000_000)

    def test_async_subtask_limit_detected_at_settle(self, _mock):
        from apps.metering.usage.tasks import settle_raw_events

        parent = self._task()
        sub = self._task(limit=5_000_000, parent=parent)
        resp = self.http_client.post(
            "/api/v1/metering/usage/ingest",
            data=json.dumps({"events": [{
                "customer_id": str(self.customer.id),
                "request_id": "r-async", "idempotency_key": "i-async",
                "task_id": str(sub.id),
                "provider_cost_micros": 6_000_000,
                "billed_cost_micros": 6_000_000,
            }]}),
            content_type="application/json", **self._auth())

        # Accept never rejects for limit reasons and never kills.
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["results"][0]["accepted"])
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")

        # Settle: same verdicts, kill flow, and event as the sync path. The
        # kill executes on the settle transaction's on_commit (#112).
        with self.captureOnCommitCallbacks(execute=True):
            settle_raw_events()
        self.assertEqual(RawIngestEvent.objects.get().status, "settled")
        sub.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(sub.status, "killed")
        self.assertEqual(parent.status, "active")
        # Rollup happened at settle too.
        self.assertEqual(parent.total_provider_cost_micros, 6_000_000)
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 1)


@patch("apps.platform.events.tasks.process_single_event")
class Pin13ContainmentTest(SubtaskPinTestBase):
    def test_subtask_killed_alone_parent_keeps_running_and_counting(self, _mock):
        parent = self._task(limit=100_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        # Trip the subtask's own limit (kill executes at commit — #112).
        with self.captureOnCommitCallbacks(execute=True):
            self._record(task_id=str(sub.id), provider_cost_micros=6_000_000,
                         billed_cost_micros=6_000_000)
        sub.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(sub.status, "killed")
        self.assertEqual(parent.status, "active")
        # Rollup: the parent's provider total carries the subtask's spend.
        self.assertEqual(parent.total_provider_cost_micros, 6_000_000)

        # The parent keeps running AND counting: direct parent events land,
        # and late events on the killed subtask still roll up.
        self._record(task_id=str(parent.id), provider_cost_micros=1_000_000,
                     billed_cost_micros=1_000_000)
        resp = self._record(task_id=str(sub.id), provider_cost_micros=2_000_000,
                            billed_cost_micros=2_000_000)
        body = resp.json()
        self.assertEqual(body["stop_reason"], "task_not_active")
        self.assertEqual(body["stop_scope"], "subtask")
        parent.refresh_from_db()
        self.assertEqual(parent.status, "active")
        self.assertEqual(parent.total_provider_cost_micros, 9_000_000)
        self.assertEqual(parent.event_count, 3)

    def test_parent_trip_kills_parent_and_cascades_to_active_subtasks(self, _mock):
        parent = self._task(limit=10_000_000)
        tripping_sub = self._task(parent=parent)
        sibling_sub = self._task(parent=parent)

        # A subtask event pushes the ROLLED-UP provider total past the
        # parent's limit: the parent's cap covers everything underneath it.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(tripping_sub.id),
                                provider_cost_micros=11_000_000,
                                billed_cost_micros=11_000_000)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_limit")
        self.assertEqual(body["stop_scope"], "task")
        self.assertEqual(body["parent_task_id"], str(parent.id))

        parent.refresh_from_db()
        tripping_sub.refresh_from_db()
        sibling_sub.refresh_from_db()
        self.assertEqual(parent.status, "killed")
        self.assertEqual(parent.metadata["kill_reason"], "task_limit")
        # Containment cuts downward: BOTH subtasks are cascade-killed ...
        self.assertEqual(tripping_sub.status, "killed")
        self.assertEqual(sibling_sub.status, "killed")
        self.assertEqual(sibling_sub.metadata["kill_reason"], "parent_killed")
        # ... but only the parent announces (the subtasks crossed nothing).
        self.assertEqual(self._events("task.limit_exceeded").count(), 1)
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 0)
        payload = self._events("task.limit_exceeded").get().payload
        self.assertEqual(payload["task_id"], str(parent.id))
        self.assertEqual(payload["total_provider_cost_micros"], 11_000_000)

    def test_both_limits_tripping_on_one_event_announce_both(self, _mock):
        parent = self._task(limit=10_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(sub.id),
                                provider_cost_micros=12_000_000,
                                billed_cost_micros=12_000_000)
        body = resp.json()
        # The WIDEST tripped scope wins the scalar slot: stop the whole tree.
        self.assertEqual(body["stop_reason"], "task_limit")
        self.assertEqual(body["stop_scope"], "task")
        # Both kills happened; both announcements fired — the subtask's own
        # crossing is not swallowed by the parent's cascade.
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 1)
        self.assertEqual(self._events("task.limit_exceeded").count(), 1)
        sub.refresh_from_db()
        self.assertEqual(sub.metadata["kill_reason"], "subtask_limit")


@patch("apps.platform.events.tasks.process_single_event")
class Pin13BatchParityTest(SubtaskPinMixin, TransactionTestCase):
    """TransactionTestCase (#112): the mid-batch semantics under test — the
    tipping item's kill LANDS before the next item runs, so that item gets
    task_not_active — exist only when each item's transaction really commits
    (kill execution rides the recording transaction's on_commit)."""

    def test_batch_parity_subtask_verdicts(self, _mock):
        parent = self._task(limit=100_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        events = [{
            "customer_id": str(self.customer.id),
            "request_id": f"rb{i}", "idempotency_key": f"ib{i}",
            "task_id": str(sub.id), "provider_cost_micros": 6_000_000,
        } for i in range(2)]
        resp = self.http_client.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": events}),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 2)
        # Item 1 trips the subtask limit; item 2 lands on the killed subtask
        # — identical to firing the same items as sequential singles.
        self.assertEqual(body["results"][0]["stop_reason"], "subtask_limit")
        self.assertEqual(body["results"][0]["stop_scope"], "subtask")
        self.assertEqual(body["results"][1]["stop_reason"], "task_not_active")
        self.assertEqual(body["results"][1]["stop_scope"], "subtask")
        for item in body["results"]:
            self.assertEqual(item["parent_task_id"], str(parent.id))
        parent.refresh_from_db()
        self.assertEqual(parent.status, "active")
        self.assertEqual(parent.total_provider_cost_micros, 12_000_000)


@patch("apps.platform.events.tasks.process_single_event")
class Pin14SubtaskDenominationTest(SubtaskPinTestBase):
    def test_only_the_provider_total_races_a_subtask_limit(self, _mock):
        parent = self._task()
        sub = self._task(limit=5_000_000, parent=parent)
        # Billed way past the limit, provider under it -> nothing fires.
        resp = self._record(task_id=str(sub.id), provider_cost_micros=1_000_000,
                            billed_cost_micros=50_000_000)
        body = resp.json()
        self.assertFalse(body["stop"])
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 0)

        # Both totals on the record and the response, denominationally explicit.
        self.assertEqual(sub.total_billed_cost_micros, 50_000_000)
        self.assertEqual(sub.total_provider_cost_micros, 1_000_000)
        self.assertEqual(body["task_total_billed_cost_micros"], 50_000_000)
        self.assertEqual(body["task_total_provider_cost_micros"], 1_000_000)

        # The provider total crossing is what kills.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(sub.id),
                                provider_cost_micros=4_500_000,
                                billed_cost_micros=1)
        self.assertEqual(resp.json()["stop_reason"], "subtask_limit")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "killed")


class StartGateSubtaskTest(SubtaskPinTestBase):
    def test_register_subtask_under_active_parent(self):
        parent = self._task()
        body = self._pre_check(parent_task_id=str(parent.id)).json()
        self.assertTrue(body["allowed"])
        self.assertEqual(body["parent_task_id"], str(parent.id))
        sub = Task.objects.get(id=body["task_id"])
        self.assertEqual(sub.parent_id, parent.id)

    def test_top_level_start_has_null_parent(self):
        body = self._pre_check().json()
        self.assertTrue(body["allowed"])
        self.assertIsNone(body["parent_task_id"])

    def test_nonexistent_parent_refused_parent_task_not_active(self):
        body = self._pre_check(parent_task_id=str(uuid.uuid4())).json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["reason"], "parent_task_not_active")
        self.assertEqual(Task.objects.count(), 0)

    def test_terminal_parent_refused_parent_task_not_active(self):
        parent = self._task()
        TaskService.complete_task(parent.id)
        body = self._pre_check(parent_task_id=str(parent.id)).json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["reason"], "parent_task_not_active")

    def test_foreign_customers_parent_refused(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        foreign_parent = TaskService.create_task(
            self.tenant, other, balance_snapshot_micros=0,
            billing_owner_id=other.id)
        body = self._pre_check(parent_task_id=str(foreign_parent.id)).json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["reason"], "parent_task_not_active")

    def test_subtask_parent_refused_subtask_depth_exceeded(self):
        parent = self._task()
        sub = self._task(parent=parent)
        body = self._pre_check(parent_task_id=str(sub.id)).json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["reason"], "subtask_depth_exceeded")

    def test_subtask_default_limit_and_coverage_gate(self):
        # The coverage gate applies to subtask limits the same as task
        # limits: a resolved subtask default refuses without coverage ...
        RiskConfig.objects.create(
            tenant=self.tenant,
            default_subtask_provider_cost_limit_micros=3_000_000)
        parent = self._task()
        body = self._pre_check(parent_task_id=str(parent.id)).json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["reason"], "cost_coverage_required")

        # ... and applies with it on. The SUBTASK default (not the task
        # default) is the fallback for a subtask start.
        self.tenant.require_cost_card_coverage = True
        self.tenant.save(update_fields=["require_cost_card_coverage"])
        body = self._pre_check(parent_task_id=str(parent.id)).json()
        self.assertTrue(body["allowed"])
        self.assertEqual(body["provider_cost_limit_micros"], 3_000_000)

        # A top-level start ignores the subtask default (no task default set
        # -> uncapped, no coverage refusal).
        body = self._pre_check().json()
        self.assertTrue(body["allowed"])
        self.assertIsNone(body["provider_cost_limit_micros"])

    def test_explicit_subtask_limit_wins_over_default(self):
        self.tenant.require_cost_card_coverage = True
        self.tenant.save(update_fields=["require_cost_card_coverage"])
        RiskConfig.objects.create(
            tenant=self.tenant,
            default_subtask_provider_cost_limit_micros=3_000_000)
        parent = self._task()
        body = self._pre_check(parent_task_id=str(parent.id),
                               provider_cost_limit_micros=7_000_000).json()
        self.assertTrue(body["allowed"])
        sub = Task.objects.get(id=body["task_id"])
        self.assertEqual(sub.provider_cost_limit_micros, 7_000_000)


class CloseCascadeTest(SubtaskPinTestBase):
    def test_closing_a_parent_auto_completes_active_subtasks(self):
        parent = self._task()
        sub_active = self._task(parent=parent)
        sub_killed = self._task(parent=parent)
        TaskService.kill_task(sub_killed.id)

        resp = self.http_client.post(
            f"/api/v1/metering/tasks/{parent.id}/close", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "completed")
        self.assertIsNone(body["parent_task_id"])
        sub_active.refresh_from_db()
        sub_killed.refresh_from_db()
        self.assertEqual(sub_active.status, "completed")
        # A killed subtask keeps its state — cleanup never rewrites history.
        self.assertEqual(sub_killed.status, "killed")

    def test_closing_a_subtask_closes_it_alone(self):
        parent = self._task()
        sub = self._task(parent=parent)
        resp = self.http_client.post(
            f"/api/v1/metering/tasks/{sub.id}/close", **self._auth())
        body = resp.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["parent_task_id"], str(parent.id))
        parent.refresh_from_db()
        self.assertEqual(parent.status, "active")
