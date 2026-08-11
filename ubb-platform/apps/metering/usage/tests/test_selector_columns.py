import pytest
from django.db import connection
from apps.metering.usage.models import Posting


@pytest.mark.django_db
class TestSelectorColumns:
    def test_ten_selector_columns_exist(self):
        names = {f.name for f in Posting._meta.get_fields()}
        for col in ("provider", "event_type", "task_type", "subtask_type",
                    "dim1", "dim2", "dim3", "dim4", "dim5", "dim6"):
            assert col in names, f"missing selector column {col}"

    def test_legacy_attribution_columns_are_gone(self):
        names = {f.name for f in Posting._meta.get_fields()}
        assert "product_id" not in names
        assert "service_id" not in names
        assert "agent_id" not in names

    def test_provider_is_indexed(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT indexdef FROM pg_indexes
                WHERE tablename = 'ubb_posting'
            """)
            defs = " ".join(row[0] for row in cur.fetchall())
        assert "provider" in defs, "provider must be indexed — it is grouped on every /analytics/usage call"

    def test_reserved_dim_keys_constant_is_gone(self):
        import apps.metering.usage.models as m
        assert not hasattr(m, "RESERVED_DIM_KEYS")
