import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService


@pytest.mark.django_db
class TestDimensionInheritance:
    def _fixture(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        parent = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                    task_type="invoice_batch", dim1="eu-west-1")
        sub = Task.objects.create(tenant=t, customer=c, parent=parent,
                                  balance_snapshot_micros=0, subtask_type="ocr")
        return t, c, parent, sub

    def _record(self, t, c, task, **kw):
        # record_usage returns a plain result dict (_result()), not the ORM
        # row — fetch the persisted UsageEvent the same way
        # test_attribution_columns.py does, so attribute access below reads
        # the durable columns, not the response envelope.
        r = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key=kw.pop("key", "k1"),
            provider="aws_textract", event_type="ocr_page",
            provider_cost_micros=1000, task_id=task.id, **kw)
        return UsageEvent.objects.get(id=r["event_id"])

    def test_event_inherits_task_type_from_the_root(self):
        t, c, parent, sub = self._fixture()
        e = self._record(t, c, sub)
        assert e.task_type == "invoice_batch"

    def test_event_inherits_subtask_type_from_the_leaf(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, sub).subtask_type == "ocr"

    def test_event_inherits_task_scoped_slot_through_the_parent(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, sub).dim1 == "eu-west-1"

    def test_event_scoped_value_overrides_inheritance(self):
        t, c, parent, sub = self._fixture()
        e = self._record(t, c, sub, dimension_slots={"dim1": "us-east-1"})
        assert e.dim1 == "us-east-1"

    def test_top_level_task_event_has_no_subtask_type(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, parent).subtask_type == ""

    def test_unattributed_event_inherits_nothing(self):
        t = Tenant.objects.create(name="T2")
        c = Customer.objects.create(tenant=t, external_id="c2")
        r = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            provider="openai", event_type="completion", provider_cost_micros=1)
        e = UsageEvent.objects.get(id=r["event_id"])
        assert e.task_type == "" and e.dim1 == ""

    def test_declared_dim1_wins_over_legacy_product_id(self):
        """Task 9's precedence gap, pinned: a caller sending BOTH the legacy
        product_id field and a declared event-scoped dim1 dimension must get
        the declared value — usage_service.py's
        `slots.get("dim1") or product_id or ""` — and this task's inheritance
        layer must not reorder that. product_id never even reaches a task's
        inherited value in this case; the event-scoped declared dimension
        wins over BOTH the legacy field and any task-inherited dim1."""
        t = Tenant.objects.create(name="T3")
        c = Customer.objects.create(tenant=t, external_id="c3")
        parent = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                    task_type="job", dim1="task-scoped-value")
        r = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            provider="openai", event_type="completion", provider_cost_micros=1,
            task_id=parent.id, product_id="legacy-product",
            dimension_slots={"dim1": "declared-value"})
        e = UsageEvent.objects.get(id=r["event_id"])
        assert e.dim1 == "declared-value"
