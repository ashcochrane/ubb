import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import TaskType
from apps.platform.dimensions.models import DimensionDef


@pytest.mark.django_db
class TestTaskTypeRegistry:
    def setup_method(self):
        # products=[...] is REQUIRED — the route is gated by _product_check,
        # so a tenant without "metering" gets 403, not 422.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        # required_dimensions is validated against the declared dimension
        # registry (slot_map) — "region" must exist before a task type can
        # require it.
        DimensionDef.objects.create(tenant=self.tenant, key="region",
                                    slot="dim1", scope="task")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _get(self, path):
        return self.client.get(path, **self._auth())

    def _put(self, path, data):
        return self.client.put(path, data=data, content_type="application/json",
                               **self._auth())

    def test_put_declares_types(self):
        r = self._put("/api/v1/metering/task-types",
                      {"task_types": [
                          {"key": "invoice_batch", "kind": "task",
                           "default_provider_cost_limit_micros": 5_000_000,
                           "required_dimensions": ["region"]},
                          {"key": "ocr", "kind": "subtask",
                           "default_provider_cost_limit_micros": 2_000_000}]})
        assert r.status_code == 200
        assert TaskType.objects.filter(tenant=self.tenant).count() == 2

    def test_put_is_idempotent(self):
        body = {"task_types": [{"key": "invoice_batch", "kind": "task",
                                "default_provider_cost_limit_micros": 5_000_000}]}
        self._put("/api/v1/metering/task-types", body)
        self._put("/api/v1/metering/task-types", body)
        assert TaskType.objects.filter(tenant=self.tenant).count() == 1

    def test_put_updates_the_ceiling(self):
        TaskType.objects.create(tenant=self.tenant, key="invoice_batch", kind="task",
                                default_provider_cost_limit_micros=1_000_000)
        self._put("/api/v1/metering/task-types",
                  {"task_types": [
                      {"key": "invoice_batch", "kind": "task",
                       "default_provider_cost_limit_micros": 9_000_000}]})
        assert TaskType.objects.get(
            tenant=self.tenant, key="invoice_batch"
        ).default_provider_cost_limit_micros == 9_000_000

    def test_undeclared_required_dimension_is_422(self):
        # "region" is pre-declared in setup_method; "customer_tier" is not —
        # the point of this test is that an UNdeclared key is rejected.
        r = self._put("/api/v1/metering/task-types",
                      {"task_types": [
                          {"key": "invoice_batch", "kind": "task",
                           "required_dimensions": ["customer_tier"]}]})
        assert r.status_code == 422
        assert "not declared" in r.json()["detail"]

    def test_get_lists_types(self):
        TaskType.objects.create(tenant=self.tenant, key="ocr", kind="subtask")
        r = self._get("/api/v1/metering/task-types")
        assert r.status_code == 200
        assert r.json()["task_types"][0]["key"] == "ocr"

    def test_put_is_atomic_across_items(self):
        """Override 2: a two-item PUT whose second item is invalid must leave
        ZERO TaskType rows from the first item — the whole loop plus the
        audit write happen inside one transaction.atomic()."""
        r = self._put("/api/v1/metering/task-types",
                      {"task_types": [
                          {"key": "invoice_batch", "kind": "task",
                           "default_provider_cost_limit_micros": 5_000_000},
                          {"key": "ocr", "kind": "subtask",
                           "required_dimensions": ["undeclared_dim"]}]})
        assert r.status_code == 422
        assert TaskType.objects.filter(tenant=self.tenant).count() == 0
