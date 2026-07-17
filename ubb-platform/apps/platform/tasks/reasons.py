"""Closed vocabulary of task-stop / limit reasons.

The single source of truth for the `reason` field on TaskLimitExceeded /
SubtaskLimitExceeded, on the ack stop-verdict fields (`stop_reason`), and on
Task kill metadata. Every producer and consumer imports these constants; no
stop path may invent a reason string.

One-rule model (docs/plans/2026-07-15-one-rule-enforcement-spec.md): these are
signal reasons, not refusal codes — every usage report answers HTTP 200; the
reason rides the response's stop fields. The retired 429-era strings
(`cost_limit_exceeded`, `balance_floor_exceeded`, the label-cap
`task_limit_exceeded`) are deliberately NOT reused.
"""

# The task's provider-cost (COGS) limit was crossed (Task.provider_cost_limit_micros).
# On a subtask event this means the PARENT's limit was crossed by the rolled-up
# provider total — a parent's cap covers everything underneath it (#38).
TASK_LIMIT = "task_limit"
# The subtask's OWN provider-cost limit was crossed; it is killed alone (#38).
SUBTASK_LIMIT = "subtask_limit"
# The unit's wallet-floor snapshot was crossed (Task.floor_snapshot_micros).
CUSTOMER_FLOOR = "customer_floor"
# An event landed on a non-active (killed/completed/failed) unit. It was
# still priced, recorded, and billed — this is a verdict, not a refusal.
TASK_NOT_ACTIVE = "task_not_active"
# Customer-wide spend stop: the owner crossed the wallet floor / budget cap.
CUSTOMER_WIDE_STOP = "customer_wide_stop"
# Reaped: task had no heartbeat within the stale window.
STALE = "stale"
# Reaped: task exceeded the maximum wall-clock age.
STALE_MAX_AGE = "stale_max_age"
# Kill-metadata only (#38): a subtask flipped by its parent's downward
# cascade — it crossed nothing of its own, so this never rides an ack's
# stop_reason or a limit event; late events on it say TASK_NOT_ACTIVE.
PARENT_KILLED = "parent_killed"

ALL_REASONS = frozenset({
    TASK_LIMIT,
    SUBTASK_LIMIT,
    CUSTOMER_FLOOR,
    TASK_NOT_ACTIVE,
    CUSTOMER_WIDE_STOP,
    STALE,
    STALE_MAX_AGE,
    PARENT_KILLED,
})

# The reasons whose verdict drives the idempotent kill flow (a fresh
# crossing); TASK_NOT_ACTIVE signals but never re-kills.
CROSSING_REASONS = frozenset({TASK_LIMIT, SUBTASK_LIMIT, CUSTOMER_FLOOR})


def kill_scope(reason, *, is_subtask):
    """The ``stop_scope`` a limit-kill reason names (#41 stop-context and the
    past-limit report share this map): a task-limit kill is always scope
    ``task`` (the parent, on a subtask event), a subtask-limit kill always
    ``subtask``; the unit-scoped reasons (floor snapshot, not-active) name
    the unit itself."""
    if reason == TASK_LIMIT:
        return "task"
    if reason == SUBTASK_LIMIT:
        return "subtask"
    return "subtask" if is_subtask else "task"


def kill_plan(unit_id, parent_id, verdicts):
    """The ordered ``[(task_id, reason), ...]`` kills an accumulate verdict
    dict demands — the single verdicts→kills map every ingest path shares
    (sync response, batch items, async settle); a new crossing verdict is
    added HERE, not at each call site.

    On a subtask event ``crossed_task_limit`` names the PARENT's crossing
    (rolled-up provider total), so the parent is the kill target — its kill
    cascades downward inside kill_task. When the subtask's own limit crossed
    too, the subtask kill comes FIRST: a cascade-killed subtask could no
    longer win its own transition, and its own announcement must not be
    swallowed by the parent's cascade. Priority within one unit: the unit's
    limit before its floor snapshot (matching the pre-#38 order).
    """
    plan = []
    if parent_id is not None:
        if verdicts.get("crossed_subtask_limit"):
            plan.append((unit_id, SUBTASK_LIMIT))
        elif verdicts.get("crossed_floor_snapshot"):
            plan.append((unit_id, CUSTOMER_FLOOR))
        if verdicts.get("crossed_task_limit"):
            plan.append((parent_id, TASK_LIMIT))
    else:
        if verdicts.get("crossed_task_limit"):
            plan.append((unit_id, TASK_LIMIT))
        elif verdicts.get("crossed_floor_snapshot"):
            plan.append((unit_id, CUSTOMER_FLOOR))
    return plan


def stop_fields(verdicts, *, is_subtask):
    """The scalar ``(stop_reason, stop_scope)`` pair an accumulate verdict
    dict puts on the ack, or ``(None, None)`` when nothing task-scoped fired.

    The WIDEST tripped scope wins the scalar slot: a parent trip
    (``task_limit`` / scope ``task``) beats a simultaneous subtask trip —
    the caller must stop the whole tree, not just the child. (The itemized
    multi-limit story is the stop-context array, ticket #41.) For the
    unit-scoped reasons (floor, not-active) the scope names the unit itself.
    """
    unit_scope = "subtask" if is_subtask else "task"
    if verdicts.get("crossed_task_limit"):
        return TASK_LIMIT, "task"
    if verdicts.get("crossed_subtask_limit"):
        return SUBTASK_LIMIT, "subtask"
    if verdicts.get("crossed_floor_snapshot"):
        return CUSTOMER_FLOOR, unit_scope
    if verdicts.get("task_not_active"):
        return TASK_NOT_ACTIVE, unit_scope
    return None, None
