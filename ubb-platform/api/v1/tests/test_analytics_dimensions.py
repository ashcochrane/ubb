"""Task 15: analytics on declared dimensions, filter by task.

Grouping now speaks the tenant's own vocabulary (registry-resolved), not a
hardcoded column allowlist. Bounded dimensions can be grouped by; unbounded
correlation identifiers (task_id) can only be filtered (design D9).
"""
import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.platform.dimensions.models import DimensionDef
from apps.platform.tasks.models import Task


@pytest.mark.django_db
class TestAnalyticsDimensions:
    def setup_method(self):
        # products=[...] is REQUIRED — routes are gated by _product_check.
        # /margin/* needs "subscriptions" as well as "metering".
        self.tenant = Tenant.objects.create(
            # No "subscriptions": plan-as-kernel (#129) retired it from
            # VALID_PRODUCTS, and margin_endpoints is gated on "metering".
            name="T", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.client = Client()

    def _get(self, path):
        return self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _seed(self):
        DimensionDef.objects.create(tenant=self.tenant, key="region", slot="dim1",
                                    scope="task")
        parent = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                     balance_snapshot_micros=0,
                                     task_type="invoice_batch")
        sub = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                  parent=parent,
                                  balance_snapshot_micros=0, subtask_type="ocr")
        for i, (task, dim1, cost) in enumerate([
                (parent, "eu-west-1", 1_000), (sub, "eu-west-1", 2_000),
                (sub, "us-east-1", 4_000)]):
            UsageEvent.objects.create(
                tenant=self.tenant, customer=self.customer, request_id=f"r{i}",
                idempotency_key=f"k{i}", provider="aws_textract",
                event_type="ocr_page", task_id=task.id,
                task_type="invoice_batch",
                subtask_type=task.subtask_type, dim1=dim1,
                provider_cost_micros=cost, billed_cost_micros=cost * 2)
        return parent, sub

    def test_group_by_declared_key_name(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/usage?dimensions=region")
        assert r.status_code == 200
        rows = {x["dimension"]: x["total_provider_cost_micros"]
                for x in r.json()["breakdowns"]["region"]}
        assert rows == {"eu-west-1": 3_000, "us-east-1": 4_000}

    def test_group_by_reserved_subtask_type(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/usage?dimensions=subtask_type")
        rows = {x["dimension"]: x["total_provider_cost_micros"]
                for x in r.json()["breakdowns"]["subtask_type"]}
        assert rows == {"ocr": 6_000, "(unattributed)": 1_000}

    def test_undeclared_key_is_422(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/usage?dimensions=nope")
        assert r.status_code == 422
        assert "unknown dimension" in r.json()["detail"]

    def test_task_id_as_a_dimension_is_422(self):
        """Correlation ids are filter-only (design D9) — grouping by one would
        build a bucket per run."""
        self._seed()
        r = self._get("/api/v1/metering/analytics/usage?dimensions=task_id")
        assert r.status_code == 422

    def test_task_id_filter_scopes_to_one_unit(self):
        parent, sub = self._seed()
        r = self._get(f"/api/v1/metering/analytics/usage?task_id={parent.id}")
        assert r.json()["total_provider_cost_micros"] == 1_000

    def test_include_subtasks_rolls_the_tree_up(self):
        parent, sub = self._seed()
        r = self._get(f"/api/v1/metering/analytics/usage?task_id={parent.id}"
                      "&include_subtasks=true")
        assert r.json()["total_provider_cost_micros"] == 7_000

    def test_usage_list_filters_by_task(self):
        parent, sub = self._seed()
        r = self._get(f"/api/v1/metering/customers/{self.customer.id}/usage"
                      f"?task_id={sub.id}")
        assert len(r.json()["data"]) == 2

    def test_margin_group_by_any_declared_key(self):
        self._seed()
        r = self._get("/api/v1/margin/by-dimension?group_by=subtask_type")
        assert r.status_code == 200
        assert {x["dimension"] for x in r.json()["rows"]} == {"ocr"}
