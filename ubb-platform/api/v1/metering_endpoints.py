from datetime import date
from uuid import UUID

from django.db.models import Sum, Count
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI, Router

from api.v1.middleware import CamelCaseRenderer
from core.auth import ApiKeyAuth, ProductAccess
from core.clerk_auth import ClerkJWTAuth
from api.v1.schemas import (
    RecordUsageRequest, RecordUsageResponse,
    PaginatedUsageResponse,
    CloseRunResponse,
    UsageAnalyticsResponse,
    CreateCardRequest, UpdateCardRequest, DimensionIn,
    CardOut, CardListResponse,
)
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent

metering_api = NinjaAPI(auth=[ApiKeyAuth(), ClerkJWTAuth()], urls_namespace="ubb_metering_v1", renderer=CamelCaseRenderer(), default_router=Router(by_alias=True))

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
            usage_metrics=payload.usage_metrics if payload.usage_metrics else None,
            group=payload.group,
            run_id=payload.run_id,
            pricing_card=payload.pricing_card,
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
              group: str = None):
    _product_check(request)

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)  # Clamp between 1 and 100

    qs = customer.usage_events.all().order_by("-effective_at", "-id")

    if group:
        qs = qs.filter(group=group)

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
                "provider": e.provider,
                "card_slug": e.card_slug or "",
                "card_name": e.card_name or "",
                "provider_cost_micros": e.provider_cost_micros,
                "billed_cost_micros": e.billed_cost_micros,
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


# --- Pricing Cards CRUD ---


def _card_to_out(card):
    dimensions = card.rates.filter(valid_to__isnull=True).order_by("metric_name")
    return {
        "id": str(card.id),
        "slug": card.slug,
        "name": card.name,
        "provider": card.provider,
        "description": card.description,
        "pricing_source_url": card.pricing_source_url,
        "group_id": str(card.group_id) if card.group_id else None,
        "group_name": card.group.name if card.group_id else None,
        "status": card.status,
        "dimensions": [
            {
                "id": str(r.id),
                "metric_name": r.metric_name,
                "pricing_type": r.pricing_type,
                "cost_per_unit_micros": r.cost_per_unit_micros,
                "provider_cost_per_unit_micros": r.provider_cost_per_unit_micros,
                "unit_quantity": r.unit_quantity,
                "currency": r.currency,
                "label": r.label,
                "unit": r.unit,
                "valid_from": r.valid_from.isoformat(),
                "valid_to": None,
            }
            for r in dimensions
        ],
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }


@metering_api.post("/pricing/cards", response={201: CardOut})
def create_card(request, payload: CreateCardRequest):
    _product_check(request)
    from apps.metering.pricing.models import Card, Rate
    from apps.platform.groups.models import Group

    group = None
    if payload.group_id:
        group = get_object_or_404(Group, id=payload.group_id, tenant=request.auth.tenant)

    card = Card.objects.create(
        tenant=request.auth.tenant,
        name=payload.name,
        slug=payload.slug,
        provider=payload.provider,
        description=payload.description,
        pricing_source_url=payload.pricing_source_url,
        group=group,
        status=payload.status,
    )
    for d in payload.dimensions:
        Rate.objects.create(
            card=card,
            metric_name=d.metric_name,
            pricing_type=d.pricing_type,
            cost_per_unit_micros=d.cost_per_unit_micros,
            provider_cost_per_unit_micros=d.provider_cost_per_unit_micros,
            unit_quantity=d.unit_quantity,
            currency=d.currency,
            label=d.label,
            unit=d.unit,
        )
    return 201, _card_to_out(card)


@metering_api.get("/pricing/cards", response=CardListResponse)
def list_cards(request, cursor: str = None, limit: int = 50):
    _product_check(request)
    from apps.metering.pricing.models import Card

    limit = min(max(limit, 1), 100)
    qs = Card.objects.filter(
        tenant=request.auth.tenant, status__in=["active", "draft"],
    ).select_related("group").order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            from ninja.errors import HttpError
            raise HttpError(400, "Invalid cursor")

    cards = list(qs[:limit + 1])
    has_more = len(cards) > limit
    cards = cards[:limit]

    next_cursor = None
    if has_more and cards:
        last = cards[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [_card_to_out(c) for c in cards],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@metering_api.get("/pricing/cards/{card_id}", response=CardOut)
def get_card(request, card_id: UUID):
    _product_check(request)
    from apps.metering.pricing.models import Card

    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    return _card_to_out(card)


@metering_api.patch("/pricing/cards/{card_id}", response=CardOut)
def update_card(request, card_id: UUID, payload: UpdateCardRequest):
    _product_check(request)
    from apps.metering.pricing.models import Card
    from apps.platform.groups.models import Group

    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    update_fields = ["updated_at"]
    if payload.name is not None:
        card.name = payload.name
        update_fields.append("name")
    if payload.description is not None:
        card.description = payload.description
        update_fields.append("description")
    if payload.pricing_source_url is not None:
        card.pricing_source_url = payload.pricing_source_url
        update_fields.append("pricing_source_url")
    if payload.group_id is not None:
        if payload.group_id == "":
            card.group = None
        else:
            card.group = get_object_or_404(Group, id=payload.group_id, tenant=request.auth.tenant)
        update_fields.append("group")
    if payload.status is not None:
        card.status = payload.status
        update_fields.append("status")
    card.save(update_fields=update_fields)
    return _card_to_out(card)


@metering_api.delete("/pricing/cards/{card_id}")
def delete_card(request, card_id: UUID):
    _product_check(request)
    from apps.metering.pricing.models import Card

    card = get_object_or_404(
        Card, id=card_id, tenant=request.auth.tenant, status="active",
    )
    card.status = "archived"
    card.save(update_fields=["status", "updated_at"])
    return {"status": "archived"}


# --- Nested Rate management on Cards ---


@metering_api.post("/pricing/cards/{card_id}/rates", response={201: dict})
def add_card_rate(request, card_id: UUID, payload: DimensionIn):
    _product_check(request)
    from apps.metering.pricing.models import Card, Rate

    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    rate = Rate.objects.create(
        card=card,
        metric_name=payload.metric_name,
        pricing_type=payload.pricing_type,
        cost_per_unit_micros=payload.cost_per_unit_micros,
        provider_cost_per_unit_micros=payload.provider_cost_per_unit_micros,
        unit_quantity=payload.unit_quantity,
        currency=payload.currency,
        label=payload.label,
        unit=payload.unit,
    )
    return 201, {
        "id": str(rate.id),
        "metric_name": rate.metric_name,
        "pricing_type": rate.pricing_type,
        "cost_per_unit_micros": rate.cost_per_unit_micros,
        "provider_cost_per_unit_micros": rate.provider_cost_per_unit_micros,
        "unit_quantity": rate.unit_quantity,
        "currency": rate.currency,
        "label": rate.label,
        "unit": rate.unit,
        "valid_from": rate.valid_from.isoformat(),
        "valid_to": None,
    }


@metering_api.put("/pricing/cards/{card_id}/rates/{rate_id}", response=dict)
def update_card_rate(request, card_id: UUID, rate_id: UUID, payload: DimensionIn):
    """Soft-expire old rate, create new version."""
    _product_check(request)
    from apps.metering.pricing.models import Card, Rate

    from django.db import transaction

    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    old_rate = get_object_or_404(
        Rate, id=rate_id, card=card, valid_to__isnull=True,
    )
    now = timezone.now()
    with transaction.atomic():
        old_rate.valid_to = now
        old_rate.save(update_fields=["valid_to", "updated_at"])

        new_rate = Rate.objects.create(
            card=card,
            metric_name=payload.metric_name,
            pricing_type=payload.pricing_type,
            cost_per_unit_micros=payload.cost_per_unit_micros,
            provider_cost_per_unit_micros=payload.provider_cost_per_unit_micros,
            unit_quantity=payload.unit_quantity,
            currency=payload.currency,
            label=payload.label,
            unit=payload.unit,
        )

    return {
        "id": str(new_rate.id),
        "metric_name": new_rate.metric_name,
        "pricing_type": new_rate.pricing_type,
        "cost_per_unit_micros": new_rate.cost_per_unit_micros,
        "provider_cost_per_unit_micros": new_rate.provider_cost_per_unit_micros,
        "unit_quantity": new_rate.unit_quantity,
        "currency": new_rate.currency,
        "label": new_rate.label,
        "unit": new_rate.unit,
        "valid_from": new_rate.valid_from.isoformat(),
        "valid_to": None,
    }


@metering_api.delete("/pricing/cards/{card_id}/rates/{rate_id}")
def delete_card_rate(request, card_id: UUID, rate_id: UUID):
    _product_check(request)
    from apps.metering.pricing.models import Card, Rate

    card = get_object_or_404(Card, id=card_id, tenant=request.auth.tenant)
    rate = get_object_or_404(
        Rate, id=rate_id, card=card, valid_to__isnull=True,
    )
    rate.valid_to = timezone.now()
    rate.save(update_fields=["valid_to", "updated_at"])
    return {"status": "deactivated"}


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

    by_card = list(
        qs.exclude(card_slug="").values("card_slug", "card_name").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum(effective_cost),
        ).order_by("-total_cost_micros")
    )

    return {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": totals["total_billed_cost_micros"] or 0,
        "total_provider_cost_micros": totals["total_provider_cost_micros"] or 0,
        "by_provider": by_provider,
        "by_card": by_card,
    }
