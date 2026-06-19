"""Tier-2 synchronous live-spend/balance ledger (WS1 / P2).

The SHARED, owner-keyed Redis counter that ``record_usage`` decrements
synchronously so the 200 response can express a real wallet/budget stop verdict
(P3 reads it; P2 only maintains it). Gated by ``enforcement_on(tenant)`` — when
the tenant's ``enforcement_mode`` is ``off`` every method is a cheap no-op and
behavior is byte-for-byte unchanged.

Two parallel counters, one per billing mode, both keyed on the resolved billing
OWNER (``resolve_billing_owner``) so a pooled business is one counter across all
its seats and an allocated/individual owner is its own:

  PREPAID  ``ubb:livebal:{owner}``        = micros of spendable balance.
           DECRBY on usage, INCRBY on credit. Tracks (credits − recorded usage),
           which is ``durable_balance − undebited_usage`` ≤ durable balance, so
           the live view is the CONSERVATIVE (lower) one. Reconcile MIN-merges
           toward the durable balance (only LOWERS), so a credit that the fast
           path missed cannot be re-raised by reconcile — therefore EVERY credit
           site MUST call ``credit()`` (the three mandatory hooks in P2.3). A
           missed credit fails SAFE (over-restrictive), a missed debit is
           absorbed by the MIN-merge.

  POSTPAID ``ubb:livespend:{owner}:{YYYY-MM}`` = micros of month-to-date spend.
           INCRBY on usage. Reconcile MAX-merges toward the durable
           owner-aggregated billed total (only RAISES), catching the first-use
           under-count (the counter is born at the first event, not the
           month-to-date total) within one reconcile cycle.

SEEDING (the one deliberate over-permissive window): the prepaid counter seeds
from the DURABLE wallet balance, which at first-use may still be high by the
usage that is recorded-but-not-yet-async-debited (handlers.py drains the debit
after record_usage commits). The live counter is therefore over-permissive by
at most that one outbox-drain window, bounded and reconcile-corrected, and
backstopped by the durable START-GATE (RiskService reads the real wallet for a
NEW run). This is the reworded I2 contract (a bounded window, not an absolute
bound) — chosen over an anti-join seed because the latter introduces a
concurrency race that the LOWER-only MIN-merge cannot repair.

KEY/CLIENT (D9): the ubb:* keys are RAW-client only (redis.from_url + Lua EVAL),
never touched via django's ``cache.*`` — so they are immune to django-redis's
``:1:`` version prefix. (The existing seat-keyed ``budget:*`` counter stays on
the django cache; the postpaid OWNER counter here is a SEPARATE ubb: key.)
"""
import logging

from django.conf import settings

from apps.platform.tenants.flags import enforcement_on, enforcing

logger = logging.getLogger("ubb.billing")

LEDGER_TTL_SECONDS = 62 * 24 * 3600  # current month + buffer; refreshed on every write

# --- Lua sources -----------------------------------------------------------

# Prepaid: atomic seed-if-absent (to the durable balance) then DECRBY. Two
# concurrent first-use debits both pass the same seed; the SET only fires once
# (EXISTS guard), and BOTH DECRBY — so the counter is decremented exactly once
# per event with no double seed. KEYS[1]=livebal; ARGV[1]=seed; ARGV[2]=debit;
# ARGV[3]=ttl. Returns the post-debit balance.
_SEED_AND_DECR = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
end
local v = redis.call('DECRBY', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return v
"""

# Prepaid credit (top-up / refund-reversal / manual). Applies ONLY if the key
# is seeded; an unseeded credit is dropped because first-use will seed from the
# already-credited durable balance. ARGV[1] may be negative. Returns new value
# or nil. KEYS[1]=livebal; ARGV[1]=amount; ARGV[2]=ttl.
_CREDIT_IF_PRESENT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    local v = redis.call('INCRBY', KEYS[1], ARGV[1])
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return v
end
return nil
"""

# Prepaid reconcile MIN-merge: only LOWERS toward the durable balance (never
# raises — credits are applied via _CREDIT_IF_PRESENT, so reconcile must not
# overwrite an in-flight decrement upward). Absent key -> seed to durable.
# KEYS[1]=livebal; ARGV[1]=durable_balance; ARGV[2]=ttl.
_RECONCILE_MIN = """
local cur = redis.call('GET', KEYS[1])
local target = tonumber(ARGV[1])
if cur == false then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
if target < tonumber(cur) then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return tonumber(cur)
"""

# Postpaid spend INCRBY (creates at amount on first use). KEYS[1]=livespend;
# ARGV[1]=amount; ARGV[2]=ttl. Returns the running month-to-date spend.
_SPEND_INCR = """
local v = redis.call('INCRBY', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return v
"""

# Postpaid reconcile MAX-merge: only RAISES toward the durable owner-aggregated
# month total (catches the first-use under-count). Mirror of the budget
# reconcile in budget_service. KEYS[1]=livespend; ARGV[1]=durable_total; ARGV[2]=ttl.
_RECONCILE_MAX = """
local cur = redis.call('GET', KEYS[1])
local target = tonumber(ARGV[1])
if cur == false then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
if target > tonumber(cur) then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return tonumber(cur)
"""


def _client():
    import redis
    return redis.from_url(settings.REDIS_URL)


def _livebal_key(owner_id) -> str:
    return f"ubb:livebal:{owner_id}"


def _livespend_key(owner_id, label) -> str:
    return f"ubb:livespend:{owner_id}:{label}"


def _stop_key(owner_id) -> str:
    # Customer-wide cooperative stop flag. Owner-keyed (NOT month-scoped), so a
    # pooled business stops all its seats and an allocated seat stops itself.
    return f"ubb:stop:{owner_id}"


def _month_label_bounds(now):
    """(label 'YYYY-MM', start date, end date exclusive) for now's month."""
    d = now.date()
    start = d.replace(day=1)
    end = (start.replace(year=start.year + 1, month=1, day=1) if start.month == 12
           else start.replace(month=start.month + 1, day=1))
    return f"{start.year:04d}-{start.month:02d}", start, end


def _same_month(effective_at, now) -> bool:
    if effective_at is None:
        return True
    from datetime import timezone as _tz
    eff = effective_at.astimezone(_tz.utc) if effective_at.tzinfo else effective_at
    return (eff.year, eff.month) == (now.year, now.month)


class LiveLedgerService:
    # ---- flag delegation ----
    @staticmethod
    def enabled(tenant) -> bool:
        return enforcement_on(tenant)

    @staticmethod
    def hard(tenant) -> bool:
        return enforcing(tenant)

    # ---- synchronous usage hook (called from record_usage) ----
    @staticmethod
    def record_usage_debit(owner_id, tenant, billed_cost_micros, *, effective_at=None, now=None):
        """Apply this event to the owner's live counter, synchronously, and
        return the customer-wide stop verdict.

        P3: if this event drives the counter across the threshold (prepaid
        wallet floor / postpaid budget cap) the owner-keyed stop flag is SET
        (cooperative — never rolls back this event; I3). The returned dict
        carries {mode, balance_micros|spend_micros, key, stop, stop_reason,
        stop_scope} (the stop fields reflect the flag AFTER this event, so a
        flag a sibling run set is surfaced too). Returns None when disabled /
        zero-cost / (postpaid) backdated to a prior month. NEVER raises — a
        Redis failure logs and returns None (fail-open; the durable start-gate
        remains the backstop)."""
        if not enforcement_on(tenant) or billed_cost_micros <= 0:
            return None
        try:
            if tenant.billing_mode == "postpaid":
                from django.utils import timezone
                now = now or timezone.now()
                # I9: a prior-month backdated event must not inflate THIS
                # month's live counter (mirrors handlers.py budget tail).
                if not _same_month(effective_at, now):
                    return None
                label, _, _ = _month_label_bounds(now)
                key = _livespend_key(owner_id, label)
                v = int(_client().eval(_SPEND_INCR, 1, key, int(billed_cost_micros), LEDGER_TTL_SECONDS))
                base = {"mode": "postpaid", "spend_micros": v, "key": key}
                mode = "postpaid"
            else:
                # prepaid / meter_only: mirror the async wallet drawdown branch.
                from apps.billing.queries import get_customer_balance
                key = _livebal_key(owner_id)
                seed = int(get_customer_balance(owner_id))
                v = int(_client().eval(_SEED_AND_DECR, 1, key, seed, int(billed_cost_micros), LEDGER_TTL_SECONDS))
                base = {"mode": "prepaid", "balance_micros": v, "key": key}
                mode = "prepaid"
            # Set (never clear) the cooperative stop flag on a crossing; a
            # non-crossing event must not clear a flag a sibling run set — the
            # flag lifts only on recovery (credit / reconcile).
            if LiveLedgerService._crossed(mode, v, owner_id, tenant):
                from apps.platform.runs.reasons import CUSTOMER_WIDE_STOP
                LiveLedgerService._set_stop(owner_id, CUSTOMER_WIDE_STOP)
            base.update(LiveLedgerService.read_stop(owner_id, tenant))
            return base
        except Exception:
            logger.warning("live_ledger.debit_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return None

    # ---- customer-wide stop flag (P3) ----
    @staticmethod
    def _crossed(mode, value, owner_id, tenant) -> bool:
        """True if the live counter has crossed the owner's threshold:
        prepaid balance below the wallet floor (-min_balance), or postpaid
        month-to-date spend at/over the budget cap (cap * hard_stop_pct)."""
        if mode == "postpaid":
            from apps.billing.gating.models import BudgetConfig
            cfg = (BudgetConfig.objects.filter(tenant_id=tenant.id, customer_id=owner_id).first()
                   or BudgetConfig.objects.filter(tenant_id=tenant.id, customer__isnull=True).first())
            if not cfg or cfg.cap_micros <= 0:
                return False
            return value >= cfg.cap_micros * cfg.hard_stop_pct // 100
        from apps.billing.queries import get_customer_min_balance
        return value < -get_customer_min_balance(owner_id, tenant.id)

    @staticmethod
    def _set_stop(owner_id, reason):
        _client().set(_stop_key(owner_id), reason, ex=LEDGER_TTL_SECONDS)

    @staticmethod
    def _clear_stop(owner_id):
        _client().delete(_stop_key(owner_id))

    @staticmethod
    def read_stop(owner_id, tenant) -> dict:
        """Current customer-wide stop verdict. Short-circuits to not-stopped
        when enforcement is off — BEFORE touching Redis (D17)."""
        off = {"stop": False, "stop_reason": None, "stop_scope": None}
        if not enforcement_on(tenant):
            return off
        try:
            v = _client().get(_stop_key(owner_id))
        except Exception:
            return off
        if v is None:
            return off
        reason = v.decode() if isinstance(v, bytes) else str(v)
        return {"stop": True, "stop_reason": reason, "stop_scope": "customer"}

    # ---- prepaid credit hook (top-up / refund-reversal / manual credit) ----
    @staticmethod
    def credit(owner_id, tenant, amount_micros):
        """INCRBY the prepaid live balance by amount_micros (may be negative).
        No-op for postpaid (no spendable balance) and when disabled. Best-effort
        — but note a DROPPED credit fails over-restrictive (MIN-merge cannot
        re-raise it), so this is called from EVERY credit site."""
        if not enforcement_on(tenant) or tenant.billing_mode == "postpaid" or amount_micros == 0:
            return
        try:
            v = _client().eval(_CREDIT_IF_PRESENT, 1, _livebal_key(owner_id),
                               int(amount_micros), LEDGER_TTL_SECONDS)
            # Recovery (P3): a positive credit that lifts the balance back to/
            # above the floor clears the cooperative stop flag so the customer's
            # runs may resume. (A negative credit / grant-expiry never clears.)
            if v is not None and amount_micros > 0:
                from apps.billing.queries import get_customer_min_balance
                if int(v) >= -get_customer_min_balance(owner_id, tenant.id):
                    LiveLedgerService._clear_stop(owner_id)
        except Exception:
            logger.warning("live_ledger.credit_failed",
                           extra={"data": {"owner_id": str(owner_id)}})

    # ---- reconcile (hourly beat) ----
    @staticmethod
    def reconcile_prepaid(owner_id, tenant):
        """MIN-merge the prepaid live balance toward the durable wallet balance.
        Holds lock_for_billing(owner) so a concurrent credit() cannot be erased
        by the read→merge (D8): the durable balance is read under the lock the
        credit/drawdown paths also take."""
        if not enforcement_on(tenant):
            return
        from django.db import transaction
        from apps.billing.locking import lock_for_billing
        from apps.billing.queries import get_customer_balance
        try:
            with transaction.atomic():
                lock_for_billing(owner_id)  # serialize vs credit/drawdown
                durable = int(get_customer_balance(owner_id))
                v = int(_client().eval(_RECONCILE_MIN, 1, _livebal_key(owner_id),
                                       durable, LEDGER_TTL_SECONDS))
            # Recovery backstop: clear the stop flag if drift-correction shows
            # the balance is back above the floor (e.g. a credit() clear that
            # never fired due to a transient Redis error).
            if not LiveLedgerService._crossed("prepaid", v, owner_id, tenant):
                LiveLedgerService._clear_stop(owner_id)
        except Exception:
            logger.warning("live_ledger.reconcile_prepaid_failed",
                           extra={"data": {"owner_id": str(owner_id)}})

    @staticmethod
    def reconcile_postpaid(owner_id, tenant, now=None):
        """MAX-merge the postpaid live spend toward the durable owner-aggregated
        month-to-date billed total."""
        if not enforcement_on(tenant):
            return
        from django.utils import timezone
        from apps.metering.queries import get_billing_owner_billed_total
        now = now or timezone.now()
        label, start, end = _month_label_bounds(now)
        try:
            durable = int(get_billing_owner_billed_total(tenant.id, owner_id, start, end))
            v = int(_client().eval(_RECONCILE_MAX, 1, _livespend_key(owner_id, label),
                                   durable, LEDGER_TTL_SECONDS))
            # Recovery backstop incl. MONTH ROLLOVER: the new month's livespend
            # is low, so once spend is back under the cap the stale stop flag
            # (which is NOT month-scoped) is cleared. Bounds the cross-month
            # stale-flag window to one reconcile cycle.
            if not LiveLedgerService._crossed("postpaid", v, owner_id, tenant):
                LiveLedgerService._clear_stop(owner_id)
        except Exception:
            logger.warning("live_ledger.reconcile_postpaid_failed",
                           extra={"data": {"owner_id": str(owner_id)}})

    # ---- read helpers (used by P3 / tests) ----
    @staticmethod
    def read_prepaid(owner_id):
        v = _client().get(_livebal_key(owner_id))
        return int(v) if v is not None else None

    @staticmethod
    def read_postpaid(owner_id, now=None):
        from django.utils import timezone
        label, _, _ = _month_label_bounds(now or timezone.now())
        v = _client().get(_livespend_key(owner_id, label))
        return int(v) if v is not None else None

    @staticmethod
    def cleanup_keys(tenant):
        """Delete an owner's Tier-2 keys when a tenant is disabled (D17). Wired
        in P7; not needed by P2."""
        raise NotImplementedError("LiveLedgerService.cleanup_keys is wired in P7")
