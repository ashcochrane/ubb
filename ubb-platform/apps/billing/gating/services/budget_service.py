import logging

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.billing.gating.crossing import (budget_stop_threshold,
                                          month_label_bounds, past_budget_stop)
from apps.metering.queries import get_customer_cost_totals

logger = logging.getLogger("ubb.billing")

_TTL_SECONDS = 62 * 24 * 3600  # current month + buffer for late reconciliation

# P1 (D8/I7): monotonic MAX-merge for the in-month budget counter. The OLD
# reconcile did an absolute cache.set(durable_total), which mid-burst could
# SET the counter BACKWARD below an in-flight cache.incr (record_usage_spend)
# that the durable ledger had not yet recorded — a lost update that
# transiently re-allowed over-cap spend. This script reads + sets max(current,
# durable) in ONE atomic Redis round-trip, so a concurrent INCR is never
# erased: an INCR before the GET is included; one after the SET only raises
# (MAX never lowers). Within a month real spend only rises, and the durable
# ledger is the truth, so raising-toward-durable is the correct discipline;
# the only legitimate decrease is at month rollover, where the key LABEL
# (budget:{cid}:{YYYY-MM}) changes and this script seeds the fresh key.
#
# NOTE on locking: unlike the prepaid live-balance reconcile, this does NOT
# take lock_for_billing(owner). The concurrent writer here is
# BudgetService.record_usage_spend, which runs OUTSIDE that lock (handlers.py
# "Shared tail", ~:102-129) and is keyed on the SEAT, so the lock would not
# serialize it. The atomic MAX-merge is what makes this race-free.
#
# KEYS[1]=physical (make_key-prefixed) budget key; ARGV[1]=durable_total;
# ARGV[2]=ttl_seconds. Returns the resulting counter value.
_RECONCILE_MAX_LUA = """
local cur = redis.call('GET', KEYS[1])
local target = tonumber(ARGV[1])
if cur == false then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
local curn = tonumber(cur)
if target > curn then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return curn
"""


def _raw_redis():
    """Raw redis-py client for the MAX-merge Lua. Django's built-in RedisCache
    stores int values UNPICKLED (RedisSerializer.dumps returns ints as-is) and
    loads() does int(data) first, so a value written by this raw client at the
    make_key-prefixed key round-trips correctly through cache.get/cache.incr.
    Reads settings.REDIS_URL at call time (the test conftest points both the
    Django cache and this at the same isolated DB)."""
    import redis
    return redis.from_url(settings.REDIS_URL)


def _period():
    """(label 'YYYY-MM', period_start date, period_end date exclusive) for the
    current calendar month — the crossing module's month math (#110)."""
    return month_label_bounds(timezone.now())


def _key(customer_id, label):
    return f"budget:{customer_id}:{label}"


class BudgetService:
    @staticmethod
    def resolve_config_for(tenant_id, customer_id):
        """THE BudgetConfig resolution — customer-specific row first, tenant
        default second. Every lane that needs a budget line resolves through
        here (#110 retired ``LiveLedgerService._threshold``'s inline copy)."""
        from apps.billing.gating.models import BudgetConfig
        cfg = BudgetConfig.objects.filter(tenant_id=tenant_id, customer_id=customer_id).first()
        if cfg:
            return cfg
        return BudgetConfig.objects.filter(tenant_id=tenant_id, customer__isnull=True).first()

    @staticmethod
    def resolve_config(customer):
        return BudgetService.resolve_config_for(customer.tenant_id, customer.id)

    @staticmethod
    def current_spend(tenant_id, customer_id):
        label, start, end = _period()
        key = _key(customer_id, label)
        val = cache.get(key)
        if val is not None:
            return int(val)
        total = get_customer_cost_totals(tenant_id, customer_id, start, end)["billed_cost_micros"]
        try:
            cache.set(key, total, timeout=_TTL_SECONDS)
        except Exception:
            pass  # Redis write failure — still return the authoritative Postgres total
        return total

    @staticmethod
    def record_spend(tenant_id, customer_id, amount_micros):
        """INCRBY the period counter. Returns (old, new, label). Rebuilds from Postgres on a missing key."""
        label, start, end = _period()
        key = _key(customer_id, label)
        try:
            new = cache.incr(key, amount_micros)
            return new - amount_micros, new, label
        except ValueError:
            # Missing key. In the production drawdown path this runs AFTER the
            # UsageEvent is committed, so the durable total already INCLUDES this
            # event — rebuild to that total (do NOT add amount again, or we double-count).
            new = get_customer_cost_totals(tenant_id, customer_id, start, end)["billed_cost_micros"]
            cache.set(key, new, timeout=_TTL_SECONDS)
            return max(0, new - amount_micros), new, label

    @staticmethod
    def check(customer):
        cfg = BudgetService.resolve_config(customer)
        if cfg is None or cfg.cap_micros <= 0:
            return {"allowed": True, "reason": None, "spend_micros": None, "cap_micros": None}
        try:
            spend = BudgetService.current_spend(customer.tenant_id, customer.id)
        except Exception:
            from apps.billing.gating.models import RiskConfig
            fail_closed = cfg.fail_closed
            if not fail_closed:
                rc = RiskConfig.objects.filter(tenant_id=customer.tenant_id).first()
                fail_closed = bool(rc and rc.gate_fail_closed)
            if fail_closed:
                return {"allowed": False, "reason": "budget_unavailable",
                        "spend_micros": None, "cap_micros": cfg.cap_micros}
            return {"allowed": True, "reason": None, "spend_micros": None, "cap_micros": cfg.cap_micros}
        # The crossing module owns the stop line + enforce_mode semantics
        # (#110): advisory -> None -> never past.
        if past_budget_stop(spend, budget_stop_threshold(cfg)):
            return {"allowed": False, "reason": "budget_exceeded",
                    "spend_micros": spend, "cap_micros": cfg.cap_micros}
        return {"allowed": True, "reason": None, "spend_micros": spend, "cap_micros": cfg.cap_micros}

    @staticmethod
    def emit_threshold_alerts(customer, cfg, old, new, label):
        if cfg is None or cfg.cap_micros <= 0:
            return
        from django.db import transaction
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import BudgetThresholdReached
        for level in cfg.alert_levels:
            threshold = cfg.cap_micros * level // 100
            if old < threshold <= new:
                already = OutboxEvent.objects.filter(
                    event_type="budget.threshold_reached", tenant_id=customer.tenant_id,
                    payload__customer_id=str(customer.id), payload__period=label,
                    payload__level=level).exists()
                if already:
                    continue
                with transaction.atomic():
                    write_event(BudgetThresholdReached(
                        tenant_id=str(customer.tenant_id), customer_id=str(customer.id),
                        period=label, level=level, spend_micros=new, cap_micros=cfg.cap_micros,
                        enforce_mode=cfg.enforce_mode))

    @staticmethod
    def reconcile_customer(customer):
        cfg = BudgetService.resolve_config(customer)
        if cfg is None or cfg.cap_micros <= 0:
            return
        label, start, end = _period()
        total = int(get_customer_cost_totals(
            customer.tenant_id, customer.id, start, end)["billed_cost_micros"] or 0)
        try:
            # P1 (D8/I7): monotonic MAX-merge on the SAME physical key the
            # Django cache uses (make_key applies the version/prefix). Never
            # lowers an in-month counter, so a concurrent record_usage_spend
            # INCR can no longer be lost.
            pkey = cache.make_key(_key(customer.id, label))
            _raw_redis().eval(_RECONCILE_MAX_LUA, 1, pkey, total, _TTL_SECONDS)
        except Exception:
            logger.warning("budget.reconcile_failed",
                           extra={"data": {"customer_id": str(customer.id)}})
            return
        BudgetService.emit_threshold_alerts(customer, cfg, 0, total, label)  # fires only not-yet-sent levels

    @staticmethod
    def record_usage_spend(customer, amount_micros):
        """Post-drawdown hook: increment the counter + emit threshold alerts. Fully fail-open.

        Runs after the wallet is already charged, so it must NEVER raise into the
        drawdown handler (that would dead-letter an already-charged event). Every
        step — config lookup, counter increment, alert emission — is best-effort;
        the hourly reconciliation repairs any missed counter/alert from the ledger.

        Budget basis (F4.2): budgets are EFFECTIVE-month; this live counter is
        current-wall-clock-month only, so the caller (billing handler) skips it
        for events backdated into a prior month. The hourly rebuild
        (reconcile_customer → get_customer_cost_totals, effective_at-filtered)
        is the source of truth. Documented bypass: an enforcing-capped seat can
        backdate into the PRIOR month to evade the live cap — bounded by
        Tenant.backfill_window_days (0 = no backfill = airtight).
        """
        if amount_micros <= 0:
            return
        try:
            cfg = BudgetService.resolve_config(customer)
            if cfg is None or cfg.cap_micros <= 0:
                return
            old, new, label = BudgetService.record_spend(customer.tenant_id, customer.id, amount_micros)
            BudgetService.emit_threshold_alerts(customer, cfg, old, new, label)
        except Exception:
            logger.warning("budget.record_usage_spend_failed",
                           extra={"data": {"customer_id": str(customer.id)}})
