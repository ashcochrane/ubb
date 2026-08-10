import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from apps.platform.work.models import Task, TaskType
from apps.platform.grouping_fields.models import GroupingField


@pytest.mark.django_db
class TestPreCheckTaskType:
    def setup_method(self):
        # products=[...] is REQUIRED: the route is gated by _product_check,
        # so a tenant without "billing" gets 403, not 422.
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        # A resolved non-null COGS limit is refused without this (see
        # RiskServiceTaskTest._enable_coverage) — these tests are about
        # ceiling RESOLUTION, not the coverage gate.
        self.tenant.require_cost_card_coverage = True
        self.tenant.save(update_fields=["require_cost_card_coverage"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 100_000_000
        wallet.save(update_fields=["balance_micros"])
        self.client = Client()

    def _post(self, path, data):
        return self.client.post(path, data=data, content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _declare(self):
        TaskType.objects.create(tenant=self.tenant, key="invoice_batch", kind="task",
                                default_provider_cost_limit_micros=5_000_000)
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="dim1",
                                    scope="task", max_cardinality=20)

    def test_ceiling_comes_from_the_task_type(self):
        self._declare()
        r = self._post("/api/v1/billing/pre-check",
                        {"customer_id": str(self.customer.id), "start_task": True,
                         "task_type": "invoice_batch",
                         "dimensions": {"region": "eu-west-1"}})
        assert r.status_code == 200
        body = r.json()
        assert body["allowed"] is True
        assert body["provider_cost_limit_micros"] == 5_000_000
        task = Task.objects.get(id=body["task_id"])
        assert task.task_type == "invoice_batch" and task.dim1 == "eu-west-1"

    def test_caller_may_request_lower(self):
        self._declare()
        r = self._post("/api/v1/billing/pre-check",
                        {"customer_id": str(self.customer.id), "start_task": True,
                         "task_type": "invoice_batch",
                         "provider_cost_limit_micros": 1_000_000,
                         "dimensions": {"region": "eu-west-1"}})
        assert r.status_code == 200
        assert r.json()["provider_cost_limit_micros"] == 1_000_000

    def test_caller_may_not_request_higher(self):
        self._declare()
        r = self._post("/api/v1/billing/pre-check",
                        {"customer_id": str(self.customer.id), "start_task": True,
                         "task_type": "invoice_batch",
                         "provider_cost_limit_micros": 99_000_000,
                         "dimensions": {"region": "eu-west-1"}})
        assert r.status_code == 422
        assert "exceeds" in r.json()["detail"]

    def test_undeclared_task_type_is_422(self):
        r = self._post("/api/v1/billing/pre-check",
                        {"customer_id": str(self.customer.id), "start_task": True,
                         "task_type": "nope"})
        assert r.status_code == 422
        assert "not declared" in r.json()["detail"]

    def test_missing_required_dimension_is_422(self):
        TaskType.objects.create(tenant=self.tenant, key="invoice_batch", kind="task",
                                required_dimensions=["region"])
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="dim1",
                                    scope="task")
        r = self._post("/api/v1/billing/pre-check",
                        {"customer_id": str(self.customer.id), "start_task": True,
                         "task_type": "invoice_batch"})
        assert r.status_code == 422
        assert "required dimension" in r.json()["detail"]
