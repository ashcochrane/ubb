"""Read contract for the dimension registry (ADR-001).

Products (metering pricing/analytics, billing start-gate) call these instead of
importing the ORM models, so the registry can be reshaped without touching
product code. Returns plain data only — never ORM objects.
"""
from apps.platform.grouping_fields.models import GroupingField


def slot_map(tenant_id) -> dict:
    """{declared key: slot} for a tenant, retired defs included.

    Retired defs stay in the map so historical rows remain groupable (D8) —
    retirement blocks new VALUES, not reads.
    """
    return dict(GroupingField.objects.filter(tenant_id=tenant_id)
                .values_list("key", "slot"))


def declared_dimensions(tenant_id) -> list[dict]:
    """Full registry as plain dicts, ordered by slot."""
    return [
        {"key": d["key"], "slot": d["slot"], "scope": d["scope"],
         "max_cardinality": d["max_cardinality"],
         "retired": d["retired_at"] is not None}
        for d in GroupingField.objects.filter(tenant_id=tenant_id)
        .order_by("slot")
        .values("key", "slot", "scope", "max_cardinality", "retired_at")
    ]
