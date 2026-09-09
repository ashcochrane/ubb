"""Tier-2 spend-control feature flag accessors (D1).

The SINGLE source of truth for whether CUSTOMER-WIDE spend enforcement is
active for a tenant. Every workstream that the switch governs reads it ONLY
through these helpers — never a second flag, never tenant.metadata.

Modes (Tenant.enforcement_mode) — two positions (#42, spec §G):
  off       -> enforcing=False  (no customer-wide enforcement)
  enforcing -> enforcing=True   (the customer-wide signal suite + its state
                                 changes)

`advisory` is retired (migration 0019 mapped it to `off`); the compute-but-
never-act middle state no longer exists, so the two historical predicates
(`enforcement_on` / `enforcing`) collapsed into the one below.

⚠ `off` MEANS "NO CUSTOMER-WIDE ENFORCEMENT", NEVER "NOTHING HAPPENS" (slice
6 §10). This module used to say every spend control is a no-op under `off`,
and that was false the day it was written: a unit of work's COGS ceiling
has always stopped the unit on the recording lane whatever the switch says,
because the ceiling is declared on the work and declaring it is the opt-in
(#150 §11.2). What the switch governs, and what it does not, as the tree
stands at #452:

GOVERNED by `enforcing` — the customer-wide family, all of it:
  - the live counters: the recording-path debit and its crossing check, the
    reconcile's seed and merge, the upward repair
    (`gating/services/live_counter.py`, `gating/repair.py`);
  - the wallet hard floor's signal on the durable drawdown lane, the signal
    ledger and its re-mint, the customer-wide stop flag and the suspension
    fold (`wallets/operations.py`, `gating/services/stop_signal_service.py`,
    `gating/patrol.py` leg 2);
  - the start gate's money-shaped refusals: the stop flag, the soft floor and
    the concurrency cap (`gating/services/risk_service.py`);
  - the customer-scope entries of an event's stop context, and the replayed
    acknowledgement's customer-wide verdict
    (`usage/services/stop_context.py`, `usage_service._replay_stop`);
  - the ANNOUNCING expiry sweeper (`work/tasks.py::reap_stale_tasks`): under
    `off` a unit past its silence window or absolute deadline is still
    expired, by `close_abandoned_tasks`, but silently.

NOT governed — always on where declared:
  - the COGS ceiling at both altitudes: the recording lane's compare and
    kill, the stop verdict on the acknowledgement, the unit-scope stop
    context (`work/services.py`, `usage/services/usage_service.py`);
  - its hourly repair — the patrol's sweep of work sitting at or past its
    ceiling and the re-mint of a stopped unit's dead-lettered announcement
    (`gating/patrol.py` leg 3), universal since #452;
  - the silence window and the absolute deadline as WINDOWS: both ladders
    are climbed for every tenant (`work/queries.py::expiry_windows`), and
    only the announcement of the resulting expiry is the switch's.

See docs/plans/2026-07-15-one-rule-enforcement-spec.md §G.
"""


def enforcement_mode(tenant) -> str:
    """Return the tenant's enforcement mode, defaulting to 'off' on any
    missing/None value so a partially-constructed tenant is always safe."""
    return getattr(tenant, "enforcement_mode", "off") or "off"


def enforcing(tenant) -> bool:
    """The one honest question: is the CUSTOMER-WIDE signal suite on? True
    ONLY in enforcing mode — the counters, the signal ledger, the customer
    scope of stop-context tagging, and the customer-wide state changes
    (start-gate refusals, the soft-floor gate, suspension, the announcing
    expiry sweeper) all hang off this single answer. The module docstring
    lists what does NOT: a unit's ceiling and its repair run under `off`
    too."""
    return enforcement_mode(tenant) == "enforcing"


def live_counter_maintenance_on(tenant) -> bool:
    """Is real-time counter maintenance on (#46, delivery spec §E; NARROWED by
    #149 §6.5)? True only when the tenant is enforcing AND has not opted out —
    the flag is a behavior posture within enforcing, meaningless outside it.

    Governs the recording-path live debit + crossing check
    (LiveCounter.debit), the reconcile's counter jobs (seed/MIN-merge) and the
    upward repair. It selects WHEN the counters are maintained, never which
    route an event takes in. The durable lane — the drawdown handler's
    detection, the signal ledger, the patrol, webhook delivery, ack
    verdicts read from the durable-maintained stop flag — hangs off
    ``enforcing`` and NEVER reads this. Defaults True on a
    partially-constructed tenant (the field's own default; posture, not
    access)."""
    return enforcing(tenant) and getattr(
        tenant, "live_counter_maintenance_enabled", True)
