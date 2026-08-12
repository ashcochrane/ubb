"""Metering Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(billing, subscriptions, referrals) to read metering data.
Functions return plain dicts, never ORM instances.

If metering becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/tenant_billing/services.py → get_period_totals()
- api/v1/billing_endpoints.py → get_revenue_analytics()
- apps/referrals/rewards/reconciliation.py → get_customer_usage_for_period()
- apps/billing/gating/tasks.py → get_customer_ids_with_usage()
- apps/billing/invoicing/tasks.py → get_customer_ids_with_usage()
- apps/billing/invoicing/services/postpaid_service.py → get_customer_cost_totals(),
  get_billed_totals_by_customer(), get_customer_billed_breakdown()
- apps/billing/wallets/tasks.py → iter_billable_usage_events()
- apps/subscriptions/handlers.py → get_usage_event_effective_at()
- apps/subscriptions/tasks.py → list_backfill_dirty_periods(),
  clear_backfill_dirty_period() (the ack half of the marker contract)
- api/v1/me_endpoints.py → get_customer_usage_summary()
"""
import uuid
from datetime import date, datetime
from typing import Iterator, TypedDict

from django.db.models import Sum, Count
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import TruncDate

from core.time_windows import utc_day_start, utc_next_day_start
from apps.platform.grouping_fields.models import SLOT_CHOICES

#: The slot columns a caller may group by, read off the registry that owns the
#: vocabulary. Restating it as a literal range here is how the two come to
#: disagree.
SLOTS = tuple(slot for slot, _ in SLOT_CHOICES)


class PeriodTotals(TypedDict):
    total_cost_micros: int
    event_count: int


#: STILL SPELLS THE RETIRED NOUN, DELIBERATELY, AND NOBODY OWNS IT YET (#269).
#:
#: #269 renamed the model and its table; it did not rename the *names built on*
#: the model, and the ticket says so — "the model, the table, the two neighbours
#: that reference it, and the tests that name it". Three groups survive the
#: rename and they are not in the same position:
#:
#:   * `UsageEventOut` / `UsageEventDetailOut` (`api/v1/schemas.py`) are on the
#:     PUBLISHED contract. Renaming a schema is a contract break, and ADR-0007 §3
#:     forbids doing it twice on one field — so it happens once, deliberately,
#:     in whichever slice rebuilds that surface.
#:   * `iter_billable_usage_events` and `get_usage_event_cost` are `queries.py`
#:     read-contract entry points, consumed across a product boundary
#:     (`apps/billing/wallets/`). Renaming them is a same-commit change on both
#:     sides, cheap but out of #269's stated extent.
#:   * This TypedDict is neither: it is internal to metering and it names a
#:     thing that is now called something else. It is the one of the three with
#:     no reason to wait, and it is recorded here rather than renamed only
#:     because #269 declined to widen — a later reader should treat it as
#:     payable, not as a decision.
class UsageEventCost(TypedDict):
    billed_cost_micros: int
    provider_cost_micros: int


def get_period_totals(tenant_id: str, period_start: date, period_end: date,
                      basis: str = "effective") -> PeriodTotals:
    """Get aggregate usage totals for a tenant's billing period.

    Returns dict with 'total_cost_micros' and 'event_count'.
    basis="effective" windows on effective_at (when the usage happened);
    basis="arrival" windows on created_at (when it was recorded) — used by
    tenant platform-fee reconciliation, which accrues fees in the ARRIVAL
    period to match the wall-clock live accumulator.
    """
    from apps.metering.usage.models import Posting

    if basis not in ("effective", "arrival"):
        raise ValueError("basis must be 'effective' or 'arrival'")
    field = "created_at" if basis == "arrival" else "effective_at"
    totals = Posting.objects.filter(
        tenant_id=tenant_id,
        **{f"{field}__gte": utc_day_start(period_start),
           f"{field}__lt": utc_day_start(period_end)},
    ).aggregate(
        total_cost=Sum("billed_cost_micros"),
        event_count=Count("id"),
    )

    return {
        "total_cost_micros": totals["total_cost"] or 0,
        "event_count": totals["event_count"] or 0,
    }


def get_usage_event_cost(usage_event_id: str, tenant_id: str | None = None) -> int | None:
    """Get the billed cost of a usage event. Returns int or None.

    If tenant_id is provided, only returns cost for events belonging to that tenant.
    """
    from apps.metering.usage.models import Posting

    qs = Posting.objects.filter(id=usage_event_id)
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    event = qs.values_list("billed_cost_micros", flat=True).first()
    return event


class RevenueAnalytics(TypedDict):
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    total_markup_micros: int
    daily: list[dict]


def get_revenue_analytics(
    tenant_id: str, start_date: date = None, end_date: date = None,
) -> RevenueAnalytics:
    """Get revenue analytics with totals and daily breakdown.

    Returns dict with total provider/billed/markup costs and a daily
    list of dicts with day, provider_cost_micros, billed_cost_micros,
    event_count.
    """
    from apps.metering.usage.models import Posting

    qs = Posting.objects.filter(tenant_id=tenant_id)

    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))

    totals = qs.aggregate(
        total_provider_cost_micros=Sum("provider_cost_micros"),
        total_billed_cost_micros=Sum("billed_cost_micros"),
    )

    provider_cost = totals["total_provider_cost_micros"] or 0
    billed_cost = totals["total_billed_cost_micros"] or 0

    daily = list(
        qs.annotate(day=TruncDate("effective_at")).values("day").annotate(
            provider_cost_micros=Sum("provider_cost_micros"),
            billed_cost_micros=Sum("billed_cost_micros"),
            event_count=Count("id"),
        ).order_by("day")
    )

    for entry in daily:
        if entry.get("day"):
            entry["day"] = entry["day"].isoformat()

    # provider_cost == 0 is valid (free provider); None means no provider cost data.
    raw_provider = totals["total_provider_cost_micros"]
    if raw_provider is not None:
        markup = billed_cost - provider_cost
    else:
        markup = 0

    return {
        "total_provider_cost_micros": provider_cost,
        "total_billed_cost_micros": billed_cost,
        "total_markup_micros": markup,
        "daily": daily,
    }


def get_customer_usage_for_period(
    tenant_id: str, customer_id: str, period_start: date, period_end: date,
) -> list[UsageEventCost]:
    """Get per-event usage data for a customer in a period.

    Returns list of dicts with billed_cost_micros, provider_cost_micros.
    Used by referrals reconciliation.
    """
    from apps.metering.usage.models import Posting

    events = Posting.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
        effective_at__gte=period_start,
        effective_at__lt=period_end,
    ).values("billed_cost_micros", "provider_cost_micros")

    return list(events)


class CustomerUsageSummary(TypedDict):
    total_billed_micros: int
    event_count: int
    metrics: list[dict]


def get_customer_usage_summary(tenant_id, customer_id, period_start: date,
                               period_end: date) -> CustomerUsageSummary:
    """Per-event_type usage rollup for ONE customer over [period_start, period_end).

    Each row: {event_type, billed_cost_micros, event_count}; the grand
    totals equal the sum of the rows by construction. A BUSINESS customer
    aggregates across its seats — the same seat basis as the postpaid business
    branch (aggregate_lines): ALL seats incl. soft-deleted via all_objects, ONE
    grouped query via customer_id__in; a business emits no usage of its own.
    Rows sort largest-billed first (ties by event_type). Sargable half-open day
    window via core.time_windows.

    The rollup ITSELF is what replaced the posting's inline unit total (#272):
    one comparable magnitude per Event Type, rather than one nameless integer
    summed across Event Types whose granularities differ.
    """
    from apps.metering.usage.models import Posting
    from apps.platform.customers.models import Customer

    customer_ids = [customer_id]
    account_type = Customer.all_objects.filter(id=customer_id).values_list(
        "account_type", flat=True).first()
    if account_type == "business":
        customer_ids = list(Customer.all_objects.filter(
            parent_id=customer_id).values_list("id", flat=True))
        if not customer_ids:
            return {"total_billed_micros": 0, "event_count": 0, "metrics": []}

    rows = (Posting.objects.filter(
        tenant_id=tenant_id, customer_id__in=customer_ids,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    ).values("event_type").annotate(
        billed_sum=Sum("billed_cost_micros"), cnt=Count("id"),
    ).order_by())

    metrics = sorted(
        ({"event_type": r["event_type"],
          "billed_cost_micros": r["billed_sum"] or 0, "event_count": r["cnt"]}
         for r in rows),
        key=lambda m: (-m["billed_cost_micros"], m["event_type"]))
    return {
        "total_billed_micros": sum(m["billed_cost_micros"] for m in metrics),
        "event_count": sum(m["event_count"] for m in metrics),
        "metrics": metrics,
    }


def get_customer_cost_totals(tenant_id, customer_id, start_date, end_date) -> dict:
    """Provider + billed cost totals for one customer over [start, end)."""
    from apps.metering.usage.models import Posting
    agg = Posting.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        effective_at__gte=utc_day_start(start_date),
        effective_at__lt=utc_day_start(end_date),
    ).aggregate(
        provider=Sum("provider_cost_micros"), billed=Sum("billed_cost_micros"),
        count=Count("id"),
    )
    return {
        "provider_cost_micros": agg["provider"] or 0,
        "billed_cost_micros": agg["billed"] or 0,
        "event_count": agg["count"] or 0,
    }


def get_billing_owner_billed_total(tenant_id, billing_owner_id, start_date, end_date) -> int:
    """Σ billed_cost_micros over [start, end) for every event whose pinned
    billing owner is ``billing_owner_id`` (Stage D ``Posting.billing_owner_id``).

    This OWNER-aggregates a pooled business across all its seats (each seat's
    events pin the business as billing owner) and reduces to a single seat for
    an allocated/individual owner (whose events pin themselves). It is the
    durable source of truth the Tier-2 postpaid live-spend counter MAX-merges
    toward (apps.billing.gating.services.live_counter)."""
    from apps.metering.usage.models import Posting
    return Posting.objects.filter(
        tenant_id=tenant_id, billing_owner_id=billing_owner_id,
        effective_at__gte=utc_day_start(start_date),
        effective_at__lt=utc_day_start(end_date),
    ).aggregate(billed=Sum("billed_cost_micros"))["billed"] or 0


def get_usage_timeseries(tenant_id, *, granularity="day", customer_id=None,
                         group_by=None, start_date=None, end_date=None) -> list[dict]:
    """Time-series spend rollup: daily or hourly COGS per tenant, optionally per customer/dimension.

    Returns list of dicts with bucket (ISO string), provider_cost_micros, billed_cost_micros,
    markup_micros, event_count, and optionally dimension (when group_by is set).
    """
    from django.db.models.functions import TruncHour
    from apps.metering.usage.models import Posting

    trunc = TruncHour if granularity == "hour" else TruncDate
    qs = Posting.objects.filter(tenant_id=tenant_id)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # end_date is INCLUSIVE, matching the /analytics/usage rollup — this is
        # the sole caller (the /analytics/usage/timeseries endpoint), so the two
        # sibling endpoints resolve the same date inputs identically.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))

    valid_group_by = ("provider", "event_type", "task_type", "subtask_type",
                      *SLOTS)
    cols = ["bucket"]
    if group_by in valid_group_by:
        cols.append(group_by)

    rows = (qs.annotate(bucket=trunc("effective_at")).values(*cols).annotate(
        provider_cost_micros=Sum("provider_cost_micros"),
        billed_cost_micros=Sum("billed_cost_micros"),
        event_count=Count("id")).order_by("bucket"))

    out = []
    for r in rows:
        d = dict(r)
        d["bucket"] = d["bucket"].isoformat() if d.get("bucket") else None
        if group_by and group_by in d:
            raw_dim = d.pop(group_by)
            # Map empty string or None to the unattributed sentinel so no events
            # are silently dropped and every timeseries bucket reconciles to the total.
            d["dimension"] = raw_dim if raw_dim else "(unattributed)"
        d["markup_micros"] = (d["billed_cost_micros"] or 0) - (d["provider_cost_micros"] or 0)
        out.append(d)
    return out


def get_per_customer_cost_totals(tenant_id, start_date, end_date) -> list[dict]:
    """Per-customer provider + billed totals over [start, end)."""
    from apps.metering.usage.models import Posting
    rows = (Posting.objects.filter(
        tenant_id=tenant_id,
        effective_at__gte=utc_day_start(start_date),
        effective_at__lt=utc_day_start(end_date),
    ).values("customer_id").annotate(
        provider_cost_micros=Sum("provider_cost_micros"),
        billed_cost_micros=Sum("billed_cost_micros"),
        event_count=Count("id"),
    ).order_by("-billed_cost_micros"))
    return [dict(r) for r in rows]


def get_dimensional_margin(tenant_id, *, group_by=None, tag_key=None,
                           start_date=None, end_date=None) -> list[dict]:
    """Usage-only margin (billed - provider) grouped by a column or a tag key.

    group_by in {"provider", "event_type", "task_type", "subtask_type",
    "grouping_field_1".."grouping_field_10"} (a resolved column, not a
    tenant-facing key — the caller resolves the tenant's declared name via the
    Grouping Field registry first);
    OR tag_key for a key read out of the open bag.
    Each row: {grouping_field_value, provider_cost_micros, billed_cost_micros,
    margin_micros, event_count}.

    The row key names the VALUE grouped rather than the axis it was grouped on,
    because the caller already chose the axis and the row would otherwise repeat
    it once per row. `get_usage_timeseries` above still spells its own row key
    the old way: that is the analytics grouping surface, whose vocabulary is
    owned by a later slice, and moving it here would take a debt that slice is
    still counting.
    """
    from apps.metering.usage.models import Posting
    qs = Posting.objects.filter(tenant_id=tenant_id)
    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        qs = qs.filter(effective_at__lt=utc_day_start(end_date))

    def _row(value, provider, billed, count):
        return {"grouping_field_value": value, "provider_cost_micros": provider or 0,
                "billed_cost_micros": billed or 0,
                "margin_micros": (billed or 0) - (provider or 0), "event_count": count}

    if tag_key:
        # The keyed margin breakdown is slice 7's surface, left where #273
        # found it — only the column underneath moved, with the fold.
        grouped = (
            qs.filter(metadata__has_key=tag_key)
            .annotate(grouping_field_value=KeyTextTransform(tag_key, "metadata"))
            .values("grouping_field_value")
            .annotate(
                prov_sum=Sum("provider_cost_micros"),
                billed_sum=Sum("billed_cost_micros"),
                cnt=Count("id"),
            )
            .order_by()
        )
        rows = [_row(g["grouping_field_value"], g["prov_sum"], g["billed_sum"], g["cnt"])
                for g in grouped]
        return sorted(rows, key=lambda r: -r["margin_micros"])

    valid = ("provider", "event_type", "task_type", "subtask_type", *SLOTS)
    if group_by not in valid:
        raise ValueError(f"group_by must be one of {valid}")
    grouped = (qs.exclude(**{group_by: ""}).values(group_by).annotate(
        prov_sum=Sum("provider_cost_micros"), billed_sum=Sum("billed_cost_micros"),
        cnt=Count("id")).order_by())
    rows = [_row(g[group_by], g["prov_sum"], g["billed_sum"], g["cnt"]) for g in grouped]
    return sorted(rows, key=lambda r: -r["margin_micros"])


def get_usage_event_effective_at(usage_event_id) -> datetime | None:
    """Get a usage event's effective_at timestamp. Returns datetime or None.

    Tolerates malformed (non-UUID) ids by returning None — the UUID is
    validated BEFORE the DB query so a legacy id (e.g. "evt-1" in old
    fixtures) can never raise DataError inside a caller's atomic block.
    """
    from apps.metering.usage.models import Posting

    try:
        uuid.UUID(str(usage_event_id))
    except (ValueError, TypeError):
        return None
    return Posting.objects.filter(id=usage_event_id).values_list(
        "effective_at", flat=True
    ).first()


def get_customer_ids_with_usage(tenant_id, period_start: date, period_end: date) -> list:
    """Distinct customer ids with ANY usage in [period_start, period_end).

    Existence-based: deliberately does NOT filter on billed_cost_micros
    (zero-billed usage still counts — budget reconcile and postpaid close
    both want every customer that emitted events). tenant_id may be a single
    tenant id or a list/tuple/set of tenant ids (one query either way).
    """
    from apps.metering.usage.models import Posting

    tenant_ids = tenant_id if isinstance(tenant_id, (list, tuple, set)) else [tenant_id]
    return list(Posting.objects.filter(
        tenant_id__in=list(tenant_ids),
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    ).values_list("customer_id", flat=True).distinct())


def get_billed_totals_by_customer(tenant_id, customer_ids, period_start: date,
                                  period_end: date) -> dict:
    """Sum(billed_cost_micros) per customer over [period_start, period_end).

    Returns {customer_id: total_billed_micros}; a customer with no events in
    the window is absent (a customer whose events all bill 0 IS present with
    0). SQL GROUP BY pushdown — the trailing .order_by() clears the model's
    default ordering so it cannot poison the GROUP BY.
    """
    from apps.metering.usage.models import Posting

    rows = (Posting.objects.filter(
        tenant_id=tenant_id, customer_id__in=list(customer_ids),
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    ).values("customer_id").annotate(total=Sum("billed_cost_micros")).order_by())
    return {r["customer_id"]: r["total"] or 0 for r in rows}


def get_customer_billed_breakdown(tenant_id, customer_id, period_start: date,
                                  period_end: date, group_by: str) -> list[tuple]:
    """Billed totals for ONE customer grouped by "tag:<key>" or the first slot.

    Returns UNSORTED, aggregated [(label, billed_micros), ...] pairs (the
    caller owns presentation order). Postpaid invoice-line label semantics:
    a missing key, an absent bag, a JSON-null or EMPTY-STRING value, and
    an empty slot value ALL collapse into "(other)" — unlike the analytics
    contract (get_usage_timeseries/get_dimensional_margin) where "" stays a
    distinct dimension. SQL GROUP BY pushdown; NULL and "" groups are merged
    into "(other)" post-query.

    ``group_by`` IS ONLY READ FOR ITS "tag:" PREFIX. Anything else means the
    first slot, whatever the stored configuration spells — which is why #276
    renaming that column changed no stored value and needed no rewrite of
    ``PostpaidUsageConfig``. A tenant configured against the old spelling still
    gets the first slot, exactly as before.
    """
    from apps.metering.usage.models import Posting

    qs = Posting.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    )
    if group_by.startswith("tag:"):
        # The key-driven invoice line labels are slice 7's surface, left where
        # #273 found them — only the column underneath moved, with the fold.
        rows = (qs.annotate(label=KeyTextTransform(group_by[4:], "metadata"))
                .values("label").annotate(total=Sum("billed_cost_micros")).order_by())
        raw_key = "label"
    else:  # the first slot
        rows = (qs.values("grouping_field_1")
                .annotate(total=Sum("billed_cost_micros")).order_by())
        raw_key = "grouping_field_1"
    merged: dict = {}
    for r in rows:
        label = r[raw_key] or "(other)"  # NULL and "" both collapse, then merge
        merged[label] = merged.get(label, 0) + (r["total"] or 0)
    return list(merged.items())


def list_backfill_dirty_periods(created_before: datetime | None = None) -> list[dict]:
    """Pending backfill markers (plain dicts, oldest first).

    Each: {"id", "tenant_id", "customer_id", "period_start" (date)}. Written by
    record_usage when an event backfills into a PRIOR calendar month; consumed
    by subscriptions' resnapshot_dirty_periods, which acks each marker via
    clear_backfill_dirty_period() AFTER its snapshot work succeeds.

    created_before: only markers created strictly before this aware datetime.
    The consumer passes now − its settle horizon so a marker is never acked
    while the backfill's accumulator write (outbox-dispatched, hours of retry
    backoff) may still be in flight — acking against a stale accumulator would
    freeze the prior-month snapshot wrong forever.
    """
    from apps.metering.usage.models import BackfillDirtyPeriod

    qs = BackfillDirtyPeriod.objects.order_by("created_at")
    if created_before is not None:
        qs = qs.filter(created_at__lt=created_before)
    return [
        {"id": r["id"], "tenant_id": r["tenant_id"],
         "customer_id": r["customer_id"], "period_start": r["period_start"]}
        for r in qs.values("id", "tenant_id", "customer_id", "period_start")
    ]


def clear_backfill_dirty_period(marker_id) -> None:
    """Ack (delete) one backfill marker by id. Idempotent.

    The deliberate WRITE half of the marker contract: the consumer deletes the
    marker only after its re-snapshot succeeded, so a crash retries it.
    """
    from apps.metering.usage.models import BackfillDirtyPeriod

    BackfillDirtyPeriod.objects.filter(id=marker_id).delete()


def iter_billable_usage_events(tenant_id, since: datetime, before: datetime,
                               basis: str = "effective") -> Iterator[dict]:
    """Iterate billable events (billed_cost_micros > 0) in [since, before).

    since/before are aware datetimes (NOT dates — no day-snapping here).
    basis="effective" windows on effective_at; basis="created" windows on
    created_at, so a consumer (e.g. drawdown repair) can flip its scan basis
    with a one-word change. Yields plain dicts:
    {"id", "billed_cost_micros", "customer_id", "billing_owner_id"}.
    Server-side cursor via .iterator() — safe for large windows.
    """
    from apps.metering.usage.models import Posting

    if basis not in ("effective", "created"):
        raise ValueError("basis must be 'effective' or 'created'")
    field = "created_at" if basis == "created" else "effective_at"
    return Posting.objects.filter(
        tenant_id=tenant_id, billed_cost_micros__gt=0,
        **{f"{field}__gte": since, f"{field}__lt": before},
    ).values("id", "billed_cost_micros", "customer_id", "billing_owner_id").iterator()
