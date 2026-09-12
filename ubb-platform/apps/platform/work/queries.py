"""Read contract for tasks and task types (ADR-001).

Billing's start-gate reads task-type policy through here; the API's analytics
routes read task rollups through here; the platform's own sweepers read the
expiry ladder through here; the two spend-control reports read a ceiling's
episodes, every completed unit's utilisation and the work a customer-wide
stop swept through here (#465, slice 6 §14). Plain data only — never ORM
objects.
"""
from typing import NamedTuple

from django.db import models
from django.db.models import Avg, Count, Q, Sum
from django.db.models.aggregates import Aggregate

from core import controls
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY
from core.crossing import ceiling_assessment, ceiling_fields
from core.vocabulary import TASK_STATUS_KILLED
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import SubtaskKilled, TaskKilled
from apps.platform.work import reasons
from apps.platform.work.models import (
    STOP_CAUSE_KEY, STOP_CONTROL_FAMILY_KEY, STOP_CONTROL_ID_KEY,
    STOP_MECHANISM_KEY, TERMINAL_TASK_STATUSES, Task, TaskType)

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
    ).values("key", "pricing_mode", "task_cogs_ceiling_micros", "uncapped",
             "silence_window_seconds", "absolute_deadline_seconds",
             "required_dimensions", "retired_at").first()
    if row is None:
        return None
    return {"key": row["key"],
            # HOW THIS KIND OF WORK IS SOLD (#414). Billing's start gate reads
            # it through here to decide whether a unit of work resolves one
            # agreed price at start or prices each event as it arrives.
            "pricing_mode": row["pricing_mode"],
            # THE CEILING THIS KIND DECLARED, AND WHETHER IT DECLARED NONE
            # (#453): one answer in two keys, exactly as the row holds it. The
            # database refuses a row saying neither or both, so a reader may
            # branch on `uncapped` and trust the figure is there otherwise.
            "task_cogs_ceiling_micros":
                row["task_cogs_ceiling_micros"],
            "uncapped": row["uncapped"],
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
         "task_cogs_ceiling_micros":
             r["task_cogs_ceiling_micros"],
         "uncapped": r["uncapped"],
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
                "task_cogs_ceiling_micros", "uncapped",
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
    tenant's own default, then UBB's backstop — for the same argument the
    kind-of-work declaration makes about ceilings: one kind of work that
    legitimately behaves differently from its sibling should not force the
    tenant to loosen the rule for both. ⚠ It is NOT the COGS ceiling's ladder
    any more (#453): a declared kind must answer the ceiling question itself,
    so the tenant's ceiling default reaches undeclared work only, while the
    tenant's two window rungs here sit under every declaration
    (`RiskService.resolve_start_policy` states the ceiling's two ladders).

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
            )
            .order_by("-sum_provider_cost_micros"))

    return [{"task_type": r["task_type"],
             "run_count": r["run_count"],
             "total_provider_cost_micros": r["sum_provider_cost_micros"],
             UNRESOLVED_EVENT_COUNT_KEY: r["sum_unresolved"],
             "total_billed_cost_micros": r["sum_billed_cost_micros"],
             UNPRICED_EVENT_COUNT_KEY: r["sum_unpriced"],
             "avg_provider_cost_micros": int(r["avg_provider_cost_micros"]),
             "p95_provider_cost_micros": int(r["p95_provider_cost_micros"])}
            for r in rows]
    # ⚠ NO REACHED COUNT ON THIS ROW ANY MORE (#465, slice 6 §14, Testing
    # Decisions claim 14). The number of pieces of work whose known total reached the
    # ceiling sat here as a third comparison beside the mean and the p95; it
    # is a fact about the ceiling as a spend control rather than about the
    # economics of a kind of work, so it moved to Utilisation and headroom
    # (`ceiling_utilisation` below, aggregated per unit by the composition
    # layer) and LEFT this report in both directions — slice 7's parity
    # matrix for this endpoint starts one field short, and has been told.


# --- the two spend-control reports' reads (#465, slice 6 §14) -------------
#
# WHAT THE KERNEL ANSWERS AND WHAT IT LEAVES TO THE JOIN. A ceiling is the
# kernel's control (slice 6 §1), so the kernel says which work it stopped,
# what each read when it fired and where each ended; the itemised events that
# arrived after a stop are metering's rows and the customer-wide lines are
# billing's ledger, and the composition layer joins the three (the seam the
# retired per-customer report already sits on). Every filter here is the
# report's own — the customer a unit belongs to, the kind of work it declared,
# and the instant it stopped or completed — so a row is never fetched to be
# thrown away one layer up.

def _window(qs, column, since, until):
    if since is not None:
        qs = qs.filter(**{f"{column}__gte": since})
    if until is not None:
        qs = qs.filter(**{f"{column}__lt": until})
    return qs


def _scoped(tenant_id, *, customer_id, task_type):
    qs = Task.objects.filter(tenant_id=tenant_id)
    if customer_id is not None:
        qs = qs.filter(customer_id=customer_id)
    if task_type is not None:
        qs = qs.filter(task_type=task_type)
    return qs


def _str_or_none(value):
    return str(value) if value else None


def _crossing_pairs(tenant_id, unit_ids):
    """``{unit id: (known total, unresolved count)}`` as the kill ANNOUNCED
    them — the pair the ceiling fired on.

    The row's two counters keep moving after the kill (every late event
    lands and counts), so the row can only say where a unit ended; what the
    ceiling read when it fired is what the ORIGINAL announcement carried
    (`_stop_and_announce` reads both off the row inside the flip's own
    transaction). A patrol re-mint (`re_announcement`) carries the row as it
    stood at repair time and is never the crossing, so the first
    announcement per unit wins. A unit whose announcement has aged out of
    outbox retention has no pair here, and the caller publishes null — the
    figure is unknown, never zero.
    """
    if not unit_ids:
        return {}
    ids = [str(i) for i in unit_ids]
    rows = (OutboxEvent.objects
            .filter(tenant_id=tenant_id,
                    event_type__in=(TaskKilled.EVENT_TYPE, SubtaskKilled.EVENT_TYPE))
            .filter(Q(payload__task_id__in=ids) | Q(payload__subtask_id__in=ids))
            .exclude(payload__re_announcement=True)
            .order_by("created_at")
            .values_list("event_type", "payload"))
    pairs = {}
    for event_type, payload in rows:
        unit_id = (payload.get("subtask_id")
                   if event_type == SubtaskKilled.EVENT_TYPE
                   else payload.get("task_id"))
        if unit_id in ids and unit_id not in pairs:
            pairs[unit_id] = (payload.get("total_provider_cost_micros"),
                              payload.get("unresolved_event_count"))
    return pairs


def ceiling_episodes(tenant_id, *, customer_id=None, task_type=None,
                     since=None, until=None) -> list[dict]:
    """Every unit UBB stopped on its OWN cost ceiling, as plain data — the
    Ceiling rows of Stops and breaches (#465, slice 6 §14).

    A row is a unit in `killed` whose stored cause is the ceiling's — which,
    since #408, is the only way `killed` and that cause meet: nothing a
    tenant declares writes the state, and no sweeper writes the cause. The
    rules #153 §10.2 and §10.4 carry are satisfied by that selection alone
    rather than by a second compare (the one-place gate): an
    `indeterminate` unit is never stopped by its ceiling, so it never appears
    here; an expiry writes `expired`; contained work the cascade stopped
    carries the cascade's cause; a pool's kill carries the pool's word. The
    scope is the row's own altitude (`reasons.unit_scope`).

    Each row carries the control that fired as the flip stamped it (family,
    id, the basis derived off the cause) and the mechanism the applying lane
    recorded, the ceiling the unit pinned at start, the instant it stopped
    (`opened_at` — a kill never resumes, so there is no close), the pair the
    ceiling FIRED on (`crossed_*`, off the announcement — see
    `_crossing_pairs`, null where none survives) and the pair the unit ENDED
    on (`final_*`, off the row). The window selects on the stop instant.
    """
    qs = _window(_scoped(tenant_id, customer_id=customer_id, task_type=task_type)
                 .filter(status=TASK_STATUS_KILLED,
                         **{f"metadata__{STOP_CAUSE_KEY}__in": reasons.CROSSING_REASONS}),
                 "completed_at", since, until)
    stopped = list(qs.order_by("completed_at", "id").values(
        "id", "parent_id", "customer_id", "task_type", "metadata",
        "task_cogs_ceiling_micros", "total_provider_cost_micros",
        "unresolved_event_count", "completed_at"))
    crossed = _crossing_pairs(tenant_id, [u["id"] for u in stopped])
    rows = []
    for u in stopped:
        cause = u["metadata"].get(STOP_CAUSE_KEY)
        crossed_known, crossed_unresolved = crossed.get(str(u["id"]), (None, None))
        rows.append({
            "task_id": str(u["id"]),
            "parent_task_id": _str_or_none(u["parent_id"]),
            "customer_id": str(u["customer_id"]),
            "task_type": u["task_type"],
            "stop_scope": reasons.unit_scope(is_subtask=u["parent_id"] is not None),
            "reason_code": cause,
            "control_family": u["metadata"].get(STOP_CONTROL_FAMILY_KEY),
            "control_id": _str_or_none(u["metadata"].get(STOP_CONTROL_ID_KEY)),
            "ceiling_basis": controls.ceiling_basis(cause),
            "trigger_source": _str_or_none(u["metadata"].get(STOP_MECHANISM_KEY)),
            "task_cogs_ceiling_micros": u["task_cogs_ceiling_micros"],
            "opened_at": u["completed_at"],
            "crossed_provider_cost_micros": crossed_known,
            "crossed_unresolved_event_count": crossed_unresolved,
            "final_provider_cost_micros": u["total_provider_cost_micros"],
            "final_unresolved_event_count": u["unresolved_event_count"],
        })
    return rows


def ceiling_utilisation(tenant_id, *, customer_id=None, task_type=None,
                        since=None, until=None) -> list[dict]:
    """Every unit whose work is over, with its ceiling assessed as it stands
    at completion — the rows of Utilisation and headroom (#465, slice 6 §14).

    One row per unit in a terminal state at either altitude, selected by the
    instant it completed. The three assessment fields are the row's own
    (`Task.ceiling_assessment`, composed by the one predicate in
    `core.crossing`) rendered under the wire names every other surface uses:
    under `not_applicable` both figures are null, never zero, and under
    `indeterminate` the percentage is a floor and the headroom a ceiling —
    the status beside them is what says so. The aggregate a report builds on
    these — the average computed per unit and then across every unit (#150
    §9.3) — is the composition layer's, because it is a statement about the
    set the report shows and not about any row.
    """
    qs = _window(_scoped(tenant_id, customer_id=customer_id, task_type=task_type)
                 .filter(status__in=TERMINAL_TASK_STATUSES),
                 "completed_at", since, until)
    rows = []
    for u in qs.order_by("completed_at", "id").values(
            "id", "parent_id", "customer_id", "task_type", "completed_at",
            "task_cogs_ceiling_micros", "total_provider_cost_micros",
            "unresolved_event_count"):
        assessment = ceiling_assessment(
            ceiling_micros=u["task_cogs_ceiling_micros"],
            known_micros=u["total_provider_cost_micros"],
            unresolved_count=u["unresolved_event_count"])
        rows.append({
            "task_id": str(u["id"]),
            "parent_task_id": _str_or_none(u["parent_id"]),
            "customer_id": str(u["customer_id"]),
            "task_type": u["task_type"],
            "completed_at": u["completed_at"],
            "task_cogs_ceiling_micros": u["task_cogs_ceiling_micros"],
            "final_provider_cost_micros": u["total_provider_cost_micros"],
            "final_unresolved_event_count": u["unresolved_event_count"],
            **ceiling_fields(assessment),
        })
    return rows


def customer_wide_stops_applied(tenant_id, *, since=None, until=None) -> list[dict]:
    """Every unit a customer-wide stop swept — `killed` with the pool's word
    as its cause — so a pool episode can say how much active work it
    stopped (#465, slice 6 §14; the kill is `CustomerSpendPoolService.
    stop_active_work` through the kernel's own seam, #459).

    The wallet policy's hard floor opens the same customer-wide state and
    sweeps nothing itself (the announcement is the signal; a subscriber fans
    it out), so no unit carries its word and none is listed here. Each row
    names the seat that owned the work and its billing owner, because the
    pool's line is declared on either and the join matches on whichever the
    episode belongs to — which is why this read takes no customer filter of
    its own. The window selects on the instant the unit stopped.
    """
    qs = _window(_scoped(tenant_id, customer_id=None, task_type=None)
                 .filter(status=TASK_STATUS_KILLED,
                         **{f"metadata__{STOP_CAUSE_KEY}": reasons.CUSTOMER_SPEND_POOL}),
                 "completed_at", since, until)
    return [{
        "task_id": str(u["id"]),
        "customer_id": str(u["customer_id"]),
        "billing_owner_id": _str_or_none(u["billing_owner_id"]),
        "reason_code": u["metadata"].get(STOP_CAUSE_KEY),
        "control_id": _str_or_none(u["metadata"].get(STOP_CONTROL_ID_KEY)),
        "stopped_at": u["completed_at"],
    } for u in qs.order_by("completed_at", "id").values(
        "id", "customer_id", "billing_owner_id", "metadata", "completed_at")]
