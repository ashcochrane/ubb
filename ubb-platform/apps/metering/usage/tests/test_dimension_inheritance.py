import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService


@pytest.mark.django_db
class TestDimensionInheritance:
    def _fixture(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        parent = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                    task_type="invoice_batch", grouping_field_1="eu-west-1")
        sub = Task.objects.create(tenant=t, customer=c, parent=parent,
                                  balance_snapshot_micros=0, subtask_type="ocr")
        return t, c, parent, sub

    def _record(self, t, c, task, **kw):
        # record_usage returns a plain result dict (_result()), not the ORM
        # row — fetch the persisted Posting the same way
        # test_attribution_columns.py does, so attribute access below reads
        # the durable columns, not the response envelope.
        r = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key=kw.pop("key", "k1"),
            provider="aws_textract", event_type="ocr_page",
            provider_cost_micros=1000, task_id=task.id, **kw)
        return Posting.objects.get(id=r["event_id"])

    def test_event_inherits_task_type_from_the_root(self):
        t, c, parent, sub = self._fixture()
        e = self._record(t, c, sub)
        assert e.task_type == "invoice_batch"

    def test_event_inherits_subtask_type_from_the_leaf(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, sub).subtask_type == "ocr"

    def test_event_inherits_task_scoped_slot_through_the_parent(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, sub).grouping_field_1 == "eu-west-1"

    def test_event_scoped_value_overrides_inheritance(self):
        t, c, parent, sub = self._fixture()
        e = self._record(t, c, sub, dimension_slots={"grouping_field_1": "us-east-1"})
        assert e.grouping_field_1 == "us-east-1"

    def test_top_level_task_event_has_no_subtask_type(self):
        t, c, parent, sub = self._fixture()
        assert self._record(t, c, parent).subtask_type == ""

    def test_unattributed_event_inherits_nothing(self):
        t = Tenant.objects.create(name="T2")
        c = Customer.objects.create(tenant=t, external_id="c2")
        r = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            provider="openai", event_type="completion", provider_cost_micros=1)
        e = Posting.objects.get(id=r["event_id"])
        assert e.task_type == "" and e.grouping_field_1 == ""

    def test_product_id_is_gone_from_the_record_usage_surface(self):
        """The legacy `product_id` wire field (and its fold onto dim1) was
        deleted wholesale (final-fixes wave, Critical 1+2) — it broke
        accept/settle price parity AND bypassed the dimension cardinality
        cap. `product_id` is no longer a parameter of
        UsageService.record_usage at all, so passing it is a plain
        TypeError, same as any other unrecognized kwarg — there is no
        precedence to pin anymore because there is no second source for
        dim1 to arbitrate against."""
        t = Tenant.objects.create(name="T3")
        c = Customer.objects.create(tenant=t, external_id="c3")
        with pytest.raises(TypeError):
            UsageService.record_usage(
                tenant=t, customer=c, request_id="r1", idempotency_key="k1",
                provider="openai", event_type="completion", provider_cost_micros=1,
                product_id="legacy-product")

    def test_declared_dim1_wins_over_task_inheritance(self):
        """dim1's only source is a declared event-scoped dimension
        (`dimension_slots`) — when both an event-scoped declared value and a
        task-inherited dim1 are present, the event-scoped value wins (D6
        precedence), unchanged by product_id's removal."""
        t = Tenant.objects.create(name="T3")
        c = Customer.objects.create(tenant=t, external_id="c3")
        parent = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                    task_type="job", grouping_field_1="task-scoped-value")
        r = UsageService.record_usage(
            tenant=t, customer=c, request_id="r1", idempotency_key="k1",
            provider="openai", event_type="completion", provider_cost_micros=1,
            task_id=parent.id,
            dimension_slots={"grouping_field_1": "declared-value"})
        e = Posting.objects.get(id=r["event_id"])
        assert e.grouping_field_1 == "declared-value"
