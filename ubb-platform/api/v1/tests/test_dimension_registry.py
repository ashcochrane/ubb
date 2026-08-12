import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue


@pytest.mark.django_db
class TestDimensionRegistry:
    def setup_method(self):
        # products=[...] is REQUIRED: these routes are gated by _product_check,
        # so a tenant without "metering" gets 403, not 422.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _get(self, path):
        return self.client.get(path, **self._auth())

    def _put(self, path, data):
        return self.client.put(path, data=data, content_type="application/json",
                               **self._auth())

    def test_put_declares_dimensions(self):
        r = self._put("/api/v1/metering/grouping-fields",
                       {"dimensions": [
                           {"key": "region", "slot": "grouping_field_1", "scope": "task",
                            "max_cardinality": 20},
                           {"key": "model", "slot": "grouping_field_2", "scope": "event"}]})
        assert r.status_code == 200
        assert GroupingField.objects.filter(tenant=self.tenant).count() == 2

    def test_get_lists_declared_dimensions(self):
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_1",
                                    scope="task", max_cardinality=20)
        r = self._get("/api/v1/metering/grouping-fields")
        assert r.status_code == 200
        assert r.json()["dimensions"] == [
            {"key": "region", "slot": "grouping_field_1", "scope": "task",
             "max_cardinality": 20, "retired": False}]

    def test_reserved_key_is_422(self):
        r = self._put("/api/v1/metering/grouping-fields",
                       {"dimensions": [
                           {"key": "provider", "slot": "grouping_field_1", "scope": "event"}]})
        assert r.status_code == 422
        assert "reserved" in r.json()["detail"]

    def test_task_id_as_dimension_is_422(self):
        r = self._put("/api/v1/metering/grouping-fields",
                       {"dimensions": [
                           {"key": "task_id", "slot": "grouping_field_1", "scope": "event"}]})
        assert r.status_code == 422
        assert "correlation" in r.json()["detail"]

    def test_slot_collision_on_a_new_key_is_422_not_500(self):
        """Important 4 (final-fixes wave): declaring a second key on a slot
        already bound to a DIFFERENT key used to hit uq_dimension_def_slot's
        IntegrityError uncaught (500) — DimensionService.declare only ever
        looked an existing def up by `key`, never by `slot`. An admin's
        copy-paste mistake (reusing one slot for a second axis) must be a 422
        DimensionError instead."""
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_1",
                                    scope="task")
        r = self._put("/api/v1/metering/grouping-fields",
                       {"dimensions": [
                           {"key": "product", "slot": "grouping_field_1", "scope": "event"}]})
        assert r.status_code == 422
        assert "grouping_field_1" in r.json()["detail"]
        assert "region" in r.json()["detail"]
        # The collision is rejected whole — no partial write.
        assert not GroupingField.objects.filter(tenant=self.tenant, key="product").exists()

    def test_values_endpoint_lists_admitted_values(self):
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_1",
                                    scope="task")
        GroupingFieldValue.objects.create(tenant=self.tenant, key="region", value="eu-west-1")
        r = self._get("/api/v1/metering/grouping-fields/region/values")
        assert r.status_code == 200
        assert r.json()["values"] == ["eu-west-1"]
