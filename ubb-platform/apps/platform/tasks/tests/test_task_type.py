import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.platform.tasks.models import TaskType
from apps.platform.tasks.queries import task_type_policy


@pytest.mark.django_db
class TestTaskType:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_key_unique_per_tenant_and_kind(self):
        t = self._t()
        TaskType.objects.create(tenant=t, key="invoice_batch", kind="task")
        with pytest.raises(IntegrityError):
            TaskType.objects.create(tenant=t, key="invoice_batch", kind="task")

    def test_same_key_allowed_across_kinds(self):
        t = self._t()
        TaskType.objects.create(tenant=t, key="ocr", kind="task")
        TaskType.objects.create(tenant=t, key="ocr", kind="subtask")
        assert TaskType.objects.filter(tenant=t, key="ocr").count() == 2

    def test_policy_returns_plain_dict(self):
        t = self._t()
        TaskType.objects.create(tenant=t, key="invoice_batch", kind="task",
                                default_provider_cost_limit_micros=5_000_000,
                                required_dimensions=["region"])
        assert task_type_policy(t.id, "invoice_batch", "task") == {
            "key": "invoice_batch",
            "default_provider_cost_limit_micros": 5_000_000,
            "required_dimensions": ["region"],
            "retired": False,
        }

    def test_policy_none_for_unknown_key(self):
        t = self._t()
        assert task_type_policy(t.id, "nope", "task") is None
