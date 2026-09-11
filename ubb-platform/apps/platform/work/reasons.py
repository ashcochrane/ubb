"""The vocabulary of why a stop fired — `reason_code` — and the mechanisms
that apply one.

The single source of truth for the `reason_code` field on the four terminal
stop events, on the ack stop-verdict fields (`stop_reason`), and on the stop
cause a unit carries in its metadata. Every producer and consumer imports
these constants; no stop path may invent a reason string.

⚠ WHAT THIS MODULE TAKES FROM THE REGISTRY, AND WHAT IT STILL SPELLS (#457).
Two registry concepts have their declared backend consumer HERE, and both are
now PAID IN FULL:

  `trigger_source`  — all five known mechanisms, in `KNOWN_TRIGGER_SOURCES`.
  `reason_code`     — all seven known values, each bound to a constant below.
                      A stop says WHICH BOUND was reached — the unit's own
                      ceiling, the customer's pool, the wallet's floor, a
                      silence window, the absolute deadline, or a parent's
                      end — so an integrator branches on a constant and never
                      parses a string (slice 6 §7).

⚠ TWO VALUES HERE ARE NOT REGISTRY VALUES, AND THAT IS THE PRODUCER/CONSUMER
RECONCILIATION THIS DOCSTRING EXISTS FOR. `task_not_active` is a VERDICT and
not a stop — a late event on a terminal unit, still priced, recorded and
billed — and `suspended` is a stop-context TAG for an owner suspended with no
open episode. Both are UBB-produced, both travel legally under the concept's
`allow_unknown`, and neither is in the registry's known values because
neither names a bound that was reached. A reader hunting for them in the
registry will not find them; this is where they are declared.

Both concepts are `open`, which is what makes an unknown value legal on the
wire rather than a defect: a stop can originate outside UBB, so a reason this
module has never heard of must still travel rather than be rejected at the
boundary (ADR-0003). "Closed" below is a rule on UBB's own PRODUCERS — no
stop path here may invent a string, and `ALL_REASONS` is the whole set they
may use. Neither set may be used to refuse a value arriving from outside.

One-rule model (docs/plans/2026-07-15-one-rule-enforcement-spec.md): these are
signal reasons, not refusal codes — every usage report answers HTTP 200; the
reason rides the response's stop fields. The retired 429-era refusal codes are
deliberately NOT reused, and the registry lists them as retired aliases.

⚠ ALTITUDE IS NOT IN THE REASON (slice 6 §7, the collapse). A unit stopped on
its own ceiling records `TASK_COGS_CEILING` whether it is a whole unit of work
or contained work; which one it was travels as `stop_scope`, derived from the
verdict's own crossing flags (`kill_plan`, `stop_fields`) or from the row's
own altitude (`unit_scope`) — never from which constant fired.

⚠ THE STORED CAUSE WAS MIGRATED ONCE, KEY AND VALUES (slice 6 §8, #457):
`work/migrations/0026` renamed the metadata key to `services.STOP_CAUSE_KEY`'s
current spelling on every row and rewrote every retired value on unit rows,
outbox payloads and the customer's suspension column. No stored row holds a
retired spelling, so no reader carries a map from one — every reader compares
by constant identity, and the two spellings no producer had emitted for a
slice (the per-task floor snapshot's, and the silence window's pre-registry
one) have left the published verdicts list with nothing to name them.
"""

from core.vocabulary import (
    CUSTOMER_BILLING_MODE_POSTPAID,
    REASON_CODE_ABSOLUTE_DEADLINE,
    REASON_CODE_CUSTOMER_SPEND_POOL,
    REASON_CODE_HARD_FLOOR,
    REASON_CODE_PARENT_EXPIRED,
    REASON_CODE_PARENT_KILLED,
    REASON_CODE_SILENCE_WINDOW,
    REASON_CODE_TASK_COGS_CEILING,
    TRIGGER_SOURCE_ENFORCEMENT_PATROL,
    TRIGGER_SOURCE_PARENT_CASCADE,
    TRIGGER_SOURCE_POOL_CROSSING,
    TRIGGER_SOURCE_STALE_REAPER,
    TRIGGER_SOURCE_USAGE_INGEST,
)

# The unit's OWN COGS ceiling was reached (`Task.task_cogs_ceiling_micros`),
# at either altitude. On a contained unit's event the parent's rolled-up
# provider total can cross the PARENT's ceiling — the parent records this
# word and is the kill target, because a parent's ceiling covers everything
# underneath it (#38) — and the contained unit's own ceiling can cross too,
# in which case it records the same word and is killed alone. Two constants
# used to carry the altitude; `stop_scope` carries it now (slice 6 §7).
TASK_COGS_CEILING = REASON_CODE_TASK_COGS_CEILING
# An event landed on a unit already in one of the five terminal states. It was
# still priced, recorded, and billed — this is a verdict, not a refusal, and
# it is deliberately NOT a registry value (see the module docstring).
TASK_NOT_ACTIVE = "task_not_active"
# Customer-wide stop: the owner's CUSTOMER SPEND POOL opened the episode. The
# postpaid lane's stop (slice 6 §4, §7 — the split of the one customer-wide
# word into the two controls that produce it).
CUSTOMER_SPEND_POOL = REASON_CODE_CUSTOMER_SPEND_POOL
# Customer-wide stop: the wallet's HARD FLOOR opened the episode. The prepaid
# lane's stop, and the same word the suspension it folds into records.
HARD_FLOOR = REASON_CODE_HARD_FLOOR
# Reaped: nothing was reported on this unit inside its silence window, and
# reporting usage is the only thing that proves a unit is alive (#412).
SILENCE_WINDOW = REASON_CODE_SILENCE_WINDOW
# Reaped: the unit passed its OWN absolute deadline, whatever it was still
# doing. The registry coined this word in slice 6 (#457); until then the
# deadline's stop travelled under this module's own spelling, and the
# migration above rewrote every stored row that carried it.
ABSOLUTE_DEADLINE = REASON_CODE_ABSOLUTE_DEADLINE
# Kill-metadata only (#38): contained work flipped by its parent's downward
# KILL cascade — it crossed nothing of its own, so this never rides an ack's
# stop_reason or a terminal event; late events on it say TASK_NOT_ACTIVE.
PARENT_KILLED = REASON_CODE_PARENT_KILLED
# Expiry-metadata only: contained work ended by its PARENT's expiry, whatever
# window the parent ran out of. The third of the three cascades to name
# itself — a close cascades `outcome_reason: parent_closed`, the CALLER's
# concept, which this module does not hold and must not; the kill cascade
# records PARENT_KILLED above; and the expiry cascade recorded the silence
# window unconditionally until slice 6 coined this, so a parent reaped on its
# deadline and its contained work disagreed in one transaction. Where each is
# declared is `services.CascadeRecord`.
PARENT_EXPIRED = REASON_CODE_PARENT_EXPIRED
# Stop-context ``limit`` tag ONLY (apps.metering.usage.services.stop_context,
# customer scope) — an owner suspended with no open episode (admin/fraud, or a
# money suspension whose episode already cleared). Deliberately NOT an episode
# reason, NOT a registry value and NOT in ALL_REASONS/CROSSING_REASONS: it
# never rides a terminal stop event or an ack's stop_reason (those are
# unit-scoped, never customer-scoped), and the retired report has nothing to
# itemize for a bare suspension.
SUSPENDED = "suspended"

#: THE SEVEN KNOWN VALUES, held whole — what a stop's cause may say when the
#: registry has a word for it. `REASON_CODE_KNOWN_VALUES` is the same set from
#: the generator's side; this spelling exists so a reader here sees which
#: constant is which.
KNOWN_REASONS = frozenset({
    TASK_COGS_CEILING,
    CUSTOMER_SPEND_POOL,
    HARD_FLOOR,
    SILENCE_WINDOW,
    ABSOLUTE_DEADLINE,
    PARENT_KILLED,
    PARENT_EXPIRED,
})

#: EVERYTHING A UBB PRODUCER MAY WRITE AS A REASON: the seven known values and
#: the one non-registry verdict an acknowledgement can carry. `SUSPENDED` is a
#: tag and not a reason, so it is not here.
ALL_REASONS = KNOWN_REASONS | {TASK_NOT_ACTIVE}

# The reasons whose verdict drives the idempotent kill flow (a fresh
# crossing); TASK_NOT_ACTIVE signals but never re-kills.
CROSSING_REASONS = frozenset({TASK_COGS_CEILING})

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
# mechanism is recorded on each stopped row instead
# (`services.TaskService._cascade`).
#
# The whole five are held here anyway, because the registry names this module as
# the concept's backend consumer and a consumer holds the vocabulary rather than
# the subset it happens to drive. That is what let the split into four events
# ADD a field to a payload rather than open a second place these words are
# spelled: all four carry the mechanism, and none of them names a value.
KNOWN_TRIGGER_SOURCES = frozenset({
    TRIGGER_SOURCE_USAGE_INGEST,
    TRIGGER_SOURCE_ENFORCEMENT_PATROL,
    TRIGGER_SOURCE_PARENT_CASCADE,
    TRIGGER_SOURCE_POOL_CROSSING,
    TRIGGER_SOURCE_STALE_REAPER,
})


def unit_scope(*, is_subtask):
    """The ``stop_scope`` a unit-scoped stop names: the unit's OWN altitude.

    This used to branch on which of two ceiling constants fired (#41's
    ``kill_scope``); the collapse (slice 6 §7) put the altitude in the scope
    field alone, so a stored stop's scope is read off the row's altitude and
    off nothing else. A parent's ceiling crossing is recorded on the PARENT's
    row, and a contained unit's own crossing on its own, so the row's altitude
    is the whole answer. Shared by the stop-context tagging and the retired
    report.
    """
    return "subtask" if is_subtask else "task"


def customer_stop_reason(billing_mode):
    """Which customer-wide stop a lane produces — the pool's or the floor's —
    told apart the way the producers are told apart: by the owner's tenant
    billing mode (slice 6 §7, the split).

    ⚠ UNTIL THE SIGNAL LEDGER CARRIES ITS OWN LINE (ticket 7 of slice 6), this
    fork is what says which control opened a customer-wide episode, and every
    producer and reader of that stop calls it rather than spelling the fork
    again. The postpaid lane is the pool's; every other mode debits a wallet
    (`LiveCounter.debit` mirrors the drawdown branch for anything that is not
    postpaid), so every other mode is the floor's. The migration that rewrote
    stored rows (`work/migrations/0026`) routed the retired word by the same
    fork, because the mode was the only fact a historical row could answer
    with.
    """
    if billing_mode == CUSTOMER_BILLING_MODE_POSTPAID:
        return CUSTOMER_SPEND_POOL
    return HARD_FLOOR


def kill_plan(unit_id, parent_id, verdicts):
    """The ordered ``[(task_id, reason), ...]`` kills an accumulate verdict
    dict demands — the single verdicts→kills map every ingest path shares
    (sync response, batch items, async settle); a new crossing verdict is
    added HERE, not at each call site.

    On a contained unit's event ``crossed_task_limit`` names the PARENT's
    crossing (rolled-up provider total), so the parent is the kill target —
    its kill cascades downward inside kill_task. When the contained unit's
    own ceiling crossed too, its kill comes FIRST: a cascade-killed unit could
    no longer win its own transition, and its own announcement must not be
    swallowed by the parent's cascade.

    Both kills record the ONE ceiling word; the flag that fired chooses the
    target, and the target's altitude is its scope.
    """
    plan = []
    if parent_id is not None:
        if verdicts.get("crossed_subtask_limit"):
            plan.append((unit_id, TASK_COGS_CEILING))
        if verdicts.get("crossed_task_limit"):
            plan.append((parent_id, TASK_COGS_CEILING))
    else:
        if verdicts.get("crossed_task_limit"):
            plan.append((unit_id, TASK_COGS_CEILING))
    return plan


def stop_fields(verdicts, *, is_subtask):
    """The scalar ``(stop_reason, stop_scope)`` pair an accumulate verdict
    dict puts on the ack, or ``(None, None)`` when nothing unit-scoped fired.

    The WIDEST tripped scope wins the scalar slot: a parent trip (scope
    ``task``) beats a simultaneous contained-unit trip — the caller must stop
    the whole tree, not just the child. (The itemized multi-limit story is the
    stop-context array, ticket #41.) The scope is read off WHICH flag fired,
    never off the reason: both trips carry the one ceiling word. For the
    unit-scoped verdict (not-active) the scope names the unit itself.
    """
    if verdicts.get("crossed_task_limit"):
        return TASK_COGS_CEILING, "task"
    if verdicts.get("crossed_subtask_limit"):
        return TASK_COGS_CEILING, "subtask"
    if verdicts.get("task_not_active"):
        return TASK_NOT_ACTIVE, unit_scope(is_subtask=is_subtask)
    return None, None
