from datetime import date
from uuid import UUID

from django.db.models import Sum, Count
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI

from core.auth import ApiKeyAuth, ProductAccess
from api.v1.schemas import (
    RecordUsageRequest, RecordUsageResponse,
    PaginatedUsageResponse,
    ProviderRateIn, ProviderRateOut,
    TenantMarkupIn, TenantMarkupOut,
    CloseRunResponse,
    UsageAnalyticsResponse,
)
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent

metering_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_metering_v1")

_product_check = ProductAccess("metering")


@metering_api.post("/usage", response={200: RecordUsageResponse})
def record_usage(request, payload: RecordUsageRequest):
    _product_check(request)

    from apps.metering.pricing.services.pricing_service import PricingError
    from apps.platform.runs.services import HardStopExceeded, RunNotActive, RunService

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    try:
        result = UsageService.record_usage(
            tenant=request.auth.tenant,
            customer=customer,
            request_id=payload.request_id,
            idempotency_key=payload.idempotency_key,
            cost_micros=payload.cost_micros,
            metadata=payload.metadata,
            event_type=payload.event_type,
            provider=payload.provider,
            usage_metrics=payload.usage_metrics,
            properties=payload.properties,
            group_keys=payload.group_keys,
            run_id=payload.run_id,
        )
    except HardStopExceeded as e:
        from django.db import transaction
        with transaction.atomic():
            RunService.kill_run(payload.run_id, reason=e.reason)
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
        from ninja.errors import HttpError
        raise HttpError(422, str(e))
    except ValueError as e:
        from ninja.errors import HttpError
        raise HttpError(422, str(e))
    return result


@metering_api.get("/customers/{customer_id}/usage", response=PaginatedUsageResponse)
def get_usage(request, customer_id: str, cursor: str = None, limit: int = 50,
              group_key: str = None, group_value: str = None):
    _product_check(request)

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)  # Clamp between 1 and 100

    qs = customer.usage_events.all().order_by("-effective_at", "-id")

    if group_key and group_value:
        qs = qs.filter(group_keys__contains={group_key: group_value})

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
                "cost_micros": e.cost_micros,
                "event_type": e.event_type,
                "provider": e.provider,
                "provider_cost_micros": e.provider_cost_micros,
                "billed_cost_micros": e.billed_cost_micros,
                "metadata": e.metadata,
                "effective_at": e.effective_at.isoformat(),
            }
            for e in events
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
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


# --- Pricing Rates CRUD ---


def _rate_to_out(rate):
    return {
        "id": rate.id,
        "provider": rate.provider,
        "event_type": rate.event_type,
        "metric_name": rate.metric_name,
        "dimensions": rate.dimensions,
        "cost_per_unit_micros": rate.cost_per_unit_micros,
        "unit_quantity": rate.unit_quantity,
        "currency": rate.currency,
        "valid_from": rate.valid_from.isoformat(),
        "valid_to": rate.valid_to.isoformat() if rate.valid_to else None,
    }


@metering_api.get("/pricing/rates", response=list[ProviderRateOut])
def list_rates(request):
    _product_check(request)
    from apps.metering.pricing.models import ProviderRate

    rates = ProviderRate.objects.filter(
        tenant=request.auth.tenant, valid_to__isnull=True,
    ).order_by("provider", "event_type", "metric_name")
    return [_rate_to_out(r) for r in rates]


@metering_api.post("/pricing/rates", response=ProviderRateOut)
def create_rate(request, payload: ProviderRateIn):
    _product_check(request)
    from apps.metering.pricing.models import ProviderRate

    rate = ProviderRate.objects.create(
        tenant=request.auth.tenant,
        provider=payload.provider,
        event_type=payload.event_type,
        metric_name=payload.metric_name,
        dimensions=payload.dimensions,
        cost_per_unit_micros=payload.cost_per_unit_micros,
        unit_quantity=payload.unit_quantity,
        currency=payload.currency,
    )
    return _rate_to_out(rate)


@metering_api.put("/pricing/rates/{rate_id}", response=ProviderRateOut)
def update_rate(request, rate_id: UUID, payload: ProviderRateIn):
    """Soft-expire old rate and create new version."""
    _product_check(request)
    from apps.metering.pricing.models import ProviderRate

    old_rate = get_object_or_404(
        ProviderRate, id=rate_id, tenant=request.auth.tenant, valid_to__isnull=True,
    )
    now = timezone.now()
    old_rate.valid_to = now
    old_rate.save(update_fields=["valid_to", "updated_at"])

    new_rate = ProviderRate.objects.create(
        tenant=request.auth.tenant,
        provider=payload.provider,
        event_type=payload.event_type,
        metric_name=payload.metric_name,
        dimensions=payload.dimensions,
        cost_per_unit_micros=payload.cost_per_unit_micros,
        unit_quantity=payload.unit_quantity,
        currency=payload.currency,
    )
    return _rate_to_out(new_rate)


@metering_api.delete("/pricing/rates/{rate_id}")
def delete_rate(request, rate_id: UUID):
    _product_check(request)
    from apps.metering.pricing.models import ProviderRate

    rate = get_object_or_404(
        ProviderRate, id=rate_id, tenant=request.auth.tenant, valid_to__isnull=True,
    )
    rate.valid_to = timezone.now()
    rate.save(update_fields=["valid_to", "updated_at"])
    return {"status": "deleted"}


# --- Pricing Markups CRUD ---


def _markup_to_out(markup):
    return {
        "id": markup.id,
        "event_type": markup.event_type,
        "provider": markup.provider,
        "markup_percentage_micros": markup.markup_percentage_micros,
        "fixed_uplift_micros": markup.fixed_uplift_micros,
        "valid_from": markup.valid_from.isoformat(),
        "valid_to": markup.valid_to.isoformat() if markup.valid_to else None,
    }


@metering_api.get("/pricing/markups", response=list[TenantMarkupOut])
def list_markups(request):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markups = TenantMarkup.objects.filter(
        tenant=request.auth.tenant, valid_to__isnull=True,
    ).order_by("event_type", "provider")
    return [_markup_to_out(m) for m in markups]


@metering_api.post("/pricing/markups", response=TenantMarkupOut)
def create_markup(request, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markup = TenantMarkup.objects.create(
        tenant=request.auth.tenant,
        event_type=payload.event_type,
        provider=payload.provider,
        markup_percentage_micros=payload.markup_percentage_micros,
        fixed_uplift_micros=payload.fixed_uplift_micros,
    )
    return _markup_to_out(markup)


@metering_api.put("/pricing/markups/{markup_id}", response=TenantMarkupOut)
def update_markup(request, markup_id: UUID, payload: TenantMarkupIn):
    """Soft-expire old markup and create new version."""
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    old_markup = get_object_or_404(
        TenantMarkup, id=markup_id, tenant=request.auth.tenant, valid_to__isnull=True,
    )
    now = timezone.now()
    old_markup.valid_to = now
    old_markup.save(update_fields=["valid_to", "updated_at"])

    new_markup = TenantMarkup.objects.create(
        tenant=request.auth.tenant,
        event_type=payload.event_type,
        provider=payload.provider,
        markup_percentage_micros=payload.markup_percentage_micros,
        fixed_uplift_micros=payload.fixed_uplift_micros,
    )
    return _markup_to_out(new_markup)


@metering_api.delete("/pricing/markups/{markup_id}")
def delete_markup(request, markup_id: UUID):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markup = get_object_or_404(
        TenantMarkup, id=markup_id, tenant=request.auth.tenant, valid_to__isnull=True,
    )
    markup.valid_to = timezone.now()
    markup.save(update_fields=["valid_to", "updated_at"])
    return {"status": "deleted"}


# --- Analytics ---


@metering_api.get("/analytics/usage", response=UsageAnalyticsResponse)
def usage_analytics(request, start_date: date = None, end_date: date = None):
    """Usage analytics. Uses billed_cost_micros (falls back to cost_micros via Coalesce)
    to correctly aggregate both pricing modes."""
    _product_check(request)
    tenant = request.auth.tenant
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lte=end_date)

    # Coalesce: use billed_cost_micros if set (metric pricing), else cost_micros (legacy)
    effective_cost = Coalesce("billed_cost_micros", "cost_micros")

    totals = qs.aggregate(
        total_events=Count("id"),
        total_billed_cost_micros=Sum(effective_cost),
        total_provider_cost_micros=Sum("provider_cost_micros"),
    )

    by_provider = list(
        qs.exclude(provider="").values("provider").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum(effective_cost),
        ).order_by("-total_cost_micros")
    )

    by_event_type = list(
        qs.exclude(event_type="").values("event_type").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum(effective_cost),
        ).order_by("-total_cost_micros")
    )

    return {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": totals["total_billed_cost_micros"] or 0,
        "total_provider_cost_micros": totals["total_provider_cost_micros"] or 0,
        "by_provider": by_provider,
        "by_event_type": by_event_type,
    }
