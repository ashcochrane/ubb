import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue


@pytest.mark.django_db
class TestGroupingField:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_key_unique_per_tenant(self):
        t = self._t()
        GroupingField.objects.create(tenant=t, key="region", slot="grouping_field_1", scope="task")
        with pytest.raises(IntegrityError):
            GroupingField.objects.create(tenant=t, key="region", slot="grouping_field_2", scope="task")

    def test_slot_unique_per_tenant(self):
        t = self._t()
        GroupingField.objects.create(tenant=t, key="region", slot="grouping_field_1", scope="task")
        with pytest.raises(IntegrityError):
            GroupingField.objects.create(tenant=t, key="model", slot="grouping_field_1", scope="event")

    def test_same_key_allowed_across_tenants(self):
        a, b = self._t(), self._t()
        GroupingField.objects.create(tenant=a, key="region", slot="grouping_field_1", scope="task")
        GroupingField.objects.create(tenant=b, key="region", slot="grouping_field_1", scope="task")
        assert GroupingField.objects.count() == 2

    def test_value_unique_per_tenant_key(self):
        t = self._t()
        GroupingFieldValue.objects.create(tenant=t, key="region", value="eu-west-1")
        with pytest.raises(IntegrityError):
            GroupingFieldValue.objects.create(tenant=t, key="region", value="eu-west-1")
