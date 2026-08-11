"""Task 16: per-task-type unit economics — the number that sets a price.

Aggregates ubb_task, never ubb_posting: per-unit costs are already
materialized by the accumulate primitive, with a subtask's spend rolled into
its parent. GET /metering/analytics/tasks reports run count, mean, p95, and
limit-hit count per KIND of job.
"""
import pytest
from django.test import Client

from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestTaskAnalytics:
    def setup_method(self):
        # products=[...] is REQUIRED — routes are gated by _product_check.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.client = Client()

    def _get(self, path):
        return self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _seed(self):
        for cost in (1_000, 2_000, 3_000, 100_000):
            Task.objects.create(
                tenant=self.tenant, customer=self.customer, balance_snapshot_micros=0,
                task_type="invoice_batch", status="completed",
                provider_cost_limit_micros=50_000,
                total_provider_cost_micros=cost, event_count=1)
        Task.objects.create(
            tenant=self.tenant, customer=self.customer, balance_snapshot_micros=0,
            task_type="receipt_scan", status="completed",
            total_provider_cost_micros=500, event_count=1)

    def test_rollup_by_task_type(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/tasks?group_by=task_type")
        assert r.status_code == 200
        rows = {x["task_type"]: x for x in r.json()["rows"]}
        assert rows["invoice_batch"]["run_count"] == 4
        assert rows["invoice_batch"]["avg_provider_cost_micros"] == 26_500
        assert rows["receipt_scan"]["run_count"] == 1

    def test_p95_is_reported(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/tasks?group_by=task_type")
        rows = {x["task_type"]: x for x in r.json()["rows"]}
        assert rows["invoice_batch"]["p95_provider_cost_micros"] >= 3_000

    def test_limit_hits_are_counted(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/tasks?group_by=task_type")
        rows = {x["task_type"]: x for x in r.json()["rows"]}
        assert rows["invoice_batch"]["limit_hit_count"] == 1

    def test_subtasks_are_excluded_from_run_counts(self):
        self._seed()
        parent = Task.objects.filter(tenant=self.tenant, task_type="invoice_batch").first()
        Task.objects.create(tenant=self.tenant, customer=self.customer, parent=parent,
                            balance_snapshot_micros=0, subtask_type="ocr",
                            total_provider_cost_micros=999)
        r = self._get("/api/v1/metering/analytics/tasks?group_by=task_type")
        rows = {x["task_type"]: x for x in r.json()["rows"]}
        assert rows["invoice_batch"]["run_count"] == 4

    def test_invalid_group_by_is_422(self):
        r = self._get("/api/v1/metering/analytics/tasks?group_by=nope")
        assert r.status_code == 422
