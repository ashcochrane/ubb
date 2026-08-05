import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task


@pytest.mark.django_db
class TestTaskTyping:
    def _tc(self):
        t = Tenant.objects.create(name="T")
        return t, Customer.objects.create(tenant=t, external_id="c1")

    def test_task_stores_its_type(self):
        t, c = self._tc()
        task = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                   task_type="invoice_batch")
        assert task.task_type == "invoice_batch" and task.subtask_type == ""

    def test_task_type_is_immutable(self):
        t, c = self._tc()
        task = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                   task_type="invoice_batch")
        task.task_type = "receipt_scan"
        with pytest.raises(ValueError, match="task_type is immutable"):
            task.save()

    def test_subtask_type_is_immutable(self):
        t, c = self._tc()
        parent = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                    task_type="invoice_batch")
        sub = Task.objects.create(tenant=t, customer=c, parent=parent,
                                  balance_snapshot_micros=0, subtask_type="ocr")
        sub.subtask_type = "classify"
        with pytest.raises(ValueError, match="subtask_type is immutable"):
            sub.save()

    def test_unrelated_field_still_saves(self):
        t, c = self._tc()
        task = Task.objects.create(tenant=t, customer=c, balance_snapshot_micros=0,
                                   task_type="invoice_batch")
        task.event_count = 5
        task.save()
        task.refresh_from_db()
        assert task.event_count == 5
