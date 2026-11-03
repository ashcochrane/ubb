"""Tier-2 spend-control feature flag accessors (D1).

The SINGLE source of truth for whether CUSTOMER-WIDE spend enforcement is
active for a tenant. Every workstream that the switch governs reads it ONLY
through these helpers — never a second flag, never tenant.metadata.

Modes (Tenant.enforcement_mode) — two positions (#42, spec §G):
  off       -> enforcing=False  (no customer-wide enforcement)
  enforcing -> enforcing=True   (the customer-wide signal suite + its state
                                 changes)

`advisory` is retired (`tenants/0019` mapped it to `off`, before the cutover
squash, #190); the compute-but-
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
  - the start gate's money-shaped refusals: the stop flag and the soft floor
    (`gating/services/risk_service.py`);
  - the customer-scope entries of an event's stop context, and the fresh
    acknowledgement's customer-wide verdict — which its replays repeat from
    what that acknowledgement kept, never by reading the switch again
    (`usage/services/stop_context.py`, `usage_service.record_new_usage`);
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

⚠ `off` IS NOT "BYTE-FOR-BYTE PRE-ENFORCEMENT" EITHER (R10 Stage C2, ruled
2026-11-03, §7 item 25). The invariant is this: under `off`, recovery
creates none of the enforcing-only stop/control artefacts — no
`StopSignalState`, no Redis stop/control write, no `customer.stopped` /
`customer.stop_cleared`, no stop acknowledgement — but a prepaid customer the
silent level test suspended on the wallet's floor IS reactivated from the
DURABLE wallet balance (the credit hook, the hourly pass), and that real
`suspended -> active` transition emits `customer.reactivated`. Under
`enforcing`, the existing stop/control semantics and artefacts are
unchanged — the same `StopSignalState` created and cleared, the same Redis
behaviour, the same `customer.stopped` / `customer.stop_cleared` and
acknowledgement semantics, the same floor/recovery calculations — and the
ONLY additive behaviour is that same `customer.reactivated`, exactly once,
on the real transition. Before C2, `off` stranded a floor suspension for
good (BILLING BLOCKER F-1): the pins that said `off` was "byte-for-byte"
pinned the defect.

⚠ THE WALLET POLICY HAS A SUBJECT ONLY WHERE A WALLET IS (W7 preparation
finding F3, ruled 2026-10-30). `holds_a_wallet` below is the one answer to
"does this tenant's mode keep a customer wallet?", and every wallet leg —
the live debit's balance counter and hard-floor check, the drawdown, the
reconcile's wallet pass, the credit hook, the upward repair — asks it. Before
it, those legs asked "not postpaid?", which answered YES for `external`: a
tenant that bills its customers elsewhere, holds no wallet, and had an absent
wallet read as a zero balance — so under `enforcing` its first priced event
crossed a floor it does not have and suspended the customer for good. An
absent wallet is never a zero-balance wallet.
"""
from core.vocabulary import CUSTOMER_BILLING_MODE_PREPAID


def holds_a_wallet(tenant) -> bool:
    """Does the tenant's billing mode keep a customer wallet to debit, floor
    and reconcile? True for `prepaid` only: `postpaid` carries a spend counter
    with no wallet, and `external` meters only (posture `metering_only`) —
    neither has a wallet-policy subject, in any enforcement mode. What
    `enforcing` still governs for them is the customer spend pool and the
    unit ceilings, which ask no wallet."""
    return getattr(tenant, "billing_mode", None) == CUSTOMER_BILLING_MODE_PREPAID


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
