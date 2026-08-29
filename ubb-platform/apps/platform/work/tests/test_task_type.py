import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import TaskType
from apps.platform.work.queries import task_type_policy


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
        """The WHOLE dict, so a key arriving or leaving is read by a person.

        A per-key assertion would pass while a policy field rode along beside
        the ones it named — and every field here is a bound something else
        resolves a ladder against, so one appearing unannounced is exactly the
        change worth seeing.
        """
        t = self._t()
        TaskType.objects.create(tenant=t, key="invoice_batch", kind="task",
                                default_provider_cost_limit_micros=5_000_000,
                                silence_window_seconds=1200,
                                absolute_deadline_seconds=7200,
                                required_dimensions=["region"])
        assert task_type_policy(t.id, "invoice_batch", "task") == {
            "key": "invoice_batch",
            "default_provider_cost_limit_micros": 5_000_000,
            "silence_window_seconds": 1200,
            "absolute_deadline_seconds": 7200,
            "required_dimensions": ["region"],
            "retired": False,
        }

    def test_a_kind_of_work_that_declares_no_window_says_so_rather_than_zero(self):
        """NULL and 0 are different declarations at the silence window, so the
        read contract must not flatten one into the other on its way out."""
        t = self._t()
        TaskType.objects.create(tenant=t, key="unbounded", kind="task")
        policy = task_type_policy(t.id, "unbounded", "task")
        assert policy["silence_window_seconds"] is None
        assert policy["absolute_deadline_seconds"] is None

    def test_policy_none_for_unknown_key(self):
        t = self._t()
        assert task_type_policy(t.id, "nope", "task") is None
