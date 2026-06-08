import logging

from django.core.cache import cache
from django.utils import timezone

from apps.metering.queries import get_customer_cost_totals

logger = logging.getLogger("ubb.billing")

_TTL_SECONDS = 62 * 24 * 3600  # current month + buffer for late reconciliation


def _period():
    """(label 'YYYY-MM', period_start date, period_end date exclusive) for the current calendar month."""
    today = timezone.now().date()
    start = today.replace(day=1)
    if today.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1)
    else:
        end = start.replace(month=start.month + 1, day=1)
    return f"{start.year:04d}-{start.month:02d}", start, end


def _key(customer_id, label):
    return f"budget:{customer_id}:{label}"


class BudgetService:
    @staticmethod
    def resolve_config(customer):
        from apps.billing.gating.models import BudgetConfig
        cfg = BudgetConfig.objects.filter(tenant_id=customer.tenant_id, customer_id=customer.id).first()
        if cfg:
            return cfg
        return BudgetConfig.objects.filter(tenant_id=customer.tenant_id, customer__isnull=True).first()

    @staticmethod
    def current_spend(tenant_id, customer_id):
        label, start, end = _period()
        key = _key(customer_id, label)
        val = cache.get(key)
        if val is not None:
            return int(val)
        total = get_customer_cost_totals(tenant_id, customer_id, start, end)["billed_cost_micros"]
        cache.set(key, total, timeout=_TTL_SECONDS)
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
        limit = cfg.cap_micros * cfg.hard_stop_pct // 100
        if cfg.enforce_mode == "enforcing" and spend >= limit:
            return {"allowed": False, "reason": "budget_exceeded",
                    "spend_micros": spend, "cap_micros": cfg.cap_micros}
        return {"allowed": True, "reason": None, "spend_micros": spend, "cap_micros": cfg.cap_micros}
