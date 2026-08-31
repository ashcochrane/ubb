"""Read contract for tasks and task types (ADR-001).

Billing's start-gate reads task-type policy through here; the API's analytics
routes read task rollups through here; the platform's own sweepers read the
expiry ladder through here. Plain data only — never ORM objects.
"""
from typing import NamedTuple

from django.db import models
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.aggregates import Aggregate

from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY
from apps.platform.work.models import Task, TaskType

#: WHAT A UNIT GETS WHEN NOBODY DECLARED ANYTHING, at either window (#412).
#:
#: The bottom rung of both ladders, and it is UBB's number rather than a
#: tenant's: fifteen minutes of silence is the window every enforcing tenant
#: already ran under before the window became declarable, and six hours is the
#: ceiling both sweepers already applied. Nothing about the numbers is new
#: here; what is new is that they are now the LAST answer rather than the only
#: one, and that they are named where the ladder bottoms out instead of being
#: spelled as durations at each sweeper.
SILENCE_WINDOW_BACKSTOP_SECONDS = 15 * 60
ABSOLUTE_DEADLINE_BACKSTOP_SECONDS = 6 * 60 * 60


def task_type_policy(tenant_id, key, kind) -> dict | None:
    """One task type's policy, or None when the key is not declared."""
    row = TaskType.objects.filter(
        tenant_id=tenant_id, key=key, kind=kind
    ).values("key", "pricing_mode", "default_provider_cost_limit_micros",
             "silence_window_seconds", "absolute_deadline_seconds",
             "required_dimensions", "retired_at").first()
    if row is None:
        return None
    return {"key": row["key"],
            # HOW THIS KIND OF WORK IS SOLD (#414). Billing's start gate reads
            # it through here to decide whether a unit of work resolves one
            # agreed price at start or prices each event as it arrives.
            "pricing_mode": row["pricing_mode"],
            "default_provider_cost_limit_micros":
                row["default_provider_cost_limit_micros"],
            "silence_window_seconds": row["silence_window_seconds"],
            "absolute_deadline_seconds": row["absolute_deadline_seconds"],
            "required_dimensions": row["required_dimensions"] or [],
            # WHETHER, AND NOT WHEN. A start gate asks only whether this kind of
            # work may still be started; the instant is a fact for a reader
            # reconciling what changed, and it is carried by the registry read
            # below, which is the one a person looks at.
            "retired": row["retired_at"] is not None}


def declared_task_types(tenant_id) -> list[dict]:
    """The tenant's whole work vocabulary, ordered by kind then key."""
    return [
        {"key": r["key"], "kind": r["kind"],
         "pricing_mode": r["pricing_mode"],
         "default_provider_cost_limit_micros":
             r["default_provider_cost_limit_micros"],
         "silence_window_seconds": r["silence_window_seconds"],
         "absolute_deadline_seconds": r["absolute_deadline_seconds"],
         "required_dimensions": r["required_dimensions"] or [],
         # BOTH, AND THEY ARE ONE COLUMN READ TWICE. `retired` is the predicate
         # a caller branches on; `retired_at` is WHEN, which a boolean throws
         # away — and when is what the frozen regime leans on, because
         # retire-plus-redeclare is only a record of a change if the instants
         # are readable. Derived from one value in one pass, so the two cannot
         # disagree; rendered here rather than by a serializer beside the Out
         # schema because this function IS this surface's row serializer.
         "retired": r["retired_at"] is not None,
         "retired_at": (r["retired_at"].isoformat()
                        if r["retired_at"] else None)}
        for r in TaskType.objects.filter(tenant_id=tenant_id)
        .order_by("kind", "key")
        .values("key", "kind", "pricing_mode",
                "default_provider_cost_limit_micros",
                "silence_window_seconds", "absolute_deadline_seconds",
                "required_dimensions", "retired_at")
    ]


#: The key an expiry policy is resolved for: the altitude a unit sits at and
#: the kind of work it declared. Both halves are needed and neither alone will
#: do — a TaskType's uniqueness is `(tenant, kind, key)`, so one word may name a
#: kind of work at either altitude and the two are different declarations with
#: different policy (#407). ``None`` is the fallback entry: every unit whose
#: declaration this tenant does not have, which includes the untyped ones.
EXPIRY_LADDER_FALLBACK = None


class ExpiryWindows(NamedTuple):
    """The two resolved bounds on one kind of work, as a pair with names.

    A NamedTuple rather than a bare pair because the two halves are not
    interchangeable and `[0]` / `[1]` at four call sites said nothing about
    which was which — and rather than a dict or a dataclass because this is
    still a tuple, which keeps it the plain data this module is only allowed
    to return.

    ``silence`` is ``None`` where the resolved answer is that there is no
    silence window. ``absolute`` is NEVER ``None``: the absolute ceiling
    cannot be switched off at any rung and both models refuse a zero, so a
    reader may rely on it being a number and does not have to handle an
    absence that cannot arise.
    """
    silence: int | None
    absolute: int


def expiry_windows(tenant_id) -> dict:
    """How long each of this tenant's kinds of work may go quiet, and how long
    it may run at all — every rung already resolved.

    ``{(kind, key): ExpiryWindows, ...}`` plus one entry under
    :data:`EXPIRY_LADDER_FALLBACK` for everything this tenant has not declared.
    See :class:`ExpiryWindows` for what each half may hold.

    THE LADDER, PER WINDOW, IN THIS ORDER: the declared kind of work, then the
    tenant's own default, then UBB's backstop. It is the ladder the COGS
    ceiling already climbs (`RiskService.resolve_start_policy`), and for the
    same argument the kind-of-work declaration makes about ceilings: one kind
    of job that legitimately behaves differently from its sibling should not
    force the tenant to loosen the rule for both.

    ⚠ RESOLVED WHEN A SWEEPER RUNS, NOT PINNED AT REGISTRATION, and that is a
    decision rather than an accident. The COGS ceiling is snapshotted onto the
    unit at creation so a configuration change cannot move a bound the unit is
    already racing; these two are read fresh precisely so a change CAN reach
    work already in flight, which is what makes widening a window the way an
    operator rescues a whole fleet of work about to be reaped for a silence its
    own workload explains. Neither number is an economic fact anything is
    charged against, so nothing depends on it being pinned.
    """
    from apps.platform.tenants.models import Tenant

    tenant = Tenant.objects.filter(id=tenant_id).values(
        "task_stale_seconds", "task_absolute_deadline_seconds").first()
    if tenant is None:
        tenant = {"task_stale_seconds": None,
                  "task_absolute_deadline_seconds": None}

    fallback = ExpiryWindows(
        silence=_rung(tenant["task_stale_seconds"],
                      SILENCE_WINDOW_BACKSTOP_SECONDS),
        absolute=_rung(tenant["task_absolute_deadline_seconds"],
                       ABSOLUTE_DEADLINE_BACKSTOP_SECONDS))
    windows = {EXPIRY_LADDER_FALLBACK: fallback}
    for row in TaskType.objects.filter(tenant_id=tenant_id).values(
            "kind", "key", "silence_window_seconds",
            "absolute_deadline_seconds"):
        windows[(row["kind"], row["key"])] = ExpiryWindows(
            silence=_rung(row["silence_window_seconds"], fallback.silence),
            absolute=_rung(row["absolute_deadline_seconds"], fallback.absolute),
        )
    return windows


def _rung(declared, beneath):
    """One step of a ladder: what this rung says, or what is under it.

    ``None`` means *nothing was declared here*, and it is the ONLY thing that
    falls through. **Zero does not**: at the silence window zero is a rung
    declaring that it wants no window, which has been that column's documented
    meaning since it was added, and reading it as a fall-through would silently
    re-arm a sweeper somebody switched off. The absolute deadline has no zero
    to read — both models refuse one — so the rule is stated once and holds for
    both ladders.

    Written as three branches rather than as `declared or beneath`, because
    that expression maps zero to the rung beneath and this one must not: the
    difference between the two is the whole of the paragraph above.
    """
    if declared is None:
        return beneath
    if declared == 0:
        return None
    return declared


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
