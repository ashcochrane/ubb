import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue
from core.vocabulary import (
    GROUPING_FIELD_SCOPE_EVENT,
    GROUPING_FIELD_SCOPE_VALUES,
    RESERVED_GROUPING_AXIS_VALUES,
)


@pytest.mark.django_db
class TestGroupingFieldRegistry:
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
                       {"grouping_fields": [
                           {"key": "region", "slot": "grouping_field_1", "scope": "task",
                            "max_cardinality": 20},
                           {"key": "model", "slot": "grouping_field_2", "scope": "event"}]})
        assert r.status_code == 200
        assert GroupingField.objects.filter(tenant=self.tenant).count() == 2

    def test_get_lists_declared_grouping_fields(self):
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_1",
                                    scope="task", max_cardinality=20)
        r = self._get("/api/v1/metering/grouping-fields")
        assert r.status_code == 200
        assert r.json()["grouping_fields"] == [
            {"key": "region", "slot": "grouping_field_1", "scope": "task",
             "max_cardinality": 20, "retired": False}]

    def test_reserved_key_is_422(self):
        r = self._put("/api/v1/metering/grouping-fields",
                       {"grouping_fields": [
                           {"key": "provider", "slot": "grouping_field_1", "scope": "event"}]})
        assert r.status_code == 422
        assert "reserved" in r.json()["detail"]

    def test_task_id_as_dimension_is_422(self):
        r = self._put("/api/v1/metering/grouping-fields",
                       {"grouping_fields": [
                           {"key": "task_id", "slot": "grouping_field_1", "scope": "event"}]})
        assert r.status_code == 422
        assert "correlation" in r.json()["detail"]

    def test_every_axis_the_registry_reserves_is_refused(self):
        """The reserved words are the registry's `reserved_grouping_axis`
        (#544), so this walks the generated set rather than naming one of them:
        an axis the registry reserves and this route lets a tenant declare
        underneath would leave one request word naming two axes."""
        assert RESERVED_GROUPING_AXIS_VALUES, "the registry reserves no axis"
        for axis in sorted(RESERVED_GROUPING_AXIS_VALUES):
            r = self._put("/api/v1/metering/grouping-fields",
                          {"grouping_fields": [
                              {"key": axis, "slot": "grouping_field_1",
                               "scope": GROUPING_FIELD_SCOPE_EVENT}]})
            assert r.status_code == 422, axis
            assert "reserved" in r.json()["detail"], axis
        assert not GroupingField.objects.filter(tenant=self.tenant).exists()

    def test_every_scope_the_registry_declares_can_be_declared(self):
        scopes = sorted(GROUPING_FIELD_SCOPE_VALUES)
        r = self._put("/api/v1/metering/grouping-fields",
                      {"grouping_fields": [
                          {"key": f"at_{scope}", "slot": f"grouping_field_{n}",
                           "scope": scope}
                          for n, scope in enumerate(scopes, start=1)]})
        assert r.status_code == 200
        assert {row["scope"] for row in r.json()["grouping_fields"]} == set(scopes)

    def test_a_scope_the_registry_does_not_declare_is_422_and_stores_nothing(self):
        """The contract publishes a Grouping Field's scope as a closed `enum`
        (#575), on the declaration AND on its representation. That is a promise
        in both directions: a declaration that stored whatever it was sent
        would have the read answer a value its own `enum` refuses. So the
        refusal names the scopes there are, and nothing is written."""
        r = self._put("/api/v1/metering/grouping-fields",
                      {"grouping_fields": [
                          {"key": "region", "slot": "grouping_field_1",
                           "scope": "session"}]})
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert "'session'" in detail
        for scope in GROUPING_FIELD_SCOPE_VALUES:
            assert scope in detail
        assert not GroupingField.objects.filter(tenant=self.tenant).exists()

    def test_one_bad_scope_refuses_the_whole_declaration(self):
        """The declaration is one act: a good field beside a bad one is not
        stored either."""
        r = self._put("/api/v1/metering/grouping-fields",
                      {"grouping_fields": [
                          {"key": "model", "slot": "grouping_field_1",
                           "scope": GROUPING_FIELD_SCOPE_EVENT},
                          {"key": "region", "slot": "grouping_field_2",
                           "scope": "session"}]})
        assert r.status_code == 422
        assert not GroupingField.objects.filter(tenant=self.tenant).exists()

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
                       {"grouping_fields": [
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
