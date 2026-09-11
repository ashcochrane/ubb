"""Customer spend pool POLICY — config resolution, the gate, and threshold alerts.

The COUNTER MECHANICS (the seat-keyed month-scoped Redis counter, its
INCR/rebuild/MAX-merge Lua and TTL discipline) moved into the live counter
(#111, D3/D3b) — one client dialect, one owner of the whole Tier-2
keyspace. What stays here is everything the counter feeds: WHICH
CustomerSpendPool applies (``resolve_config_for``), the start-gate verdict with
its fail-open/fail-closed policy (``check``), and the level-based alert
emission (``emit_threshold_alerts``).
"""
import logging

from django.utils import timezone

from core.crossing import (spend_pool_stop_threshold, month_label_bounds,
                           past_spend_pool_stop)
from apps.billing.gating.services.live_counter import LiveCounter

logger = logging.getLogger("ubb.billing")


def _period():
    """(label 'YYYY-MM', period_start date, period_end date exclusive) for the
    current calendar month — the crossing module's month math (#110)."""
    return month_label_bounds(timezone.now())


class CustomerSpendPoolService:
    @staticmethod
    def resolve_config_for(tenant_id, customer_id):
        """THE CustomerSpendPool resolution — customer-specific row first, tenant
        default second. Every lane that needs a pool's line resolves through
        here (#110 retired the live lane's inline copy)."""
        from apps.billing.gating.models import CustomerSpendPool
        cfg = CustomerSpendPool.objects.filter(tenant_id=tenant_id, customer_id=customer_id).first()
        if cfg:
            return cfg
        return CustomerSpendPool.objects.filter(tenant_id=tenant_id, customer__isnull=True).first()

    @staticmethod
    def resolve_config(customer):
        return CustomerSpendPoolService.resolve_config_for(customer.tenant_id, customer.id)

    @staticmethod
    def current_spend(tenant_id, customer_id):
        """The seat's month-to-date spend — the live counter's spend-pool read
        (rebuilds from the durable ledger on a missing key; a Redis READ
        failure raises so ``check`` can apply its fail-open/closed policy)."""
        return LiveCounter.spend_pool_read(tenant_id, customer_id)

    @staticmethod
    def period_basis(tenant_id, customer_id, *, now=None):
        """The pool's DURABLE basis for the current effective month, as the
        pair the status read publishes (#456, slice 6 §4, §13): ``(label,
        known_period_charges_micros, unresolved_posting_count)`` — the
        resolved period charges, a lower bound wherever the count beside them
        is not zero, and the count of postings whose customer price UBB has
        not resolved and so could not include. Read from metering's read
        contract, which is the same total the live counter rebuilds from and
        MAX-merges toward: a status read reports the figure the gate's
        counter is a cache of, never the cache. The count is the price pair's
        own (``core.cost_totals``), not the supplier-cost pair's — a pool
        bounds what the customer is charged."""
        from apps.metering.queries import get_customer_cost_totals
        from core.amount_status_pairs import CUSTOMER_PRICE
        label, start, end = month_label_bounds(now or timezone.now())
        totals = get_customer_cost_totals(tenant_id, customer_id, start, end)
        return (label, int(totals["billed_cost_micros"]),
                int(totals[CUSTOMER_PRICE.count_key]))

    @staticmethod
    def check(customer):
        cfg = CustomerSpendPoolService.resolve_config(customer)
        if cfg is None or cfg.cap_micros <= 0:
            return {"allowed": True, "reason": None, "spend_micros": None, "cap_micros": None}
        try:
            spend = CustomerSpendPoolService.current_spend(customer.tenant_id, customer.id)
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
        # (#110): alert_only -> None -> never past.
        if past_spend_pool_stop(spend, spend_pool_stop_threshold(cfg)):
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
        cfg = CustomerSpendPoolService.resolve_config(customer)
        if cfg is None or cfg.cap_micros <= 0:
            return
        try:
            # P1 (D8/I7): the live counter's monotonic MAX-merge toward the
            # durable in-month total — never lowers, so a concurrent
            # drawdown-tail INCR can no longer be lost.
            total, label = LiveCounter.spend_pool_reconcile(customer.tenant_id, customer.id)
        except Exception:
            logger.warning("customer_spend_pool.reconcile_failed",
                           extra={"data": {"customer_id": str(customer.id)}})
            return
        CustomerSpendPoolService.emit_threshold_alerts(customer, cfg, 0, total, label)  # fires only not-yet-sent levels

    @staticmethod
    def record_usage_spend(customer, amount_micros):
        """Post-drawdown hook: increment the counter + emit threshold alerts. Fully fail-open.

        Runs after the wallet is already charged, so it must NEVER raise into the
        drawdown handler (that would dead-letter an already-charged event). Every
        step — config lookup, counter increment, alert emission — is best-effort;
        the hourly reconciliation repairs any missed counter/alert from the ledger.

        Period basis (F4.2): a pool is EFFECTIVE-month; this live counter is
        current-wall-clock-month only, so the caller (billing handler) skips it
        for events backdated into a prior month. The hourly rebuild
        (reconcile_customer → LiveCounter.spend_pool_reconcile, effective_at-filtered)
        is the source of truth. Documented bypass: an enforcing-capped seat can
        backdate into the PRIOR month to evade the live cap — bounded by
        Tenant.backfill_window_days (0 = no backfill = airtight).
        """
        if amount_micros <= 0:
            return
        try:
            cfg = CustomerSpendPoolService.resolve_config(customer)
            if cfg is None or cfg.cap_micros <= 0:
                return
            old, new, label = LiveCounter.spend_pool_incr(
                customer.tenant_id, customer.id, amount_micros)
            CustomerSpendPoolService.emit_threshold_alerts(customer, cfg, old, new, label)
        except Exception:
            logger.warning("customer_spend_pool.record_usage_spend_failed",
                           extra={"data": {"customer_id": str(customer.id)}})
