"""The COGS ceiling belongs to the declared KIND of work (design D7).

Precedence: the caller may request LOWER than the kind of work allows, never
higher -> the kind of work's own default -> the tenant default for this
altitude -> uncapped.

⚠ THIS MOVED WITH ITS SUBJECT, NOT WITH ITS OWNER (#410). Every case here used
to drive the ceiling through a flag on the billing-gated affordability call,
which was the only way to register a unit of work. It is `POST /api/v1/tasks`
now, at the root and behind no product gate, so what is asserted is unchanged
and where it is asserted is not. The ceiling itself is untouched: nothing about
how it is configured, denominated or compared moved with it.

⚠ AND A REFUSAL IS NOW A REFUSAL. These verdicts used to ride back inside a
`200` carrying `allowed: false`, because the call they rode on was a question
first and a registration second. A start is not a question, so a request the
ceiling rules refuse answers `422` and one the customer's own state refuses
answers `409` — the same rules, told to the caller as answers to what it asked.
"""
import uuid

import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from apps.platform.work.models import Task, TaskType
from apps.platform.grouping_fields.models import GroupingField


@pytest.mark.django_db
class TestTheCeilingBelongsToTheKindOfWork:
    def setup_method(self):
        # `products` no longer admits these calls — the start route is
        # ungated. It is set because `Tenant.clean` refuses a tenant that
        # declares no product at all, and it names billing because these cases
        # fund a wallet and so want the money-shaped half to run beside the
        # ceiling resolution rather than be skipped.
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 100_000_000
        wallet.save(update_fields=["balance_micros"])
        self.client = Client()

    def _start(self, **body):
        body.setdefault("customer_id", str(self.customer.id))
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        return self.client.post("/api/v1/tasks", data=body,
                                content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _declare(self):
        TaskType.objects.create(tenant=self.tenant, key="invoice_batch", kind="task",
                                default_provider_cost_limit_micros=5_000_000)
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_1",
                                     scope="task", max_cardinality=20)

    def test_ceiling_comes_from_the_task_type(self):
        self._declare()
        r = self._start(task_type="invoice_batch",
                        dimensions={"region": "eu-west-1"})
        assert r.status_code == 200
        body = r.json()
        assert body["provider_cost_limit_micros"] == 5_000_000
        task = Task.objects.get(id=body["task_id"])
        assert task.task_type == "invoice_batch" and task.grouping_field_1 == "eu-west-1"

    def test_caller_may_request_lower(self):
        self._declare()
        r = self._start(task_type="invoice_batch",
                        provider_cost_limit_micros=1_000_000,
                        dimensions={"region": "eu-west-1"})
        assert r.status_code == 200
        assert r.json()["provider_cost_limit_micros"] == 1_000_000

    def test_caller_may_not_request_higher(self):
        self._declare()
        r = self._start(task_type="invoice_batch",
                        provider_cost_limit_micros=99_000_000,
                        dimensions={"region": "eu-west-1"})
        assert r.status_code == 422
        assert "exceeds" in r.json()["detail"]
        assert Task.objects.count() == 0

    def test_undeclared_task_type_is_422(self):
        r = self._start(task_type="nope")
        assert r.status_code == 422
        assert "not declared" in r.json()["detail"]
        assert Task.objects.count() == 0

    def test_missing_required_dimension_is_422(self):
        TaskType.objects.create(tenant=self.tenant, key="invoice_batch", kind="task",
                                required_dimensions=["region"])
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_1",
                                     scope="task")
        r = self._start(task_type="invoice_batch")
        assert r.status_code == 422
        assert "required grouping field" in r.json()["detail"]
        assert Task.objects.count() == 0
