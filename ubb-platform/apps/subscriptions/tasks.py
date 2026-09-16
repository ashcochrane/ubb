import datetime
import logging

from celery import shared_task
from django.utils import timezone

from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY
from apps.platform.events.tasks import RETRY_HORIZON as OUTBOX_RETRY_HORIZON
from apps.platform.tenants.models import Tenant
from apps.subscriptions.economics.services import MarginService
from apps.subscriptions.stripe.sync import sync_subscriptions

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_economics")
def calculate_all_economics_task():
    """Daily task: snapshot margin for all metering tenants."""
    today = timezone.now().date()
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1)

    tenants = Tenant.objects.filter(
        products__contains=["metering"],
        is_active=True,
    )

    for tenant in tenants:
        try:
            results = MarginService.snapshot_all(
                tenant.id, period_start, period_end,
            )
            logger.info(
                "Margin snapshots calculated",
                extra={"data": {
                    "tenant_id": str(tenant.id),
                    "snapshots": len(results),
                }},
            )
        except Exception:
            logger.exception(
                "Margin snapshot failed",
                extra={"data": {"tenant_id": str(tenant.id)}},
            )


#: WHAT THE POSTING LEDGER SAYS ABOUT A PERIOD, IN THE ACCUMULATOR'S OWN
#: COLUMNS. One mapping rather than two copies of it: the hourly repair below
#: reads a whole tenant's ledger and the marker path reads one customer's, and
#: an accumulator repaired by one route into a different shape from the other is
#: the drift both of them exist to remove.
#:
#: The two PAIRS are what make it a mapping rather than a list (#328, #351): the
#: read contract counts the postings each total excluded, and a row repaired to
#: the right totals while keeping stale counts is a row that disagrees with
#: itself.
_LEDGER_COLUMNS = (
    ("total_provider_cost_micros", "provider_cost_micros"),
    ("unresolved_event_count", UNRESOLVED_EVENT_COUNT_KEY),
    ("total_billed_cost_micros", "billed_cost_micros"),
    ("unpriced_event_count", UNPRICED_EVENT_COUNT_KEY),
    ("event_count", "event_count"),
)

#: The ledger's answer for a customer that has no postings in the period at all
#: — a complete answer rather than an unknown one, and the shape the repair
#: needs when an accumulator has outlived the postings behind it.
_NOTHING_IN_THE_PERIOD = {ledger_key: 0 for _, ledger_key in _LEDGER_COLUMNS}


def repair_one_accumulator(tenant_id, customer_id, period_start, period_end,
                           totals) -> bool:
    """Set one period's accumulator to what the posting ledger says.

    Returns whether anything moved, which is the drift both callers report.
    `totals` is a row of the metering read contract's cost totals, or
    `_NOTHING_IN_THE_PERIOD` where the ledger has none.

    ⚠ **THE PERIOD END IS WRITTEN WITHOUT BEING COMPARED**, which is deliberate
    and not an oversight: it is the calendar's answer rather than the ledger's,
    so a row differing only there is a row whose stored bound was wrong, and
    correcting it silently is right. Drift is about the figures.
    """
    from apps.subscriptions.economics.models import CustomerCostAccumulator

    columns = {column: totals[ledger_key] for column, ledger_key in _LEDGER_COLUMNS}
    acc = CustomerCostAccumulator.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        period_start=period_start).first()
    if acc is None and not any(columns.values()):
        # NOTHING TO CACHE AND NOTHING CACHING IT. A customer whose period the
        # ledger has no postings for is already answered correctly by the
        # absence — `snapshot_customer` reads a missing accumulator as no cost
        # and nothing left out — so writing a row of zeros would add a record
        # that says exactly what its absence said.
        return False
    if acc is None:
        CustomerCostAccumulator.objects.create(
            tenant_id=tenant_id, customer_id=customer_id,
            period_start=period_start, period_end=period_end, **columns)
        return True
    if all(getattr(acc, column) == value for column, value in columns.items()):
        return False
    CustomerCostAccumulator.objects.filter(id=acc.id).update(
        period_end=period_end, **columns)
    return True


@shared_task(queue="ubb_economics")
def reconcile_cost_accumulators():
    """Source-of-truth repair: recompute each open-period CustomerCostAccumulator
    from SUM(Posting) by effective_at (mirrors reconcile_usage_drawdowns).

    Covers current + TWO previous calendar months: the backfill window
    (Tenant.backfill_window_days, max 60 days) can span 3 calendar months, so a
    maximally backdated event still lands inside the reconcile horizon and is
    corrected within the hour.

    ⚠ **THIS HORIZON IS A SWEEP AND NOT AN AUTHORITY** (#502, slice 7 §8). It
    catches drift in the months a backdated recording can reach on its own, and
    it used to be the only thing that repaired these rows at all — which quietly
    made three months the age past which a figure UBB knew to be wrong stayed
    wrong. What repairs an OLDER period is the marker channel, which is bounded
    by nothing: `resnapshot_dirty_periods` calls the same repair below for
    whatever month a marker names. Neither is a reporting surface any more, so
    nothing a tenant reads waits on either.

    # TODO: extend to aggregate business-level rollup once Stage-E2 "seats never
    # invoiced directly" semantics are confirmed stable (avoid double-counting).
    """
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.models import CustomerCostAccumulator
    from apps.subscriptions.handlers import _period_bounds_for

    today = timezone.now().date()
    cur_start, cur_end = _period_bounds_for(today)
    prev_start, prev_end = _period_bounds_for(cur_start - datetime.timedelta(days=1))
    prev2_start, prev2_end = _period_bounds_for(prev_start - datetime.timedelta(days=1))

    drift = 0
    for period_start, period_end in ((prev2_start, prev2_end),
                                     (prev_start, prev_end), (cur_start, cur_end)):
        for tenant in Tenant.objects.filter(products__contains=["metering"], is_active=True):
            ledger = {r["customer_id"]: r
                      for r in get_per_customer_cost_totals(tenant.id, period_start, period_end)}
            stored = set(CustomerCostAccumulator.objects.filter(
                tenant_id=tenant.id, period_start=period_start
            ).values_list("customer_id", flat=True))
            for customer_id in stored | set(ledger):
                if repair_one_accumulator(
                        tenant.id, customer_id, period_start, period_end,
                        ledger.get(customer_id, _NOTHING_IN_THE_PERIOD)):
                    drift += 1

    logger.info("cost_accumulator_reconcile", extra={"data": {"drift_count": drift}})


# Markers younger than this are NOT consumed. The snapshot reads the cost
# accumulator, which the OUTBOX populates — a dispatch can legitimately land
# up to RETRY_HORIZON after the backfill committed (the outbox retry backoff
# before dead-letter). Acking a younger marker could freeze the prior-month
# snapshot against an accumulator that has not seen the backfill yet — wrong
# forever. 3h covers the dead-letter horizon plus one full :50 accumulator
# reconcile pass (which repairs even a dead-lettered dispatch from the ledger).
RESNAPSHOT_MARKER_MIN_AGE = datetime.timedelta(hours=3)
# Loud rot: growing the outbox backoff schedule past this age would ack
# markers whose accumulator dispatch is still legitimately in flight.
assert RESNAPSHOT_MARKER_MIN_AGE > OUTBOX_RETRY_HORIZON


@shared_task(queue="ubb_economics")
def resnapshot_dirty_periods():
    """Rebuild a closed period's two per-customer caches when its facts move.

    Consumes BackfillDirtyPeriod markers via the metering read contract —
    only markers older than RESNAPSHOT_MARKER_MIN_AGE, so the accumulator the
    snapshot reads has provably settled (outbox horizon + one reconcile pass).
    For a marker on a PRIOR month: repair the accumulator from the posting
    ledger, then re-run snapshot_customer (update_or_create, idempotent) +
    evaluate_and_emit (transition-guarded + OutboxEvent-deduped, idempotent),
    then ack the marker — a crash before the ack leaves the marker for the next
    hourly run. A NON-prior (current/future-month) marker is skipped WITHOUT
    ack: markers are only ever written for prior months, so one is reachable
    here only via clock skew, and acking it would discard work — it is consumed
    once the month genuinely rolls past it.

    ⚠ **THE REPAIR IS WHAT MAKES THE MARKER WORK AT ANY AGE** (#502, slice 7
    §8). The snapshot is built from the accumulator, and the accumulator is
    swept on a three-month horizon — so consuming a marker on an older month
    without repairing first would faithfully re-freeze the figures the period
    had when its cost was still unknown, and ack the marker for having done it.
    Reading the ledger for the one customer the marker names costs one query and
    takes the horizon out of the path entirely, which is what "a cache is
    invalidatable by anything that can change its inputs, at any age" means.

    ⚠ **AND IT MAKES THE MINIMUM AGE MORE LOAD-BEARING, NOT LESS.** The repair
    SETS the row from the ledger, where the outbox handler INCREMENTS it — so a
    dispatch landing after a repair would add its event on top of a total that
    already counted it. The floor is what keeps the two apart, and it is why
    this waits out the dispatch horizon rather than trusting the repair to make
    waiting unnecessary.

    Beat: hourly at :55, AFTER reconcile_cost_accumulators (:50).
    """
    from apps.metering.queries import (
        clear_backfill_dirty_period, get_customer_cost_totals,
        list_backfill_dirty_periods,
    )
    from apps.subscriptions.handlers import _period_bounds_for

    cur_start, _ = _period_bounds_for(timezone.now().date())
    resnapshots = 0
    cutoff = timezone.now() - RESNAPSHOT_MARKER_MIN_AGE
    for marker in list_backfill_dirty_periods(created_before=cutoff):
        period_start = marker["period_start"]
        try:
            if period_start >= cur_start:
                # Clock-skew guard: leave the marker in place (no ack).
                continue
            _, period_end = _period_bounds_for(period_start)
            repair_one_accumulator(
                marker["tenant_id"], marker["customer_id"], period_start,
                period_end,
                get_customer_cost_totals(marker["tenant_id"],
                                         marker["customer_id"],
                                         period_start, period_end))
            econ = MarginService.snapshot_customer(
                marker["tenant_id"], marker["customer_id"],
                period_start, period_end)
            MarginService.evaluate_and_emit(econ)
            resnapshots += 1
            # Ack AFTER the snapshot work succeeded — a crash before this
            # leaves the marker for the next hourly run.
            clear_backfill_dirty_period(marker["id"])
        except Exception:
            # Keep the marker: retried next hour. Other markers still run.
            logger.exception("resnapshot_dirty_period_failed", extra={"data": {
                "tenant_id": str(marker["tenant_id"]),
                "customer_id": str(marker["customer_id"]),
                "period_start": str(period_start)}})
    if resnapshots:
        logger.info("resnapshot_dirty_periods", extra={"data": {
            "resnapshots": resnapshots}})


@shared_task(queue="ubb_subscriptions")
def sync_tenant_subscriptions_task(tenant_id):
    """On-demand task: sync subscriptions for a specific tenant."""
    tenant = Tenant.objects.get(id=tenant_id)
    result = sync_subscriptions(tenant)
    logger.info(
        "Subscription sync completed",
        extra={"data": {"tenant_id": str(tenant_id), **result}},
    )
    return result


@shared_task(queue="ubb_subscriptions")
def reconcile_subscription_mirrors():
    """Hourly repair of the Stripe subscription mirror.

    The mirror is a pure cache of Stripe's state, refreshed by
    customer.subscription.* webhooks. A missed webhook would otherwise leave a
    canceled subscription displayed as active indefinitely — every other cache
    in this codebase has a scheduled reconciler; this one did not until
    2026-07-27 (sync_tenant_subscriptions_task existed but was never wired).

    Fans out one task per tenant with a connected account; tenants without one
    have no subscriptions to mirror.
    """
    from apps.platform.tenants.models import Tenant

    tenant_ids = Tenant.objects.exclude(
        stripe_connected_account_id="",
    ).exclude(
        stripe_connected_account_id__isnull=True,
    ).values_list("id", flat=True)
    for tenant_id in tenant_ids:
        sync_tenant_subscriptions_task.delay(str(tenant_id))
