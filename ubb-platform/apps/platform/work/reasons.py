"""Closed vocabulary of task-stop / limit reasons, and the mechanisms that
apply one.

The single source of truth for the `reason` field on TaskLimitExceeded /
SubtaskLimitExceeded, on the ack stop-verdict fields (`stop_reason`), and on the
stop metadata a unit carries. Every producer and consumer imports these
constants; no stop path may invent a reason string.

⚠ WHAT THIS MODULE TAKES FROM THE REGISTRY, AND WHAT IT STILL SPELLS (#412).
Two registry concepts have their declared backend consumer HERE, and this module
now sources from `core.vocabulary` everything it legitimately can:

  `trigger_source`  — PAID IN FULL. All five known mechanisms are held by
                      reference below, in `KNOWN_TRIGGER_SOURCES`.
  `reason_code`     — TWO of five. `parent_killed` (#200) and `silence_window`,
                      which the silence-window expiry path produces. The other
                      three known values are the end-state names for mechanisms
                      that do not exist yet; importing them here would be this
                      module performing another slice's renames on paths it
                      cannot drive, so they are deliberately left.

Both concepts are `open`, which is what makes shipping a subset legal rather
than partial: an open set is designed for a consumer that produces some of it.

⚠ THE METADATA KEY IS STILL SPELLED `kill_reason` AND CARRIES EXPIRIES TOO
(#408). Both sweepers write `expired` rather than `killed`, and the reason they
pass — a silence window elapsed, or the absolute deadline — is stamped under the
key it always used. The key is `outcome_reason`'s to rename, in the ticket that
wires that concept's consumers; renaming it here would be a second spelling of a
value set another ticket owns. Nothing mis-reads it in the meantime: every
consumer of the key gates on `status == killed` first.

One-rule model (docs/plans/2026-07-15-one-rule-enforcement-spec.md): these are
signal reasons, not refusal codes — every usage report answers HTTP 200; the
reason rides the response's stop fields. The retired 429-era strings
(`cost_limit_exceeded`, `balance_floor_exceeded`, the label-cap
`task_limit_exceeded`) are deliberately NOT reused.

"Closed" above and the registry's `open` kind are not in conflict, and the
generated name is `REASON_CODE_KNOWN_VALUES` for exactly that reason. Closed is
a rule on UBB's own PRODUCERS: no stop path here may invent a string, and
`ALL_REASONS` is the whole set they may use. Open is a rule on CONSUMERS: a stop
can originate outside UBB, so a reason this module has never heard of must still
travel rather than be rejected at the boundary (ADR-0003). Neither set may be
used to refuse a value arriving from outside.

The rest carry names the registry retires. Swapping one here would change what
the API returns, which slice 0 did not do — each is a rename owned by a later
slice and recorded in the migration ledger (#201).
"""

from core.vocabulary import (
    REASON_CODE_PARENT_KILLED,
    REASON_CODE_SILENCE_WINDOW,
    TRIGGER_SOURCE_ENFORCEMENT_PATROL,
    TRIGGER_SOURCE_PARENT_CASCADE,
    TRIGGER_SOURCE_POOL_CROSSING,
    TRIGGER_SOURCE_STALE_REAPER,
    TRIGGER_SOURCE_USAGE_INGEST,
)

# The task's provider-cost (COGS) limit was crossed (Task.provider_cost_limit_micros).
# On a subtask event this means the PARENT's limit was crossed by the rolled-up
# provider total — a parent's cap covers everything underneath it (#38).
TASK_LIMIT = "task_limit"
# The subtask's OWN provider-cost limit was crossed; it is killed alone (#38).
SUBTASK_LIMIT = "subtask_limit"
# An event landed on a unit already in one of the five terminal states. It was
# still priced, recorded, and billed — this is a verdict, not a refusal.
TASK_NOT_ACTIVE = "task_not_active"
# Customer-wide spend stop: the owner crossed the wallet floor / budget cap.
CUSTOMER_WIDE_STOP = "customer_wide_stop"
# Reaped: nothing was reported on this unit inside its silence window, and
# reporting usage is the only thing that proves a unit is alive (#412). Held by
# reference: the registry has a word for this stop and it is that word, so the
# backend cannot keep a second spelling of it that drifts.
#
# ⚠ ITS STRING CHANGED WHEN IT BECAME REGISTRY-SOURCED, AND STORED DATA STILL
# HOLDS THE OLD ONE. Outbox rows and stop metadata written before #412 carry the
# pre-registry spelling `stale`, so the terminal-event split's row-routing rule
# — reaper reasons to `*.expired`, everything else to `*.killed` — must match
# that older value as well as this constant, or a row that predates this commit
# is routed as a spend stop. Every code consumer names the constant; the two
# places that hold the VALUE both keep the old spelling beside the new one, on
# `customer_floor`'s precedent — the published `stop_reasons` list in
# `openapi/error-codes.json` and the console's display map.
SILENCE_WINDOW = REASON_CODE_SILENCE_WINDOW
# Reaped: the unit passed its absolute deadline, whatever it was still doing.
#
# ⚠ THIS ONE KEEPS THE MODULE'S OWN VALUE, AND THAT IS NOT AN OVERSIGHT (#412).
# The registry declares no known value for the absolute deadline's stop, and
# `reason_code` is an OPEN concept with `allow_unknown` — so a value it has
# never seen travels legally rather than being refused at the boundary.
# Coining one here would be this module inventing a name the registry owns.
# Slice 6 settles whether the concept gains one.
STALE_MAX_AGE = "stale_max_age"
# Kill-metadata only (#38): a subtask flipped by its parent's downward KILL
# cascade — it crossed nothing of its own, so this never rides an ack's
# stop_reason or a limit event; late events on it say TASK_NOT_ACTIVE.
#
# ⚠ IT IS THE KILL CASCADE'S REASON AND NOT THE OTHER TWO'S (#408, #413). All
# three cascades record a reason now, and they are not the same one: a parent's
# close cascades `cancelled` recording `outcome_reason: parent_closed`, a
# CALLER-supplied concept this module does not hold and must not, and a
# parent's expiry cascades `expired` recording `SILENCE_WINDOW` above. Where
# each is declared, and the one approximation the expiry record makes, is
# `services.CascadeRecord`.
PARENT_KILLED = REASON_CODE_PARENT_KILLED
# Stop-context ``limit`` tag ONLY (apps.metering.usage.services.stop_context,
# customer scope) — an owner suspended with no open floor episode
# (admin/fraud, or a money suspension whose episode already cleared).
# Deliberately NOT an episode reason and NOT in ALL_REASONS/CROSSING_REASONS:
# it never rides a TaskLimitExceeded/SubtaskLimitExceeded event or an ack's
# stop_reason (those are task/subtask-scoped, never customer-scoped), and
# the past-limit report has nothing to itemize for a bare suspension.
SUSPENDED = "suspended"

ALL_REASONS = frozenset({
    TASK_LIMIT,
    SUBTASK_LIMIT,
    TASK_NOT_ACTIVE,
    CUSTOMER_WIDE_STOP,
    SILENCE_WINDOW,
    STALE_MAX_AGE,
    PARENT_KILLED,
})

# The reasons whose verdict drives the idempotent kill flow (a fresh
# crossing); TASK_NOT_ACTIVE signals but never re-kills.
CROSSING_REASONS = frozenset({TASK_LIMIT, SUBTASK_LIMIT})

# EVERY MECHANISM UBB HAS THAT CAN APPLY A STOP, held by reference (#412).
#
# A stop's CAUSE and the MECHANISM that applied it are two different questions,
# and both travel as structured fields so a webhook never carries either in its
# name (ADR-0006 §5). The causes are the reasons above; these are the
# mechanisms. Nothing in this module maps one to the other, because the mapping
# is not one-to-one in either direction — the same cause can be found by
# ingest or by the patrol, and the same mechanism can find several causes —
# so the producer names its own mechanism at the point it acts.
#
# ⚠ FOUR OF THE FIVE ARE PRODUCED TODAY AND ONE IS NOT, WHICH IS WHAT AN OPEN
# SET IS FOR. The terminal stop events carry the mechanism, and the three paths
# that APPLY a stop each name themselves on the event: the usage-ingest lane,
# the enforcement patrol, and the sweeper. `pool_crossing` waits on the
# mechanism that produces it. `parent_cascade` is produced too, since #413, but
# it reaches no PAYLOAD and never will while a cascade stays silent — a cascade
# announces nothing because its parent's event is the one signal, so the
# mechanism is recorded on each stopped row instead (`services._cascade`).
#
# The whole five are held here anyway, because the registry names this module as
# the concept's backend consumer and a consumer holds the vocabulary rather than
# the subset it happens to drive. That is also what makes the ticket splitting
# those two events into four an addition to a payload rather than a second place
# these words get spelled.
KNOWN_TRIGGER_SOURCES = frozenset({
    TRIGGER_SOURCE_USAGE_INGEST,
    TRIGGER_SOURCE_ENFORCEMENT_PATROL,
    TRIGGER_SOURCE_PARENT_CASCADE,
    TRIGGER_SOURCE_POOL_CROSSING,
    TRIGGER_SOURCE_STALE_REAPER,
})


def kill_scope(reason, *, is_subtask):
    """The ``stop_scope`` a limit-kill reason names (#41 stop-context and the
    past-limit report share this map): a task-limit kill is always scope
    ``task`` (the parent, on a subtask event), a subtask-limit kill always
    ``subtask``; the unit-scoped reasons (not-active) name the unit itself."""
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
    swallowed by the parent's cascade.
    """
    plan = []
    if parent_id is not None:
        if verdicts.get("crossed_subtask_limit"):
            plan.append((unit_id, SUBTASK_LIMIT))
        if verdicts.get("crossed_task_limit"):
            plan.append((parent_id, TASK_LIMIT))
    else:
        if verdicts.get("crossed_task_limit"):
            plan.append((unit_id, TASK_LIMIT))
    return plan


def stop_fields(verdicts, *, is_subtask):
    """The scalar ``(stop_reason, stop_scope)`` pair an accumulate verdict
    dict puts on the ack, or ``(None, None)`` when nothing task-scoped fired.

    The WIDEST tripped scope wins the scalar slot: a parent trip
    (``task_limit`` / scope ``task``) beats a simultaneous subtask trip —
    the caller must stop the whole tree, not just the child. (The itemized
    multi-limit story is the stop-context array, ticket #41.) For the
    unit-scoped reasons (not-active) the scope names the unit itself.
    """
    unit_scope = "subtask" if is_subtask else "task"
    if verdicts.get("crossed_task_limit"):
        return TASK_LIMIT, "task"
    if verdicts.get("crossed_subtask_limit"):
        return SUBTASK_LIMIT, "subtask"
    if verdicts.get("task_not_active"):
        return TASK_NOT_ACTIVE, unit_scope
    return None, None
