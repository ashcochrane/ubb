import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue
from apps.platform.grouping_fields.services import DimensionService, DimensionError


@pytest.mark.django_db
class TestDeclare:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_declare_binds_key_to_slot(self):
        t = self._t()
        d = DimensionService.declare(t, key="region", slot="grouping_field_1", scope="task")
        assert d.key == "region" and d.slot == "grouping_field_1"

    def test_reserved_key_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="reserved"):
            DimensionService.declare(t, key="provider", slot="grouping_field_1", scope="event")

    def test_correlation_id_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="correlation"):
            DimensionService.declare(t, key="task_id", slot="grouping_field_1", scope="event")

    def test_slot_is_immutable(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="grouping_field_1", scope="task")
        with pytest.raises(DimensionError, match="slot is immutable"):
            DimensionService.declare(t, key="region", slot="grouping_field_2", scope="task")

    def test_scope_is_immutable(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="grouping_field_1", scope="task")
        with pytest.raises(DimensionError, match="scope is immutable"):
            DimensionService.declare(t, key="region", slot="grouping_field_1", scope="event")

    def test_cardinality_raises_only(self):
        t = self._t()
        DimensionService.declare(t, key="region", slot="grouping_field_1", scope="task",
                                 max_cardinality=50)
        DimensionService.declare(t, key="region", slot="grouping_field_1", scope="task",
                                 max_cardinality=80)
        with pytest.raises(DimensionError, match="lowered"):
            DimensionService.declare(t, key="region", slot="grouping_field_1", scope="task",
                                     max_cardinality=10)


@pytest.mark.django_db
class TestAdmit:
    def _t(self):
        t = Tenant.objects.create(name="T")
        DimensionService.declare(t, key="region", slot="grouping_field_1", scope="task",
                                 max_cardinality=2)
        DimensionService.declare(t, key="model", slot="grouping_field_2", scope="event")
        return t

    def test_admit_maps_keys_to_slots(self):
        t = self._t()
        assert DimensionService.admit(t, {"model": "gpt-4"}, scope="event") == {"grouping_field_2": "gpt-4"}

    def test_admit_records_the_value(self):
        t = self._t()
        DimensionService.admit(t, {"model": "gpt-4"}, scope="event")
        assert GroupingFieldValue.objects.filter(tenant=t, key="model", value="gpt-4").exists()

    def test_admit_is_idempotent_on_repeat_value(self):
        t = self._t()
        DimensionService.admit(t, {"model": "gpt-4"}, scope="event")
        DimensionService.admit(t, {"model": "gpt-4"}, scope="event")
        assert GroupingFieldValue.objects.filter(tenant=t, key="model").count() == 1

    def test_unknown_key_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="unknown grouping field"):
            DimensionService.admit(t, {"nope": "x"}, scope="event")

    def test_wrong_scope_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="scope"):
            DimensionService.admit(t, {"region": "eu"}, scope="event")

    def test_cardinality_cap_rejects_novel_value(self):
        t = self._t()
        DimensionService.admit(t, {"region": "eu"}, scope="task")
        DimensionService.admit(t, {"region": "us"}, scope="task")
        with pytest.raises(DimensionError, match="cardinality"):
            DimensionService.admit(t, {"region": "ap"}, scope="task")

    def test_cap_does_not_block_known_value(self):
        t = self._t()
        DimensionService.admit(t, {"region": "eu"}, scope="task")
        DimensionService.admit(t, {"region": "us"}, scope="task")
        assert DimensionService.admit(t, {"region": "eu"}, scope="task") == {"grouping_field_1": "eu"}

    def test_retired_def_rejects_novel_value(self):
        t = self._t()
        DimensionService.admit(t, {"model": "gpt-4"}, scope="event")
        GroupingField.objects.filter(tenant=t, key="model").update(
            retired_at="2026-07-27T00:00:00Z")
        with pytest.raises(DimensionError, match="retired"):
            DimensionService.admit(t, {"model": "gpt-5"}, scope="event")

    def test_value_over_100_chars_is_rejected(self):
        t = self._t()
        with pytest.raises(DimensionError, match="exceeds 100 characters"):
            DimensionService.admit(t, {"model": "x" * 101}, scope="event")

    def test_admit_is_atomic_on_multi_key_failure(self):
        t = self._t()
        # region is task scope, model is event scope
        # Try to admit both at event scope: region will fail, model should not be recorded
        with pytest.raises(DimensionError, match="scope"):
            DimensionService.admit(t, {"model": "gpt-4", "region": "eu"}, scope="event")
        # Verify model's value was NOT recorded due to atomicity
        assert not GroupingFieldValue.objects.filter(tenant=t, key="model", value="gpt-4").exists()
