"""Tier-2 spend-control feature flag accessors (D1).

The SINGLE source of truth for whether real-time spend enforcement is active
for a tenant. Every workstream (live ledger, stop flag, per-task cap,
concurrency cap, reaper, SDK contract) reads enforcement state ONLY through
these helpers — never a second flag, never tenant.metadata.

Modes (Tenant.enforcement_mode) — two positions (#42, spec §G):
  off       -> enforcing=False  (byte-for-byte pre-enforcement behavior)
  enforcing -> enforcing=True   (the full signal suite + state changes)

`advisory` is retired (migration 0019 mapped it to `off`); the compute-but-
never-act middle state no longer exists, so the two historical predicates
(`enforcement_on` / `enforcing`) collapsed into the one below.

See docs/plans/2026-07-15-one-rule-enforcement-spec.md §G.
"""


def enforcement_mode(tenant) -> str:
    """Return the tenant's enforcement mode, defaulting to 'off' on any
    missing/None value so a partially-constructed tenant is always safe."""
    return getattr(tenant, "enforcement_mode", "off") or "off"


def enforcing(tenant) -> bool:
    """The one honest question: is the signal suite on? True ONLY in
    enforcing mode — counters, signals, stop-context tagging, and state
    changes (task flips, start-gate refusals, soft-floor gate, suspension,
    reapers) all hang off this single answer. In off, every one of them is
    a no-op."""
    return enforcement_mode(tenant) == "enforcing"
