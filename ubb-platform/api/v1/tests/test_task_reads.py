"""Task 14: task read endpoints — the per-unit cost receipt.

Reads the materialized rollups the accumulate primitive maintains
(total_billed_cost_micros, total_provider_cost_micros, event_count) —
never aggregates ubb_usage_event. GET /metering/tasks lists top-level units
only (parent__isnull=True); a subtask's numbers surface in its parent's
detail view via `subtasks`.
"""
import pytest
from django.test import Client

from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestTaskReads:
    def setup_method(self):
        # products=[...] is REQUIRED — routes are gated by _product_check.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.client = Client()

    def _get(self, path):
        return self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _tree(self):
        parent = Task.objects.create(
            tenant=self.tenant, customer=self.customer, balance_snapshot_micros=0,
            task_type="invoice_batch", dim1="eu-west-1",
            provider_cost_limit_micros=5_000_000,
            total_provider_cost_micros=2_010_000,
            total_billed_cost_micros=2_480_000, event_count=412)
        Task.objects.create(
            tenant=self.tenant, customer=self.customer, parent=parent,
            balance_snapshot_micros=0, subtask_type="ocr",
            total_provider_cost_micros=1_740_000, event_count=340)
        return parent

    def test_detail_returns_rollups_and_subtasks(self):
        parent = self._tree()
        r = self._get(f"/api/v1/metering/tasks/{parent.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["task_type"] == "invoice_batch"
        assert body["total_provider_cost_micros"] == 2_010_000
        assert body["dimensions"] == {"dim1": "eu-west-1"}
        assert len(body["subtasks"]) == 1
        assert body["subtasks"][0]["subtask_type"] == "ocr"

    def test_list_returns_top_level_tasks_only(self):
        self._tree()
        r = self._get("/api/v1/metering/tasks")
        assert r.status_code == 200
        assert [t["task_type"] for t in r.json()["data"]] == ["invoice_batch"]

    def test_list_filters_by_task_type(self):
        self._tree()
        Task.objects.create(tenant=self.tenant, customer=self.customer,
                            balance_snapshot_micros=0, task_type="receipt_scan")
        r = self._get("/api/v1/metering/tasks?task_type=receipt_scan")
        assert [t["task_type"] for t in r.json()["data"]] == ["receipt_scan"]

    def test_foreign_task_is_404(self):
        other_tenant = Tenant.objects.create(name="Other", products=["metering"])
        other_customer = Customer.objects.create(tenant=other_tenant, external_id="c2")
        other_task = Task.objects.create(
            tenant=other_tenant, customer=other_customer, balance_snapshot_micros=0,
            task_type="invoice_batch")
        r = self._get(f"/api/v1/metering/tasks/{other_task.id}")
        assert r.status_code == 404
