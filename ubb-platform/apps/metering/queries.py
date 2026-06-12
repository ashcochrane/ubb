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
"""
import uuid
from datetime import date, datetime
from typing import Iterator, TypedDict

from django.db.models import Sum, Count
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import TruncDate

from core.time_windows import utc_day_start, utc_next_day_start


class PeriodTotals(TypedDict):
    total_cost_micros: int
    event_count: int


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
    from apps.metering.usage.models import UsageEvent

    if basis not in ("effective", "arrival"):
        raise ValueError("basis must be 'effective' or 'arrival'")
    field = "created_at" if basis == "arrival" else "effective_at"
    totals = UsageEvent.objects.filter(
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
    from apps.metering.usage.models import UsageEvent

    qs = UsageEvent.objects.filter(id=usage_event_id)
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
    from apps.metering.usage.models import UsageEvent

    qs = UsageEvent.objects.filter(tenant_id=tenant_id)

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
    from apps.metering.usage.models import UsageEvent

    events = UsageEvent.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
        effective_at__gte=period_start,
        effective_at__lt=period_end,
    ).values("billed_cost_micros", "provider_cost_micros")

    return list(events)


def get_customer_cost_totals(tenant_id, customer_id, start_date, end_date) -> dict:
    """Provider + billed cost totals for one customer over [start, end)."""
    from apps.metering.usage.models import UsageEvent
    agg = UsageEvent.objects.filter(
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


def get_usage_timeseries(tenant_id, *, granularity="day", customer_id=None,
                         group_by=None, start_date=None, end_date=None) -> list[dict]:
    """Time-series spend rollup: daily or hourly COGS per tenant, optionally per customer/dimension.

    Returns list of dicts with bucket (ISO string), provider_cost_micros, billed_cost_micros,
    markup_micros, event_count, and optionally dimension (when group_by is set).
    """
    from django.db.models.functions import TruncHour
    from apps.metering.usage.models import UsageEvent

    trunc = TruncHour if granularity == "hour" else TruncDate
    qs = UsageEvent.objects.filter(tenant_id=tenant_id)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        qs = qs.filter(effective_at__lt=utc_day_start(end_date))

    valid_group_by = ("provider", "event_type", "product_id", "service_id", "agent_id")
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
    from apps.metering.usage.models import UsageEvent
    rows = (UsageEvent.objects.filter(
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

    group_by in {"provider", "event_type", "product_id"}; OR tag_key for tags->>key.
    Each row: {dimension, provider_cost_micros, billed_cost_micros, margin_micros, event_count}.
    """
    from apps.metering.usage.models import UsageEvent
    qs = UsageEvent.objects.filter(tenant_id=tenant_id)
    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        qs = qs.filter(effective_at__lt=utc_day_start(end_date))

    def _row(dim, provider, billed, count):
        return {"dimension": dim, "provider_cost_micros": provider or 0,
                "billed_cost_micros": billed or 0,
                "margin_micros": (billed or 0) - (provider or 0), "event_count": count}

    if tag_key:
        grouped = (
            qs.filter(tags__has_key=tag_key)
            .annotate(dimension=KeyTextTransform(tag_key, "tags"))
            .values("dimension")
            .annotate(
                prov_sum=Sum("provider_cost_micros"),
                billed_sum=Sum("billed_cost_micros"),
                cnt=Count("id"),
            )
            .order_by()
        )
        rows = [_row(g["dimension"], g["prov_sum"], g["billed_sum"], g["cnt"]) for g in grouped]
        return sorted(rows, key=lambda r: -r["margin_micros"])

    if group_by not in ("provider", "event_type", "product_id"):
        raise ValueError("group_by must be provider, event_type, or product_id")
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
    from apps.metering.usage.models import UsageEvent

    try:
        uuid.UUID(str(usage_event_id))
    except (ValueError, TypeError):
        return None
    return UsageEvent.objects.filter(id=usage_event_id).values_list(
        "effective_at", flat=True
    ).first()


def get_customer_ids_with_usage(tenant_id, period_start: date, period_end: date) -> list:
    """Distinct customer ids with ANY usage in [period_start, period_end).

    Existence-based: deliberately does NOT filter on billed_cost_micros
    (zero-billed usage still counts — budget reconcile and postpaid close
    both want every customer that emitted events). tenant_id may be a single
    tenant id or a list/tuple/set of tenant ids (one query either way).
    """
    from apps.metering.usage.models import UsageEvent

    tenant_ids = tenant_id if isinstance(tenant_id, (list, tuple, set)) else [tenant_id]
    return list(UsageEvent.objects.filter(
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
    from apps.metering.usage.models import UsageEvent

    rows = (UsageEvent.objects.filter(
        tenant_id=tenant_id, customer_id__in=list(customer_ids),
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    ).values("customer_id").annotate(total=Sum("billed_cost_micros")).order_by())
    return {r["customer_id"]: r["total"] or 0 for r in rows}


def get_customer_billed_breakdown(tenant_id, customer_id, period_start: date,
                                  period_end: date, group_by: str) -> list[tuple]:
    """Billed totals for ONE customer grouped by "tag:<key>" or "product_id".

    Returns UNSORTED, aggregated [(label, billed_micros), ...] pairs (the
    caller owns presentation order). Postpaid invoice-line label semantics:
    a missing tag key, NULL tags, a JSON-null or EMPTY-STRING tag value, and
    an empty product_id ALL collapse into "(other)" — unlike the analytics
    contract (get_usage_timeseries/get_dimensional_margin) where "" stays a
    distinct dimension. SQL GROUP BY pushdown; NULL and "" groups are merged
    into "(other)" post-query.
    """
    from apps.metering.usage.models import UsageEvent

    qs = UsageEvent.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    )
    if group_by.startswith("tag:"):
        rows = (qs.annotate(label=KeyTextTransform(group_by[4:], "tags"))
                .values("label").annotate(total=Sum("billed_cost_micros")).order_by())
        raw_key = "label"
    else:  # "product_id"
        rows = (qs.values("product_id")
                .annotate(total=Sum("billed_cost_micros")).order_by())
        raw_key = "product_id"
    merged: dict = {}
    for r in rows:
        label = r[raw_key] or "(other)"  # NULL and "" both collapse, then merge
        merged[label] = merged.get(label, 0) + (r["total"] or 0)
    return list(merged.items())


def list_backfill_dirty_periods() -> list[dict]:
    """All pending backfill markers (plain dicts, oldest first).

    Each: {"id", "tenant_id", "customer_id", "period_start" (date)}. Written by
    record_usage when an event backfills into a PRIOR calendar month; consumed
    by subscriptions' resnapshot_dirty_periods, which acks each marker via
    clear_backfill_dirty_period() AFTER its snapshot work succeeds.
    """
    from apps.metering.usage.models import BackfillDirtyPeriod

    return [
        {"id": r["id"], "tenant_id": r["tenant_id"],
         "customer_id": r["customer_id"], "period_start": r["period_start"]}
        for r in BackfillDirtyPeriod.objects.order_by("created_at").values(
            "id", "tenant_id", "customer_id", "period_start")
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
    from apps.metering.usage.models import UsageEvent

    if basis not in ("effective", "created"):
        raise ValueError("basis must be 'effective' or 'created'")
    field = "created_at" if basis == "created" else "effective_at"
    return UsageEvent.objects.filter(
        tenant_id=tenant_id, billed_cost_micros__gt=0,
        **{f"{field}__gte": since, f"{field}__lt": before},
    ).values("id", "billed_cost_micros", "customer_id", "billing_owner_id").iterator()
