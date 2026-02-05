from ninja import NinjaAPI
from core.auth import ApiKeyAuth, ProductAccess
from api.v1.schemas import (
    RecordUsageRequest, RecordUsageResponse,
    PaginatedUsageResponse,
)
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from django.shortcuts import get_object_or_404

metering_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_metering_v1")

_product_check = ProductAccess("metering")


@metering_api.post("/usage", response=RecordUsageResponse)
def record_usage(request, payload: RecordUsageRequest):
    _product_check(request)

    from apps.metering.pricing.services.pricing_service import PricingError

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
        )
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
