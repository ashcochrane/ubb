"""Customer spend pool POLICY — which pool applies, the start gate, the
threshold alerts, and the pool's own stop (slice 6 §4, #459).

The COUNTER MECHANICS (the seat-keyed month-scoped Redis counter, its
INCR/rebuild/MAX-merge Lua and TTL discipline) moved into the live counter
(#111, D3/D3b) — one client dialect, one owner of the whole Tier-2
keyspace. What stays here is everything the counter feeds: WHICH
CustomerSpendPool applies (``resolve_config_for``), the start-gate verdict with
its fail-open/fail-closed policy (``check``), the level-based alert
emission (``emit_threshold_alerts``), and — since #459 — the pool's stop:
the durable-lane compare on the seat's counter (``record_usage_spend``), the
seat-level bottom line (``reconcile_customer``) and the kill the pool's
winning stop transition registers (``stop_active_work``).

ENFORCEMENT IS PAYMENT-MODE INDEPENDENT (#150 §7.1, slice 6 §4 — a RULING).
A blocking pool stops a prepaid customer's active work mid-flight and refuses
its next start exactly as it stops a postpaid customer's: payment mode decides
who invoices and nothing else. Every lane below asks the mode nothing — the
drawdown handler counts the seat's charge in every mode, the live counter's
pool leg runs in every mode, and the ledger keys the pool's line by the
control rather than by the owner's tenant. ``alert_only`` stays the absence of
a stop line (``core.crossing.spend_pool_stop_threshold`` answers None), never a
flag a compare inspects.

TWO DECLARED LEVELS (#150 §7.3). A pool is declared on a customer — a seat or
a business — and a unit's charges count toward its SEAT's pool and its
BILLING OWNER's pool where each exists. The two month counters are the two
levels: the seat-keyed spend-pool counter (this module's, fed by the drawdown
handler, MAX-merged toward the seat's own durable charges) and the owner-keyed
live spend counter (the live counter's, fed by the recording lane, MAX-merged
toward the owner-aggregated durable charges). Both alert, both stop, both
refuse. THE TENANT DEFAULT APPLIES TO SEATS ONLY: a business with no row of
its own has no pool, so one configured number never becomes two lines at two
altitudes. For a standalone customer the two levels coincide — one row, one
ledger line — because it is its own billing owner.

KNOWN-OVER FIRES ON A PAIR (#150 §4.2, §4.4). The pool's durable basis is a
lower-bound pair — the resolved period charges and the count of postings
whose customer price UBB could not resolve (``period_basis``). Known charges
at or over the stop line block; known below with unknowns present alerts and
never blocks. ``unknown`` revenue is excluded from the figure and reported
beside it; ``not_applicable`` is excluded and reported as excluded; ``waived``
is the one honest zero. Nothing here sums an unknown as zero: the drawdown
handler counts a posting only when it carries a resolved amount, and the
rebuild reads the same pair.

THE CHARGE IS COUNTED EXACTLY ONCE. ADR-0013 makes a delivered fixed-price
unit's Charge → posting → ``usage.recorded`` chain 1:1, and the drawdown
handler increments the seat's pool once per posting; a replayed close writes
no second Charge and so no second increment. The test that pins it is
``test_a_blocking_pool_stops_prepaid_work_as_it_stops_postpaid.py``.

⚠ AN INPUT THIS MODULE OWES A LATER TICKET, STATED HERE WHERE THE POOL IS
COUNTED: **a compensating Charge must decrement its period's pool.** Today a
compensating record is refused a projection outright
(``pricing/services/charge_projection.py``) because the money rails act only
on a positive amount, so nothing can reach this module with a negative
figure; the day a compensating Charge has a path to the rails (#472), the
period it compensates must have its pool decremented by the compensated
amount — on the seat's counter, on the owner's, and in the durable basis the
rebuild reads — or the pool will bound revenue the tenant has since given
back. Not built here (the spec's Out of Scope hands it to #194's issue).

THE STOP REACHES `killed` ONLY THROUGH THE KERNEL (slice 6 §1). On the
pool line's winning stop transition every active unit of the stopped
customer is killed through ``TaskService.kill_and_announce`` with the pool's
word as the cause, ``pool_crossing`` as the mechanism and the pool row's id as
the control — billing imports the kernel, never the reverse (ADR-001 rule 1),
and the kill runs after the transition commits, in its own transaction, as
the ceiling's does: the crossing charge is already recorded and billed, and
the kill is a signal, never a wall. The hourly patrol re-sweeps active work
under an open pool line so a kill that crashed is late, never lost.

THE FAIL-CLOSED POSTURE on the pool read is unchanged and still read: the
pool row's own ``fail_closed`` first, else the tenant's risk row
(``RiskConfig.gate_fail_closed``) — the one column that row keeps (§1).
"""
import logging

from django.db import transaction
from django.utils import timezone

from core.crossing import (spend_pool_stop_threshold, month_label_bounds,
                           past_spend_pool_stop)
from core.vocabulary import (
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_UNAVAILABLE,
    TASK_STATUS_ACTIVE, TRIGGER_SOURCE_POOL_CROSSING)
from apps.billing.gating.services.live_counter import LiveCounter
from apps.platform.tenants.flags import enforcing
from apps.platform.work import reasons

logger = logging.getLogger("ubb.billing")

#: The customer altitude the tenant default never reaches (slice 6 §4). The
#: account type has no registry seat; it is `Customer.ACCOUNT_TYPE_CHOICES`'
#: own literal, spelled here the way the postpaid invoicing service spells it.
A_BUSINESS = "business"


def _period():
    """(label 'YYYY-MM', period_start date, period_end date exclusive) for the
    current calendar month — the crossing module's month math (#110)."""
    return month_label_bounds(timezone.now())


class CustomerSpendPoolService:
    @staticmethod
    def resolve_config_for(tenant_id, customer_id, *, account_type=None):
        """THE CustomerSpendPool resolution — the customer's own row first,
        the tenant default second, AND THE DEFAULT REACHES A SEAT ONLY (slice
        6 §4, #459): a business with no row of its own has no pool, so one
        configured number never becomes a line at two altitudes. Every lane
        that needs a pool's line resolves through here (#110 retired the live
        lane's inline copy). ``account_type`` is read off the customer row
        when the caller holds it and looked up once otherwise — only on the
        fallback path, so a customer with its own row still costs one query."""
        from apps.billing.gating.models import CustomerSpendPool
        cfg = CustomerSpendPool.objects.filter(tenant_id=tenant_id, customer_id=customer_id).first()
        if cfg:
            return cfg
        if account_type is None:
            from apps.platform.customers.models import Customer
            account_type = (Customer.all_objects.filter(id=customer_id)
                            .values_list("account_type", flat=True).first())
        if account_type == A_BUSINESS:
            return None
        return CustomerSpendPool.objects.filter(tenant_id=tenant_id, customer__isnull=True).first()

    @staticmethod
    def resolve_config(customer):
        return CustomerSpendPoolService.resolve_config_for(
            customer.tenant_id, customer.id, account_type=customer.account_type)

    @staticmethod
    def current_spend(tenant_id, customer_id):
        """The seat's month-to-date spend — the live counter's spend-pool read
        (rebuilds from the durable ledger on a missing key; a Redis READ
        failure raises so ``check`` can apply its fail-open/closed policy)."""
        return LiveCounter.spend_pool_read(tenant_id, customer_id)

    @staticmethod
    def period_basis(tenant_id, customer_id, *, now=None):
        """The pool's DURABLE basis for the current effective month: the
        period label, then the pair the status read publishes (#456, slice 6
        §4, §13) — ``(label, known_period_charges_micros,
        unresolved_posting_count)``: the resolved period charges, a lower
        bound wherever the count beside them is not zero, and the count of
        postings whose customer price UBB has not resolved and so could not
        include. Read from metering's read
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
        """The start gate's pool verdict for one SEAT, in the registry's own
        refusal words (`affordability_reason`, held by constant): the seat's
        known period charges at or over its pool's stop line refuse the
        start; a pool whose state cannot be read refuses only under the
        fail-closed posture."""
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
                return {"allowed": False,
                        "reason": AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_UNAVAILABLE,
                        "spend_micros": None, "cap_micros": cfg.cap_micros}
            return {"allowed": True, "reason": None, "spend_micros": None, "cap_micros": cfg.cap_micros}
        # The crossing module owns the stop line + enforce_mode semantics
        # (#110): alert_only -> None -> never past.
        if past_spend_pool_stop(spend, spend_pool_stop_threshold(cfg)):
            return {"allowed": False,
                    "reason": AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
                    "spend_micros": spend, "cap_micros": cfg.cap_micros}
        return {"allowed": True, "reason": None, "spend_micros": spend, "cap_micros": cfg.cap_micros}

    @staticmethod
    def emit_threshold_alerts(customer, cfg, old, new, label):
        """The level-based alerts for ONE declared level — the customer the
        pool row is declared on, a seat or a business — deduplicated per
        (customer, period, level) on the outbox. Both levels alert: the
        drawdown handler and the seat reconcile call this for the seat, the
        live counter's pool leg and the owner reconcile for the owner."""
        if cfg is None or cfg.cap_micros <= 0:
            return
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
    def signal_if_past(customer, cfg, spend_micros):
        """The DURABLE lane's stop for one declared level (#459): the
        customer's known period charges at or over the pool's stop line
        drive the pool's line on the signal ledger — the winner announces
        the customer-wide stop, suspends and registers the kill; a crossing
        the live lane already signalled loses silently — and re-align the
        fast flag.
        Signals exist only in enforcing (#42); the compare is the shared
        predicate and the line is the pool's own (``alert_only`` = no line).
        Returns True when the customer is past the line."""
        tenant = customer.tenant
        if not enforcing(tenant):
            return False
        if not past_spend_pool_stop(spend_micros, spend_pool_stop_threshold(cfg)):
            return False
        from apps.billing.gating.services.stop_signal_service import StopSignalService
        try:
            StopSignalService.drive_stop(
                customer.id, tenant, line=reasons.CUSTOMER_SPEND_POOL,
                control_id=cfg.id)
        except Exception:
            logger.warning("customer_spend_pool.stop_transition_failed",
                           extra={"data": {"customer_id": str(customer.id)}})
        LiveCounter.ensure_stop_flag(customer.id, reasons.CUSTOMER_SPEND_POOL)
        return True

    @staticmethod
    def stop_active_work(owner_id, tenant, control_id):
        """Every active unit of the stopped customer reaches `killed` through
        the kernel (slice 6 §1, §4): the pool's word as the cause,
        ``pool_crossing`` as the mechanism, the pool row as the control. The
        customer is the one the pool's line is declared on — a seat's own
        work, or every unit a business is the billing owner of — and a
        parent's kill cascades to its contained work inside the kernel.
        ``kill_and_announce`` never raises and a lost race (already
        terminal) is simply not counted, so this is safe to run again from
        the patrol. Returns how many pieces of work this call stopped."""
        from django.db.models import Q
        from apps.platform.work.models import Task
        from apps.platform.work.services import TaskService
        stopped = 0
        active = (Task.objects.filter(tenant_id=tenant.id, status=TASK_STATUS_ACTIVE)
                  .filter(Q(customer_id=owner_id) | Q(billing_owner_id=owner_id))
                  .only("id", "customer_id"))
        for unit in active.iterator():
            if TaskService.kill_and_announce(
                    unit.id, reasons.CUSTOMER_SPEND_POOL,
                    tenant_id=tenant.id, customer_id=unit.customer_id,
                    trigger_source=TRIGGER_SOURCE_POOL_CROSSING,
                    control_id=control_id):
                stopped += 1
        return stopped

    @staticmethod
    def reconcile_customer(customer, *, now=None):
        """The seat-level hourly bottom line: MAX-merge the seat's counter
        toward its durable period charges, fire any not-yet-sent alert, and
        drive the pool's line both ways — a crossing the lanes missed is
        signalled here (late, never lost), a stale one (month rollover, a
        raised or removed pool) is cleared and the customer's work may begin
        again. A customer whose pool has gone still clears."""
        from apps.billing.gating.services.stop_signal_service import CLEAR_RECONCILED
        cfg = CustomerSpendPoolService.resolve_config(customer)
        if cfg is None or cfg.cap_micros <= 0:
            CustomerSpendPoolService._lift_if_open(customer, CLEAR_RECONCILED)
            return
        try:
            # P1 (D8/I7): the live counter's monotonic MAX-merge toward the
            # durable in-month total — never lowers, so a concurrent
            # drawdown-tail INCR can no longer be lost.
            total, label = LiveCounter.spend_pool_reconcile(
                customer.tenant_id, customer.id, now=now)
        except Exception:
            logger.warning("customer_spend_pool.reconcile_failed",
                           extra={"data": {"customer_id": str(customer.id)}})
            return
        CustomerSpendPoolService.emit_threshold_alerts(customer, cfg, 0, total, label)  # fires only not-yet-sent levels
        if CustomerSpendPoolService.signal_if_past(customer, cfg, total):
            # A kill that crashed between the transition and its commit is
            # retried here: the sweep is idempotent.
            CustomerSpendPoolService.stop_active_work(
                customer.id, customer.tenant, cfg.id)
        else:
            CustomerSpendPoolService._lift_if_open(customer, CLEAR_RECONCILED)

    @staticmethod
    def _lift_if_open(customer, clear_reason):
        tenant = customer.tenant
        if not enforcing(tenant):
            return
        try:
            LiveCounter.resume(customer.id, tenant, line=reasons.CUSTOMER_SPEND_POOL,
                               clear_reason=clear_reason)
        except Exception:
            logger.warning("customer_spend_pool.resume_failed",
                           extra={"data": {"customer_id": str(customer.id)}})

    @staticmethod
    def record_usage_spend(customer, amount_micros):
        """Post-drawdown hook: increment the seat's counter, emit threshold
        alerts, and — the durable lane of the pool's stop (#459) — signal a
        crossing. Fully fail-open.

        Runs after the wallet is already charged, so it must NEVER raise into the
        drawdown handler (that would dead-letter an already-charged event). Every
        step — config lookup, counter increment, alert emission, the signal —
        is best-effort; the hourly reconciliation repairs any missed
        counter/alert/signal from the ledger.

        Period basis (F4.2): a pool is EFFECTIVE-month; this live counter is
        current-wall-clock-month only, so the caller (billing handler) skips it
        for events backdated into a prior month. The hourly rebuild
        (reconcile_customer → LiveCounter.spend_pool_reconcile, effective_at-filtered)
        is the source of truth. Documented bypass: an enforcing-capped seat can
        backdate into the PRIOR month to evade the live cap — bounded by
        Tenant.backfill_window_days (0 = no backfill = airtight).

        The amount is the posting's RESOLVED customer price and nothing else:
        the handler hands this nothing for a posting whose price is unknown or
        not applicable, which is what keeps the figure a floor that never sums
        an unknown as zero.
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
            CustomerSpendPoolService.signal_if_past(customer, cfg, new)
        except Exception:
            logger.warning("customer_spend_pool.record_usage_spend_failed",
                           extra={"data": {"customer_id": str(customer.id)}})
