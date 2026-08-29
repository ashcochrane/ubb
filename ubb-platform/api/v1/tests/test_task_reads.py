"""Task 14: task read endpoints — the per-unit cost receipt.

Reads the materialized rollups the accumulate primitive maintains
(total_billed_cost_micros, total_provider_cost_micros, event_count) —
never aggregates ubb_posting. GET /tasks lists top-level work only
(parent__isnull=True); a contained unit's numbers surface in its parent's
detail view via `subtasks`, and in the containment collection beside it
(#413) — `GET /tasks/{id}/subtasks`, the READ side of containment, whose
write side is the one create route with a parent named.

⚠ THE PATHS MOVED TO THE ROOT PREFIX AND STOPPED BEING GATED (#409). What is
asserted here is unchanged — the rollups and the shape of the receipt — and
`test_task_lifecycle_endpoints.py` beside this one is where the mount and the
absence of a product gate are proved.
"""
import uuid

import pytest
from django.test import Client

from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestTaskReads:
    def setup_method(self):
        # `products` is NOT what admits these calls any more (#409) — the three
        # lifecycle routes are ungated. It is set because `Tenant.clean`
        # refuses a tenant that declares no product at all.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.client = Client()

    def _get(self, path):
        return self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _tree(self):
        parent = Task.objects.create(
            tenant=self.tenant, customer=self.customer, balance_snapshot_micros=0,
            task_type="invoice_batch", grouping_field_1="eu-west-1",
            provider_cost_limit_micros=5_000_000,
            total_provider_cost_micros=2_010_000,
            total_billed_cost_micros=2_480_000, event_count=412)
        Task.objects.create(
            tenant=self.tenant, customer=self.customer, parent=parent,
            balance_snapshot_micros=0, task_type="ocr",
            total_provider_cost_micros=1_740_000, event_count=340)
        return parent

    def test_detail_returns_rollups_and_subtasks(self):
        parent = self._tree()
        r = self._get(f"/api/v1/tasks/{parent.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["task_type"] == "invoice_batch"
        assert body["total_provider_cost_micros"] == 2_010_000
        assert body["dimensions"] == {"grouping_field_1": "eu-west-1"}
        assert len(body["subtasks"]) == 1
        # ONE FIELD, at either altitude (#407): the contained unit's declared
        # kind is read off the same property as its parent's, and it is
        # `parent_task_id` that says which altitude the row sits at.
        assert body["subtasks"][0]["task_type"] == "ocr"
        assert body["subtasks"][0]["parent_task_id"] == str(parent.id)
        assert "subtask_type" not in body["subtasks"][0]

    def test_list_returns_top_level_tasks_only(self):
        self._tree()
        r = self._get("/api/v1/tasks")
        assert r.status_code == 200
        assert [t["task_type"] for t in r.json()["data"]] == ["invoice_batch"]

    def test_list_filters_by_task_type(self):
        self._tree()
        Task.objects.create(tenant=self.tenant, customer=self.customer,
                            balance_snapshot_micros=0, task_type="receipt_scan")
        r = self._get("/api/v1/tasks?task_type=receipt_scan")
        assert [t["task_type"] for t in r.json()["data"]] == ["receipt_scan"]

    def test_the_contained_collection_lists_what_is_inside_one_unit(self):
        """`GET /tasks/{id}/subtasks` — the read side of containment (#413).

        The START of contained work is deliberately NOT here: a start is a start
        and goes through the one create route with a parent named, so there is
        one registration shape at either altitude. This is the read.
        """
        parent = self._tree()
        r = self._get(f"/api/v1/tasks/{parent.id}/subtasks")
        assert r.status_code == 200
        body = r.json()
        assert [t["task_type"] for t in body["data"]] == ["ocr"]
        assert body["data"][0]["parent_task_id"] == str(parent.id)
        assert body["has_more"] is False

    def test_a_unit_with_nothing_inside_it_answers_an_empty_collection(self):
        """An empty collection, never a 404. The unit exists and the honest
        answer about it is that nothing is contained in it — a 404 would say
        the unit does not, and would send a caller looking for the wrong bug."""
        alone = Task.objects.create(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0, task_type="invoice_batch")
        r = self._get(f"/api/v1/tasks/{alone.id}/subtasks")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_the_collection_of_an_unknown_unit_is_a_404(self):
        r = self._get(f"/api/v1/tasks/{uuid.uuid4()}/subtasks")
        assert r.status_code == 404

    def test_the_collection_of_another_tenants_unit_is_a_404(self):
        """The 404 that matters: a real row, read by the tenant it does not
        belong to. `test_foreign_task_is_404` below makes the same claim about
        the detail read, and neither is evidence for the other."""
        r = self._get(f"/api/v1/tasks/{self._a_foreign_task().id}/subtasks")
        assert r.status_code == 404

    def _a_foreign_task(self):
        other_tenant = Tenant.objects.create(name="Other", products=["metering"])
        other_customer = Customer.objects.create(tenant=other_tenant,
                                                 external_id="c2")
        return Task.objects.create(
            tenant=other_tenant, customer=other_customer,
            balance_snapshot_micros=0, task_type="invoice_batch")

    def test_foreign_task_is_404(self):
        r = self._get(f"/api/v1/tasks/{self._a_foreign_task().id}")
        assert r.status_code == 404
