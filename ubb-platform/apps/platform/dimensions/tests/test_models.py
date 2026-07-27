import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.platform.dimensions.models import DimensionDef, DimensionValue


@pytest.mark.django_db
class TestDimensionDef:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_key_unique_per_tenant(self):
        t = self._t()
        DimensionDef.objects.create(tenant=t, key="region", slot="dim1", scope="task")
        with pytest.raises(IntegrityError):
            DimensionDef.objects.create(tenant=t, key="region", slot="dim2", scope="task")

    def test_slot_unique_per_tenant(self):
        t = self._t()
        DimensionDef.objects.create(tenant=t, key="region", slot="dim1", scope="task")
        with pytest.raises(IntegrityError):
            DimensionDef.objects.create(tenant=t, key="model", slot="dim1", scope="event")

    def test_same_key_allowed_across_tenants(self):
        a, b = self._t(), self._t()
        DimensionDef.objects.create(tenant=a, key="region", slot="dim1", scope="task")
        DimensionDef.objects.create(tenant=b, key="region", slot="dim1", scope="task")
        assert DimensionDef.objects.count() == 2

    def test_value_unique_per_tenant_key(self):
        t = self._t()
        DimensionValue.objects.create(tenant=t, key="region", value="eu-west-1")
        with pytest.raises(IntegrityError):
            DimensionValue.objects.create(tenant=t, key="region", value="eu-west-1")
