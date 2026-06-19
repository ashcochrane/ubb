"""Tier-2 spend-control feature flag accessors (D1).

The SINGLE source of truth for whether real-time spend enforcement is active
for a tenant. Every workstream (live ledger, stop flag, per-task cap,
concurrency cap, reaper, SDK contract) reads enforcement state ONLY through
these helpers — never a second flag, never tenant.metadata.

Modes (Tenant.enforcement_mode):
  off       -> enforcement_on=False, enforcing=False  (unchanged behavior)
  advisory  -> enforcement_on=True,  enforcing=False  (compute + emit, never block)
  enforcing -> enforcement_on=True,  enforcing=True   (block/kill/suspend live)

See docs/plans/2026-06-19-tier2-realtime-spend-control-design.md (§6 D1).
"""


def enforcement_mode(tenant) -> str:
    """Return the tenant's enforcement mode, defaulting to 'off' on any
    missing/None value so a partially-constructed tenant is always safe."""
    return getattr(tenant, "enforcement_mode", "off") or "off"


def enforcement_on(tenant) -> bool:
    """True in advisory OR enforcing — i.e. counters are maintained and the
    stop verdict is computed/emitted. Gates the synchronous live-ledger writes
    and event emission."""
    return enforcement_mode(tenant) != "off"


def enforcing(tenant) -> bool:
    """True ONLY in enforcing mode. Gates the paths where UBB itself
    blocks/kills/suspends. Advisory mode must never reach these."""
    return enforcement_mode(tenant) == "enforcing"
