"""Read contract for tasks and task types (ADR-001).

Billing's start-gate reads task-type policy through here; the API's analytics
routes read task rollups through here. Plain data only — never ORM objects.
"""
from apps.platform.tasks.models import Task, TaskType


def task_type_policy(tenant_id, key, kind) -> dict | None:
    """One task type's policy, or None when the key is not declared."""
    row = TaskType.objects.filter(
        tenant_id=tenant_id, key=key, kind=kind
    ).values("key", "default_provider_cost_limit_micros", "required_dimensions",
             "retired_at").first()
    if row is None:
        return None
    return {"key": row["key"],
            "default_provider_cost_limit_micros":
                row["default_provider_cost_limit_micros"],
            "required_dimensions": row["required_dimensions"] or [],
            "retired": row["retired_at"] is not None}


def declared_task_types(tenant_id) -> list[dict]:
    """The tenant's whole work vocabulary, ordered by kind then key."""
    return [
        {"key": r["key"], "kind": r["kind"],
         "default_provider_cost_limit_micros":
             r["default_provider_cost_limit_micros"],
         "required_dimensions": r["required_dimensions"] or [],
         "retired": r["retired_at"] is not None}
        for r in TaskType.objects.filter(tenant_id=tenant_id)
        .order_by("kind", "key")
        .values("key", "kind", "default_provider_cost_limit_micros",
                "required_dimensions", "retired_at")
    ]
