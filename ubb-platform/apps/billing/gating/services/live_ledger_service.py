"""Tier-2 synchronous live-spend/balance ledger (WS1 — SKELETON, P0).

This module is the SHARED, owner-keyed Redis counter that `record_usage` will
decrement synchronously so the 200 response can express a real wallet/budget
stop verdict (today the verdict is async and `_result` hardcodes False).

P0 ships ONLY this skeleton: the flag delegation, the key strategy, and the
Lua sources. There are NO callers yet — the operation methods raise
NotImplementedError so a premature call fails loudly. P2 fills the bodies and
wires the single synchronous decrement into UsageService.record_usage.

Design: docs/plans/2026-06-19-tier2-realtime-spend-control-{design,implementation}.md.

KEY STRATEGY (D9 — load-bearing, do not deviate in P2):
  * The NEW Tier-2 keys live on a RAW redis client (`redis.from_url`) so Lua
    EVAL is available, and they are PREFIXED `ubb:` to stay clear of
    django-redis's namespace:
        ubb:livebal:{owner_id}                 (prepaid remaining-above-floor)
        ubb:stop:{owner_id}                    (customer-wide kill flag, P3)
        ubb:runslots:{owner_id}                (concurrency in-flight count, P5)
        ubb:taskcost:{tenant}:{owner}:{task}:{YYYY-MM}  (per-task cap, P4)
    These keys are touched ONLY via the raw client — NEVER via django's
    `cache.*` API.
  * The EXISTING budget counter `budget:{customer}:{YYYY-MM}` is written by
    `BudgetService` via django's `cache.incr`. Django's RedisCache applies a
    version prefix (the `:1:` segment) and KEY_PREFIX (empty here) through
    `cache.make_key`, so the PHYSICAL key is e.g. `:1:budget:...`. Any Lua
    MAX-merge over that counter (P1/P2 postpaid) MUST go through
    `django_redis.get_redis_connection()` with the make_key-prefixed key, NOT a
    raw `redis.from_url` GET (which would silently miss the prefixed key).
"""
import logging

from django.conf import settings

from apps.platform.tenants.flags import enforcement_on, enforcing

logger = logging.getLogger("ubb.billing")

# TTL for the prepaid live-balance key: current month + buffer, refreshed on
# every seed/reconcile so an active owner's key never expires mid-month.
LIVEBAL_TTL_SECONDS = 62 * 24 * 3600

# --- Lua sources (registered in P2; defined here so the contract is fixed) ---

# Prepaid seed-and-decrement, ONE atomic round-trip so two concurrent first-use
# debits cannot both seed (D7). KEYS[1]=ubb:livebal:{owner};
# ARGV[1]=seed_value (durable balance minus recorded-but-undebited usage),
# ARGV[2]=debit, ARGV[3]=ttl_seconds. Returns the post-debit balance.
SEED_AND_DECR_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
end
return redis.call('DECRBY', KEYS[1], ARGV[2])
"""

# Prepaid credit that ONLY applies if the key is already seeded (an unseeded
# credit is dropped: first-use will seed from the post-credit durable balance,
# so no double count). KEYS[1]=ubb:livebal:{owner}; ARGV[1]=amount (may be
# negative for grant expiry). Returns the new value or nil if unseeded.
CREDIT_IF_PRESENT_LUA = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    return redis.call('INCRBY', KEYS[1], ARGV[1])
end
return nil
"""

# Prepaid reconcile MIN-merge (monotonic down toward the durable balance, I7).
# KEYS[1]=ubb:livebal:{owner}; ARGV[1]=durable_target, ARGV[2]=ttl_seconds.
# If unseeded, sets to the target; else lowers to min(current, target). Run
# under lock_for_billing(owner) so a concurrent credit cannot be erased (D8).
RECONCILE_MIN_LUA = """
local cur = redis.call('GET', KEYS[1])
if cur == false then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return tonumber(ARGV[1])
end
if tonumber(ARGV[1]) < tonumber(cur) then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return tonumber(ARGV[1])
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return tonumber(cur)
"""

_NOT_WIRED = "LiveLedgerService.{} is wired in P2 — not callable in P0"


def _client():
    """Raw redis-py client for Lua EVAL on the ubb:* Tier-2 keys (P2)."""
    import redis
    return redis.from_url(settings.REDIS_URL)


def _prepaid_key(owner_id) -> str:
    return f"ubb:livebal:{owner_id}"


class LiveLedgerService:
    # ---- flag delegation (real, harmless in P0) ----
    @staticmethod
    def enabled(tenant) -> bool:
        """advisory OR enforcing — maintain the counter + compute the verdict."""
        return enforcement_on(tenant)

    @staticmethod
    def hard(tenant) -> bool:
        """enforcing only — UBB itself may block/kill/suspend."""
        return enforcing(tenant)

    # ---- operations (bodies land in P2; loud failure if called early) ----
    @staticmethod
    def record_usage_debit(owner_id, tenant, billed_cost_micros, *,
                           effective_at=None, now=None):
        raise NotImplementedError(_NOT_WIRED.format("record_usage_debit"))

    @staticmethod
    def credit(owner_id, tenant, amount_micros):
        raise NotImplementedError(_NOT_WIRED.format("credit"))

    @staticmethod
    def seed_prepaid(owner_id, tenant):
        raise NotImplementedError(_NOT_WIRED.format("seed_prepaid"))

    @staticmethod
    def read_prepaid(owner_id):
        raise NotImplementedError(_NOT_WIRED.format("read_prepaid"))

    @staticmethod
    def reconcile_prepaid(owner_id, tenant):
        raise NotImplementedError(_NOT_WIRED.format("reconcile_prepaid"))

    @staticmethod
    def cleanup_keys(tenant):
        """Delete an owner's Tier-2 keys when a tenant is disabled (D17, P7)."""
        raise NotImplementedError(_NOT_WIRED.format("cleanup_keys"))
