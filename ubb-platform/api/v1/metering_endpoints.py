import logging
import re
from datetime import date, datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Sum, Count, Q
from django.db.models.fields.json import KeyTextTransform
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Query

from core.auth import ApiKeyAuth, ProductAccess
from core.time_windows import utc_day_start, utc_next_day_start
from django.utils import timezone

from api.v1.schemas import (
    RecordUsageRequest, RecordUsageResponse,
    UsageBatchRequest, UsageBatchResponse,
    PaginatedUsageResponse,
    UsageEventDetailOut,
    TenantMarkupIn, TenantMarkupOut,
    CloseRunResponse,
    UsageAnalyticsResponse,
    UsageTimeseriesResponse,
    RateIn, RateOut, BookIn, BookOut, RateChangeIn, PublishIn, AssignIn,
)
from apps.metering.pricing.models import (
    Rate, RateCard, RateCardAssignment,
    CARD_TYPE_CHOICES, PRICING_MODEL_CHOICES, validate_tiers,
)
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent

logger = logging.getLogger(__name__)

metering_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_metering_v1")

_product_check = ProductAccess("metering")


@metering_api.post("/usage", response={200: RecordUsageResponse})
def record_usage(request, payload: RecordUsageRequest):
    _product_check(request)

    from apps.platform.runs.services import HardStopExceeded, RunNotActive, RunService
    from apps.metering.pricing.services.pricing_service import PricingError
    from apps.metering.usage.services.usage_service import EffectiveAtError

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    if payload.run_id is not None:
        get_object_or_404(Run, id=payload.run_id, tenant=request.auth.tenant, customer=customer)
    try:
        result = UsageService.record_usage(
            tenant=request.auth.tenant,
            customer=customer,
            request_id=payload.request_id,
            idempotency_key=payload.idempotency_key,
            provider_cost_micros=payload.provider_cost_micros,
            billed_cost_micros=payload.billed_cost_micros,
            units=payload.units,
            currency=payload.currency,
            product_id=payload.product_id,
            metadata=payload.metadata,
            event_type=payload.event_type,
            provider=payload.provider,
            tags=payload.tags,
            run_id=payload.run_id,
            usage_metrics=payload.usage_metrics,
            effective_at=payload.effective_at,
        )
    except HardStopExceeded as e:
        from django.db import transaction
        # A per-task cost-cap breach (P4) can fire with no run — guard kill_run.
        if payload.run_id is not None:
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import RunLimitExceeded
            with transaction.atomic():
                killed = RunService.kill_run(payload.run_id, reason=e.reason,
                                             tenant_id=request.auth.tenant.id, customer_id=customer.id)
                # P6 fan-out: notify sibling/idle workers of THIS run (the
                # posting worker already gets the 429). scope="run".
                write_event(RunLimitExceeded(
                    tenant_id=str(request.auth.tenant.id), customer_id=str(customer.id),
                    billing_owner_id=str(killed.billing_owner_id or ""),
                    run_id=str(killed.id), external_run_id=killed.external_run_id,
                    task_id=killed.task_id, reason=e.reason, scope="run",
                    total_cost_micros=e.total_cost_micros,
                    limit_micros=killed.cost_limit_micros or 0))
        return metering_api.create_response(request, {
            "error": "hard_stop_exceeded",
            "reason": e.reason,
            "run_id": e.run_id,
            "total_cost_micros": e.total_cost_micros,
            "hard_stop": True,
        }, status=429)
    except RunNotActive as e:
        return metering_api.create_response(request, {
            "error": "run_not_active",
            "run_id": e.run_id,
            "status": e.status,
        }, status=409)
    except PricingError as e:
        return metering_api.create_response(
            request, {"error": "pricing_error", "detail": str(e)}, status=422)
    except EffectiveAtError as e:
        # MUST precede the ValueError branch below (EffectiveAtError IS a
        # ValueError) so the typed code survives to the response body.
        return metering_api.create_response(
            request, {"error": e.code, "detail": str(e)}, status=422)
    except ValueError as e:
        from ninja.errors import HttpError
        raise HttpError(422, str(e))
    provenance = result.get("pricing_provenance") or {}
    result["uncosted_metrics"] = provenance.get("uncosted_metrics", [])
    return result


def _record_batch_item(request, tenant, item, customers, run_exists):
    """One batch item == one independent POST /usage, error mapping included.

    Mirrors the single endpoint's except branches byte-for-byte as per-item
    result dicts ({"ok": false, "error": <same code>, ...same fields...}); a
    success mirrors the single-call success body plus {"ok": true}. 404s
    become per-item {"error": "not_found"}; the generic ValueError branch
    becomes {"error": "validation_error"}.
    """
    from django.db import transaction
    from apps.platform.runs.services import HardStopExceeded, RunNotActive, RunService
    from apps.metering.pricing.services.pricing_service import PricingError
    from apps.metering.usage.services.usage_service import EffectiveAtError

    cid = str(item.customer_id)
    if cid not in customers:
        customers[cid] = Customer.objects.filter(id=item.customer_id, tenant=tenant).first()
    customer = customers[cid]
    if customer is None:
        return {"ok": False, "error": "not_found", "detail": "Customer not found"}
    if item.run_id is not None:
        run_key = (cid, str(item.run_id))
        if run_key not in run_exists:
            run_exists[run_key] = Run.objects.filter(
                id=item.run_id, tenant=tenant, customer=customer).exists()
        if not run_exists[run_key]:
            return {"ok": False, "error": "not_found", "detail": "Run not found"}
    try:
        result = UsageService.record_usage(
            tenant=tenant,
            customer=customer,
            request_id=item.request_id,
            idempotency_key=item.idempotency_key,
            provider_cost_micros=item.provider_cost_micros,
            billed_cost_micros=item.billed_cost_micros,
            units=item.units,
            currency=item.currency,
            product_id=item.product_id,
            metadata=item.metadata,
            event_type=item.event_type,
            provider=item.provider,
            tags=item.tags,
            run_id=item.run_id,
            usage_metrics=item.usage_metrics,
            effective_at=item.effective_at,
        )
    except HardStopExceeded as e:
        # Same side effect as the single endpoint: kill the run, then the
        # batch CONTINUES — later items on this run get run_not_active,
        # identical to firing the same items as sequential singles. A per-task
        # cost-cap breach (P4) can fire with no run — guard kill_run.
        try:
            if item.run_id is not None:
                from apps.platform.events.outbox import write_event
                from apps.platform.events.schemas import RunLimitExceeded
                with transaction.atomic():
                    killed = RunService.kill_run(item.run_id, reason=e.reason,
                                                 tenant_id=tenant.id, customer_id=customer.id)
                    write_event(RunLimitExceeded(  # P6 fan-out (scope="run")
                        tenant_id=str(tenant.id), customer_id=str(customer.id),
                        billing_owner_id=str(killed.billing_owner_id or ""),
                        run_id=str(killed.id), external_run_id=killed.external_run_id,
                        task_id=killed.task_id, reason=e.reason, scope="run",
                        total_cost_micros=e.total_cost_micros,
                        limit_micros=killed.cost_limit_micros or 0))
        except Exception:
            # A kill failure must never 500 the whole batch. NOTE: the run is
            # left ACTIVE, so later items on it may SUCCEED instead of getting
            # run_not_active — the loud log is the operator signal.
            logger.exception("run.kill_failed", extra={"data": {
                "run_id": str(item.run_id), "tenant_id": str(tenant.id),
                "customer_id": str(customer.id), "reason": e.reason}})
        return {"ok": False, "error": "hard_stop_exceeded", "reason": e.reason,
                "run_id": e.run_id, "total_cost_micros": e.total_cost_micros,
                "hard_stop": True}
    except RunNotActive as e:
        return {"ok": False, "error": "run_not_active",
                "run_id": e.run_id, "status": e.status}
    except PricingError as e:
        return {"ok": False, "error": "pricing_error", "detail": str(e)}
    except EffectiveAtError as e:
        return {"ok": False, "error": e.code, "detail": str(e)}
    except ValueError as e:
        return {"ok": False, "error": "validation_error", "detail": str(e)}
    provenance = result.get("pricing_provenance") or {}
    result["uncosted_metrics"] = provenance.get("uncosted_metrics", [])
    return {"ok": True, **result}


@metering_api.post("/usage/batch", response={200: UsageBatchResponse})
def record_usage_batch(request, payload: UsageBatchRequest):
    """Batch ingestion: 1..100 INDEPENDENT items (>100 or 0 → 422).

    Each item runs the same per-item record_usage in its own atomic commit —
    deliberately NOT one mega-transaction, which would hold Run/counter locks
    for the whole batch, delay outbox dispatch, and diverge from the semantics
    of N sequential singles. Always HTTP 200 with positionally-aligned
    results[] + succeeded/failed counts; per-item idempotency makes a
    whole-batch replay return the original event ids with zero new rows, and
    a duplicate idempotency_key WITHIN one batch resolves to the first item's
    event id (the first item commits before the second runs).
    """
    _product_check(request)
    tenant = request.auth.tenant
    customers: dict = {}
    run_exists: dict = {}
    results = [_record_batch_item(request, tenant, item, customers, run_exists)
               for item in payload.events]
    succeeded = sum(1 for r in results if r.get("ok"))
    return {"results": results, "succeeded": succeeded,
            "failed": len(results) - succeeded}


@metering_api.get("/customers/{customer_id}/usage", response=PaginatedUsageResponse)
def get_usage(request, customer_id: str, cursor: str = None, limit: int = 50,
              tag_key: str = None, tag_value: str = None):
    _product_check(request)

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)  # Clamp between 1 and 100

    qs = customer.usage_events.all().order_by("-effective_at", "-id")

    if tag_key and tag_value:
        qs = qs.filter(tags__contains={tag_key: tag_value})

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor)
        except ValueError:
            from ninja.errors import HttpError
            raise HttpError(400, "Invalid cursor")

    events = list(qs[:limit + 1])  # Fetch one extra to check has_more
    has_more = len(events) > limit
    events = events[:limit]

    next_cursor = None
    if has_more and events:
        last = events[-1]
        next_cursor = encode_cursor(last.effective_at, last.id)

    return {
        "data": [
            {
                "id": e.id,
                "request_id": e.request_id,
                "event_type": e.event_type,
                "provider": e.provider,
                "provider_cost_micros": e.provider_cost_micros,
                "billed_cost_micros": e.billed_cost_micros,
                "units": e.units,
                "metadata": e.metadata,
                "effective_at": e.effective_at.isoformat(),
            }
            for e in events
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@metering_api.get("/usage/{event_id}", response={200: UsageEventDetailOut, 404: dict})
def get_usage_event(request, event_id: UUID):
    """Fetch one usage event's full pricing receipt (audit / dispute lookup).

    Returns every priced field plus pricing_provenance — the recorded
    "why this amount" (engine version, price source, per-metric card, and
    tier-by-tier breakdown). The usage list omits provenance to stay lean;
    this is where it is read back. Tenant-scoped; 404 for an unknown or
    foreign event id."""
    _product_check(request)
    from apps.metering.usage.models import UsageEvent

    e = get_object_or_404(UsageEvent, id=event_id, tenant=request.auth.tenant)
    return 200, {
        "id": e.id,
        "request_id": e.request_id,
        "idempotency_key": e.idempotency_key,
        "event_type": e.event_type,
        "provider": e.provider,
        "product_id": e.product_id,
        "service_id": e.service_id,
        "agent_id": e.agent_id,
        "units": e.units,
        "currency": e.currency,
        "provider_cost_micros": e.provider_cost_micros,
        "billed_cost_micros": e.billed_cost_micros,
        "usage_metrics": e.usage_metrics or {},
        "pricing_provenance": e.pricing_provenance or {},
        "tags": e.tags,
        "metadata": e.metadata,
        "run_id": str(e.run_id) if e.run_id else None,
        "effective_at": e.effective_at.isoformat(),
        "created_at": e.created_at.isoformat(),
    }


# --- Run lifecycle ---


@metering_api.post("/runs/{run_id}/close", response=CloseRunResponse)
def close_run(request, run_id: UUID):
    _product_check(request)
    from apps.platform.runs.services import RunService
    from apps.platform.runs.models import Run

    run = get_object_or_404(Run, id=run_id, tenant=request.auth.tenant)
    completed = RunService.complete_run(run.id)
    return {
        "run_id": str(completed.id),
        "status": completed.status,
        "total_cost_micros": completed.total_cost_micros,
        "event_count": completed.event_count,
    }


# --- Pricing Markup ---


@metering_api.get("/pricing/markup", response=TenantMarkupOut)
def get_tenant_markup(request):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markup = TenantMarkup.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if markup is None:
        return {"markup_percentage_micros": 0, "fixed_uplift_micros": 0}
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_api.put("/pricing/markup", response=TenantMarkupOut)
def upsert_tenant_markup(request, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markup, _ = TenantMarkup.objects.update_or_create(
        tenant=request.auth.tenant,
        customer=None,
        defaults={
            "markup_percentage_micros": payload.markup_percentage_micros,
            "fixed_uplift_micros": payload.fixed_uplift_micros,
        },
    )
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_api.get("/pricing/customers/{customer_id}/markup", response=TenantMarkupOut)
def get_customer_markup(request, customer_id: UUID):
    _product_check(request)
    from apps.metering.pricing.services.markup_service import MarkupService

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    markup = MarkupService.resolve(tenant=request.auth.tenant, customer=customer)
    if markup is None:
        return {"markup_percentage_micros": 0, "fixed_uplift_micros": 0}
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_api.put("/pricing/customers/{customer_id}/markup", response=TenantMarkupOut)
def upsert_customer_markup(request, customer_id: UUID, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    markup, _ = TenantMarkup.objects.update_or_create(
        tenant=request.auth.tenant,
        customer=customer,
        defaults={
            "markup_percentage_micros": payload.markup_percentage_micros,
            "fixed_uplift_micros": payload.fixed_uplift_micros,
        },
    )
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_api.delete("/pricing/customers/{customer_id}/markup")
def delete_customer_markup(request, customer_id: UUID):
    """Remove a customer's markup override so they revert to inheriting the
    tenant default. This is NOT the same as PUT-ing 0/0 — a 0/0 row still
    resolves as the customer's markup and SHADOWS the tenant default, pinning
    the customer at cost. Idempotent: 'no_override' when none existed; a bad
    customer id is a 404."""
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    deleted, _ = TenantMarkup.objects.filter(
        tenant=request.auth.tenant, customer=customer).delete()
    return {"status": "deleted" if deleted else "no_override"}


# --- Analytics ---


_ANALYTICS_ALLOWED_COLS = {"provider", "event_type", "product_id", "customer", "service_id", "agent_id"}


@metering_api.get("/analytics/usage", response={200: UsageAnalyticsResponse, 422: dict})
def usage_analytics(request, start_date: date = None, end_date: date = None,
                    customer_id: str = None, tag_key: str = None,
                    dimensions: list[str] = Query(None)):
    """Usage analytics with markup margin and customer/product/tag breakdowns."""
    _product_check(request)
    tenant = request.auth.tenant
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))
    if customer_id:
        qs = qs.filter(customer_id=customer_id)

    totals = qs.aggregate(
        total_events=Count("id"),
        total_billed_cost_micros=Sum("billed_cost_micros"),
        total_provider_cost_micros=Sum("provider_cost_micros"),
    )
    total_billed = totals["total_billed_cost_micros"] or 0
    total_provider = totals["total_provider_cost_micros"] or 0

    by_provider = list(
        qs.exclude(provider="").values("provider").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )
    by_event_type = list(
        qs.exclude(event_type="").values("event_type").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )
    by_customer = list(
        qs.values("customer__external_id").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )
    by_product = list(
        qs.exclude(product_id="").values("product_id").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )

    by_tag = []
    if tag_key:
        by_tag = list(
            qs.filter(tags__has_key=tag_key)
            .annotate(tag_value=KeyTextTransform(tag_key, "tags"))
            .values("tag_value")
            .annotate(
                event_count=Count("id"),
                total_cost_micros=Sum("billed_cost_micros"),
                total_provider_cost_micros=Sum("provider_cost_micros"),
            )
            .order_by("-total_cost_micros")
        )

    breakdowns: dict = {}
    if dimensions:
        if len(dimensions) > 6:
            return 422, {"error": "at most 6 dimensions"}
        for dim in dimensions:
            if dim.startswith("tag:"):
                key = dim[4:]
                if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key):
                    return 422, {"error": f"invalid tag dimension {dim}"}
                # Events that have the key (non-NULL dimension value).
                rows_with_key = list(
                    qs.filter(tags__has_key=key)
                    .annotate(dimension=KeyTextTransform(key, "tags"))
                    .values("dimension")
                    .annotate(
                        event_count=Count("id"),
                        total_provider_cost_micros=Sum("provider_cost_micros"),
                        total_billed_cost_micros=Sum("billed_cost_micros"),
                    )
                    .order_by("-total_billed_cost_micros")
                )
                # Events that are MISSING the key -> bucket as "(unattributed)".
                unattr_qs = qs.exclude(tags__has_key=key)
                unattr_agg = unattr_qs.aggregate(
                    event_count=Count("id"),
                    total_provider_cost_micros=Sum("provider_cost_micros"),
                    total_billed_cost_micros=Sum("billed_cost_micros"),
                )
                if (unattr_agg["event_count"] or 0) > 0:
                    rows_with_key.append({
                        "dimension": "(unattributed)",
                        "event_count": unattr_agg["event_count"] or 0,
                        "total_provider_cost_micros": unattr_agg["total_provider_cost_micros"] or 0,
                        "total_billed_cost_micros": unattr_agg["total_billed_cost_micros"] or 0,
                    })
                rows = sorted(rows_with_key, key=lambda r: -(r["total_billed_cost_micros"] or 0))
            elif dim in _ANALYTICS_ALLOWED_COLS:
                col = "customer__external_id" if dim == "customer" else dim
                # Run over the FULL qs (no exclusion) so every event is counted.
                # customer always has an external_id so no "(unattributed)" needed there.
                rows = list(
                    qs.values(col)
                    .annotate(
                        event_count=Count("id"),
                        total_provider_cost_micros=Sum("provider_cost_micros"),
                        total_billed_cost_micros=Sum("billed_cost_micros"),
                    )
                    .order_by("-total_billed_cost_micros")
                )
                for r in rows:
                    raw_val = r.pop(col)
                    # Map empty string or None to the sentinel for non-customer cols
                    if dim != "customer" and not raw_val:
                        raw_val = "(unattributed)"
                    r["dimension"] = raw_val
            else:
                return 422, {"error": f"unknown dimension {dim}"}
            breakdowns[dim] = rows

    return 200, {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": total_billed,
        "total_provider_cost_micros": total_provider,
        "usage_markup_margin_micros": total_billed - total_provider,
        "by_provider": by_provider,
        "by_event_type": by_event_type,
        "by_customer": by_customer,
        "by_product": by_product,
        "by_tag": by_tag,
        "breakdowns": breakdowns,
    }


@metering_api.get("/analytics/usage/timeseries", response={200: UsageTimeseriesResponse, 422: dict})
def usage_timeseries(request, granularity: str = "day", start_date: date = None, end_date: date = None,
                     customer_id: str = None, group_by: str = None):
    """Time-series spend rollup: daily or hourly COGS per tenant/customer.

    start_date and end_date are both INCLUSIVE calendar dates, matching the
    /analytics/usage rollup so the same inputs cover the same window on both.
    """
    _product_check(request)
    if granularity not in ("hour", "day"):
        return 422, {"error": "granularity must be hour or day"}
    if group_by is not None and group_by not in ("provider", "event_type", "product_id", "service_id", "agent_id"):
        return 422, {"error": "invalid group_by"}
    # guardrail: cap hourly windows to ~92 days
    if granularity == "hour" and start_date and end_date and (end_date - start_date).days > 92:
        return 422, {"error": "hourly window too large (max 92 days)"}
    from apps.metering.queries import get_usage_timeseries
    series = get_usage_timeseries(request.auth.tenant.id, granularity=granularity,
        customer_id=customer_id, group_by=group_by, start_date=start_date, end_date=end_date)
    return 200, {"granularity": granularity, "group_by": group_by or "", "series": series}


# --- Rate Cards ---

_billing_check = ProductAccess("billing")


def _book_to_out(b):
    return {
        "id": str(b.id),
        "card_type": b.card_type,
        "provider_key": b.provider_key,
        "key": b.key,
        "name": b.name,
        "currency": b.currency,
        "version": b.version,
        "is_default": b.is_default,
    }


def _rate_to_out(r):
    return {
        "id": str(r.id),
        "rate_card_id": str(r.rate_card_id) if r.rate_card_id else None,
        "lineage_id": str(r.lineage_id),
        "card_type": r.card_type,
        "metric_name": r.metric_name,
        "provider": r.provider,
        "event_type": r.event_type,
        "dimensions": r.dimensions,
        "pricing_model": r.pricing_model,
        "rate_per_unit_micros": r.rate_per_unit_micros,
        "unit_quantity": r.unit_quantity,
        "fixed_micros": r.fixed_micros,
        "tiers": r.tiers,
        "currency": r.currency,
        "product_id": r.product_id,
        "valid_from": r.valid_from.isoformat(),
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
    }


def _gate_card_type(request, card_type):
    _product_check(request)
    if card_type == "price":
        _billing_check(request)


def _resolve_card_currency(tenant, raw_currency):
    """CUR-1 rate-card currency pin: cards live in the tenant's currency.

    Omitted/empty currency defaults to the tenant's default_currency; an
    explicit value must match it case-insensitively. Returns the normalized
    lowercase currency, or raises ValueError (mapped to 422 by callers).
    """
    tenant_currency = (tenant.default_currency or "usd").lower()
    if not raw_currency:
        return tenant_currency
    card_currency = str(raw_currency).strip().lower()
    if card_currency != tenant_currency:
        raise ValueError(
            f"rate-card currency {card_currency!r} does not match tenant "
            f"currency {tenant_currency!r} (per-tenant single currency; "
            "multi-currency/FX is not supported)")
    return card_currency


@metering_api.get("/pricing/rate-cards", response=list[BookOut])
def list_books(request, card_type: str = None):
    """List the tenant's rate-card BOOKS (containers). Rates live under a book
    and are read via GET /pricing/rate-cards/{book_id}/rates."""
    _product_check(request)
    qs = RateCard.objects.filter(tenant=request.auth.tenant)
    if card_type:
        qs = qs.filter(card_type=card_type)
    return [_book_to_out(b) for b in qs.order_by(
        "card_type", "provider_key", "key", "id")]


@metering_api.post("/pricing/rate-cards", response={200: BookOut, 422: dict})
def create_book(request, payload: BookIn):
    """Create a rate-card BOOK. Rates are added under it (so every API-created
    rate is book-scoped and therefore resolvable)."""
    _gate_card_type(request, payload.card_type)
    valid_types = {c[0] for c in CARD_TYPE_CHOICES}
    if payload.card_type not in valid_types:
        return 422, {"error": f"card_type must be one of {sorted(valid_types)}"}
    try:
        currency = _resolve_card_currency(request.auth.tenant, payload.currency)
    except ValueError as e:
        return 422, {"error": str(e)}
    try:
        book = RateCard.objects.create(
            tenant=request.auth.tenant, card_type=payload.card_type,
            provider_key=payload.provider_key, key=payload.key, name=payload.name,
            currency=currency, is_default=payload.is_default)
    except IntegrityError as e:
        return 422, {"error": f"rate-card book conflict: {e}"}
    return 200, _book_to_out(book)


@metering_api.get("/pricing/rate-cards/{book_id}/rates", response={200: list[RateOut], 404: dict})
def list_book_rates(request, book_id: UUID, include_history: bool = False,
                    as_of: datetime = None):
    """List the rates in a book. Active-only by default; ``include_history``
    returns every version (superseded rows carry a ``valid_to``), and ``as_of``
    returns the version active at that instant (point-in-time)."""
    _product_check(request)
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    qs = Rate.objects.filter(tenant=request.auth.tenant, rate_card=book)
    if as_of is not None:
        qs = qs.filter(valid_from__lte=as_of).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
    elif not include_history:
        qs = qs.filter(valid_to__isnull=True)
    return 200, [_rate_to_out(r) for r in qs.order_by(
        "provider", "event_type", "metric_name", "-valid_from", "id")]


@metering_api.post("/pricing/rate-cards/{book_id}/rates", response={200: RateOut, 422: dict})
def add_rate(request, book_id: UUID, payload: RateIn):
    """Add a rate to a book. card_type and currency are inherited from the book
    (single source of truth); tier/enum validation mirrors the old flat create."""
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    if book.is_default and payload.provider != book.provider_key:
        return 422, {"error": (f"rate provider {payload.provider!r} must match the "
                               f"default book's provider {book.provider_key!r}")}
    valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
    if payload.pricing_model not in valid_models:
        return 422, {"error": f"pricing_model must be one of {sorted(valid_models)}"}
    try:
        validate_tiers(book.card_type, payload.pricing_model, payload.tiers)
    except ValueError as e:
        return 422, {"error": str(e)}
    try:
        rate = Rate.objects.create(
            tenant=request.auth.tenant, rate_card=book, card_type=book.card_type,
            metric_name=payload.metric_name, provider=payload.provider,
            event_type=payload.event_type, dimensions=payload.dimensions,
            pricing_model=payload.pricing_model,
            rate_per_unit_micros=payload.rate_per_unit_micros,
            unit_quantity=payload.unit_quantity, fixed_micros=payload.fixed_micros,
            tiers=payload.tiers, currency=book.currency, product_id=payload.product_id,
            book_version_from=book.version)
    except IntegrityError as e:
        return 422, {"error": f"rate conflict: {e}"}
    return 200, _rate_to_out(rate)


@metering_api.post("/pricing/rate-cards/{book_id}/publish", response={200: BookOut, 422: dict})
def publish_book(request, book_id: UUID, payload: PublishIn):
    """Atomically reprice a set of the book's rates: each change supersedes the
    matching active rate (same lineage, valid_to stamped) and opens a new
    version; the book version bumps once. All-or-nothing."""
    from apps.metering.pricing.services.book_service import BookService

    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    try:
        BookService.publish(book, [c.dict(exclude_none=True) for c in payload.changes])
    except ValueError as e:
        return 422, {"error": str(e)}
    book.refresh_from_db()
    return 200, _book_to_out(book)


@metering_api.post("/pricing/customers/{customer_id}/rate-card", response={200: dict, 422: dict})
def assign_book(request, customer_id: UUID, payload: AssignIn):
    """Assign a PRICE book to a customer (one per customer per currency).
    Resolution consults the assigned book before the per-provider default."""
    _billing_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    book = get_object_or_404(RateCard, id=payload.rate_card_id,
                             tenant=request.auth.tenant, card_type="price")
    RateCardAssignment.objects.update_or_create(
        tenant=request.auth.tenant, customer=customer, currency=book.currency,
        defaults={"rate_card": book})
    return 200, {"assigned": str(book.id)}


@metering_api.delete("/pricing/rate-cards/{card_id}")
def delete_rate_card(request, card_id: UUID):
    _product_check(request)
    card = get_object_or_404(Rate, id=card_id, tenant=request.auth.tenant, valid_to__isnull=True)
    card.valid_to = timezone.now()
    card.save(update_fields=["valid_to", "updated_at"])
    return {"status": "deleted"}
