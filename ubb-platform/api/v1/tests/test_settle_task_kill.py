"""One-rule (#37) settle-time kill flow — the async successor to the retired
accept-time run-kill tests.

Task-limit detection moved to settle (exact provider costs); the kill flow is
TaskService.kill_and_announce: idempotent active->killed flip, emitting
task.limit_exceeded ONLY on the winning transition, in its own transaction,
never raising. This file pins the three properties that survive from the old
model: exactly-once emission under a concurrent race, kill-failure isolation
(a settle that triggers a failing kill still completes), and no
re-announcement for a crossing that lands on an already-killed task.
"""
import threading
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TransactionTestCase

from api.v1.tests.test_ingest_endpoint import IngestEndpointTestBase
from apps.metering.usage.models import RawIngestEvent, UsageEvent
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.models import Task
from apps.platform.tasks.services import TaskService
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.billing.wallets.models import Wallet


class ConcurrentKillRaceTest(TransactionTestCase):
    """N callers racing kill_and_announce on the same over-limit task ->
    exactly one transition, exactly one task.limit_exceeded.
    TransactionTestCase (not TestCase): threads need their own DB connections
    to SEE each other's committed rows — under TestCase's wrapping
    transaction the race never actually happens."""

    def setUp(self):
        cache.clear()
        from apps.metering.usage.services.ingest_accept import reset_task_meta_cache
        reset_task_meta_cache()
        self.tenant = Tenant.objects.create(
            name="KillRace", products=["metering", "billing", "metering_async"],
            billing_mode="prepaid", enforcement_mode="enforcing",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="race1")
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        # An over-limit task: the provider total already crossed the limit —
        # exactly the state racing settle workers see when their crossing
        # verdicts all trigger the kill flow.
        self.task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, provider_cost_limit_micros=500_000,
            total_provider_cost_micros=1_000_000, total_billed_cost_micros=1_000_000,
            billing_owner_id=self.customer.id,
        )

    def tearDown(self):
        cache.clear()

    def _kill(self):
        from django.db import connection
        try:
            return TaskService.kill_and_announce(
                self.task.id, "task_limit",
                tenant_id=self.tenant.id, customer_id=self.customer.id)
        finally:
            connection.close()

    # Patched so the on_commit outbox dispatch is inert: TransactionTestCase
    # really commits, and the shared-task .delay would otherwise reach for a
    # live broker. mock.patch swaps the module attribute process-wide, so the
    # worker threads' write_event picks the mock up too.
    @patch("apps.platform.events.tasks.process_single_event")
    def test_concurrent_kill_single_transition_single_event(self, _mock):
        n = 4
        results = [None] * n

        def worker(idx):
            results[idx] = self._kill()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Exactly ONE caller wins the active->killed transition ...
        self.assertEqual(sum(1 for r in results if r is True), 1)
        self.assertEqual(sum(1 for r in results if r is False), n - 1)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "killed")
        self.assertEqual(self.task.metadata.get("kill_reason"), "task_limit")
        # ... and exactly ONE task.limit_exceeded is emitted.
        events = OutboxEvent.objects.filter(event_type="task.limit_exceeded")
        self.assertEqual(events.count(), 1)
        payload = events.get().payload
        self.assertEqual(payload["task_id"], str(self.task.id))
        self.assertEqual(payload["reason"], "task_limit")


class KillFailureIsolationTest(IngestEndpointTestBase):
    """A kill_task crash must be swallowed by kill_and_announce (False +
    task.kill_failed log) and must never poison the settle that triggered it
    — under 200-always/record-always, the event IS recorded, so a kill
    failure can only ever be a loud log."""

    def _crossing_raw(self):
        task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, provider_cost_limit_micros=500_000,
            billing_owner_id=self.customer.id,
        )
        resp = self._post([self._event(task_id=str(task.id),
                                       billed_cost_micros=1_000_000,
                                       provider_cost_micros=1_000_000)])
        self.assertEqual(resp.status_code, 200)
        return task, RawIngestEvent.objects.get()

    def test_kill_and_announce_swallows_and_returns_false(self):
        task, _ = self._crossing_raw()
        with patch.object(TaskService, "kill_task",
                          side_effect=RuntimeError("lock timeout")):
            with self.assertLogs("apps.platform.tasks.services", level="ERROR") as logs:
                transitioned = TaskService.kill_and_announce(
                    task.id, "task_limit",
                    tenant_id=self.tenant.id, customer_id=self.customer.id)
        self.assertFalse(transitioned)
        self.assertTrue(any("task.kill_failed" in m for m in logs.output))
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="task.limit_exceeded").count(), 0)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_settle_completes_when_kill_fails(self, _dispatch):
        task, raw = self._crossing_raw()
        # The kill executes on the settle transaction's on_commit (#112) —
        # run the captured callbacks while the failing kill_task patch holds.
        with patch.object(TaskService, "kill_task",
                          side_effect=RuntimeError("lock timeout")):
            with self.assertLogs("apps.platform.tasks.services", level="ERROR") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    result = UsageService.settle_raw(raw)
        # The settle itself completed — the raw is settled, not poisoned.
        self.assertEqual(result, "settled")
        self.assertTrue(any("task.kill_failed" in m for m in logs.output))
        raw.refresh_from_db()
        self.assertEqual(raw.status, "settled")
        # The event landed and counted; only the kill was lost (the next
        # event's crossing verdict retries it).
        self.assertEqual(UsageEvent.objects.count(), 1)
        task.refresh_from_db()
        self.assertEqual(task.status, "active")
        self.assertEqual(task.total_provider_cost_micros, 1_000_000)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="task.limit_exceeded").count(), 0)


class SecondCrossingNoSecondEventTest(IngestEndpointTestBase):
    """A second settle landing past the limit on an ALREADY-KILLED task is a
    task_not_active verdict, not a crossing — no second kill, no second
    task.limit_exceeded (re-announcing every late event would be spam)."""

    @patch("apps.platform.events.tasks.process_single_event")
    def test_second_settle_crossing_emits_no_second_event(self, _dispatch):
        task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, provider_cost_limit_micros=500_000,
            billing_owner_id=self.customer.id,
        )
        resp = self._post([
            self._event(task_id=str(task.id), billed_cost_micros=1_000_000,
                        provider_cost_micros=1_000_000),
            self._event(task_id=str(task.id), billed_cost_micros=1_000_000,
                        provider_cost_micros=1_000_000),
        ])
        self.assertEqual(resp.status_code, 200)
        raws = list(RawIngestEvent.objects.order_by("created_at"))
        self.assertEqual(len(raws), 2)

        # First settle crosses the limit -> kill + exactly one event. The
        # kill executes on the settle transaction's on_commit (#112).
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(UsageService.settle_raw(raws[0]), "settled")
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="task.limit_exceeded").count(), 1)

        # Second settle on the killed task: still records true costs, but a
        # dead task is task_not_active — never a second announcement.
        self.assertEqual(UsageService.settle_raw(raws[1]), "settled")
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.total_provider_cost_micros, 2_000_000)
        self.assertEqual(task.event_count, 2)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="task.limit_exceeded").count(), 1)
