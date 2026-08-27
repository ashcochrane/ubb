"""Read contract for tasks and task types (ADR-001).

Billing's start-gate reads task-type policy through here; the API's analytics
routes read task rollups through here. Plain data only — never ORM objects.
"""
from django.db import models
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.aggregates import Aggregate

from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY
from apps.platform.work.models import Task, TaskType


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


class PercentileCont(Aggregate):
    """p95 over a grouped column. Postgres-only, which matches the project —
    DATABASE_URL is Postgres and GinIndex is already in use at
    apps/metering/usage/models.py:83."""
    function = "PERCENTILE_CONT"
    name = "PercentileCont"
    template = "%(function)s(0.95) WITHIN GROUP (ORDER BY %(expressions)s)"
    output_field = models.BigIntegerField()


def task_rollup_by_type(tenant_id, *, start_date=None, end_date=None,
                        group_by="task_type") -> list[dict]:
    """Unit economics per KIND of job — the number that sets a price.

    Aggregates ubb_task rows, never ubb_posting: per-unit costs are already
    materialized by the accumulate primitive, with subtask spend rolled into its
    parent.

    ⚠ ONE ALTITUDE PER ANSWER, AND WHICH ONE IS ALL THE ARGUMENT DECIDES. The
    default asks about work with no parent, so `run_count` counts each whole
    unit of work and never what is contained in one — a contained unit's spend
    is already inside its parent's totals, and counting both would count it
    twice. The other altitude answers about contained work alone, same terms.

    Each row carries its OWN ``unresolved_event_count`` (#328): the number of
    events this KIND of work could not cost, summed over every unit in the
    group. Non-zero makes every figure in the row a floor — the total, the mean
    and the p95 alike, since each unit contributing to them is one. One kind of
    job being incompletely costed says nothing about another's, which is why the
    count is per row rather than one number for the answer.

    ⚠ The columns summed here are the UNIT's materialized totals, which are NOT
    NULL — so a grouped `Sum` over them can never answer `None` (a group exists
    in the result only because a row produced it) and the coalesces that used to
    decorate this block have gone rather than been left reading as though they
    guarded something. The nullable column is the POSTING's, one layer down, and
    the accumulate primitive is where its absence is turned into the count.

    ⚠ ``group_by`` NAMES AN ALTITUDE, NOT A COLUMN (#407). A unit of work
    declares its kind in ONE column at either altitude, so both answers group
    on that column and the parent link — the only thing that says which
    altitude a row is at — is what the argument selects on. The two accepted
    values stay the reserved attribution axes a posting carries, which is what
    a caller is asking about and what the analytics surface beside this one
    groups by.
    """
    if group_by not in ("task_type", "subtask_type"):
        raise ValueError("group_by must be task_type or subtask_type")

    qs = Task.objects.filter(tenant_id=tenant_id)
    qs = qs.filter(parent__isnull=True) if group_by == "task_type" \
        else qs.filter(parent__isnull=False)
    if start_date:
        qs = qs.filter(created_at__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__lt=end_date)

    # Annotation aliases deliberately differ from the source column names:
    # aliasing an annotation to the same name as the field it sums breaks the
    # OTHER aggregates in this same .annotate() call that reference that field
    # by name (e.g. Avg("total_provider_cost_micros")) — Django resolves the
    # string against the just-added Sum annotation instead of the raw column,
    # which is an aggregate-of-aggregate and Postgres rejects it.
    rows = (qs.exclude(task_type="")
            .values("task_type")
            .annotate(
                run_count=Count("id"),
                sum_provider_cost_micros=Sum("total_provider_cost_micros"),
                sum_billed_cost_micros=Sum("total_billed_cost_micros"),
                sum_unresolved=Sum("unresolved_event_count"),
                sum_unpriced=Sum("unpriced_event_count"),
                avg_provider_cost_micros=Avg("total_provider_cost_micros"),
                p95_provider_cost_micros=PercentileCont("total_provider_cost_micros"),
                limit_hit_count=Count("id", filter=Q(
                    provider_cost_limit_micros__isnull=False,
                    total_provider_cost_micros__gte=F("provider_cost_limit_micros"))),
            )
            .order_by("-sum_provider_cost_micros"))

    return [{"task_type": r["task_type"],
             "run_count": r["run_count"],
             "total_provider_cost_micros": r["sum_provider_cost_micros"],
             UNRESOLVED_EVENT_COUNT_KEY: r["sum_unresolved"],
             "total_billed_cost_micros": r["sum_billed_cost_micros"],
             UNPRICED_EVENT_COUNT_KEY: r["sum_unpriced"],
             "avg_provider_cost_micros": int(r["avg_provider_cost_micros"]),
             "p95_provider_cost_micros": int(r["p95_provider_cost_micros"]),
             "limit_hit_count": r["limit_hit_count"]}
            for r in rows]
