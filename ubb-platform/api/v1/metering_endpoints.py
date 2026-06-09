import re
from datetime import date, datetime
from uuid import UUID

from django.db import transaction
from django.db.models import Sum, Count, Q
from django.db.models.fields.json import KeyTextTransform
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Query

from core.auth import ApiKeyAuth, ProductAccess
from django.utils import timezone

from api.v1.schemas import (
    RecordUsageRequest, RecordUsageResponse,
    PaginatedUsageResponse,
    TenantMarkupIn, TenantMarkupOut,
    CloseRunResponse,
    UsageAnalyticsResponse,
    UsageTimeseriesResponse,
    RateCardIn, RateCardOut, RateCardUpdateIn, RateCardBatchIn,
)
from apps.metering.pricing.models import RateCard, CARD_TYPE_CHOICES, PRICING_MODEL_CHOICES
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent

metering_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_metering_v1")

_product_check = ProductAccess("metering")


@metering_api.post("/usage", response={200: RecordUsageResponse})
def record_usage(request, payload: RecordUsageRequest):
    _product_check(request)

    from apps.platform.runs.services import HardStopExceeded, RunNotActive, RunService
    from apps.metering.pricing.services.pricing_service import PricingError

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
        )
    except HardStopExceeded as e:
        from django.db import transaction
        with transaction.atomic():
            RunService.kill_run(payload.run_id, reason=e.reason,
                                tenant_id=request.auth.tenant.id, customer_id=customer.id)
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
    except ValueError as e:
        from ninja.errors import HttpError
        raise HttpError(422, str(e))
    provenance = result.get("pricing_provenance") or {}
    result["uncosted_metrics"] = provenance.get("uncosted_metrics", [])
    return result


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
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lte=end_date)
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
        from collections import defaultdict
        agg = defaultdict(lambda: {"event_count": 0, "total_cost_micros": 0, "total_provider_cost_micros": 0})
        for tags, billed, provider in qs.filter(tags__has_key=tag_key).values_list(
            "tags", "billed_cost_micros", "provider_cost_micros"
        ):
            val = (tags or {}).get(tag_key)
            agg[val]["event_count"] += 1
            agg[val]["total_cost_micros"] += billed or 0
            agg[val]["total_provider_cost_micros"] += provider or 0
        by_tag = [
            {
                "tag_value": k,
                "event_count": v["event_count"],
                "total_cost_micros": v["total_cost_micros"],
                "total_provider_cost_micros": v["total_provider_cost_micros"],
            }
            for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["total_cost_micros"])
        ]

    breakdowns: dict = {}
    if dimensions:
        if len(dimensions) > 6:
            return 422, {"error": "at most 6 dimensions"}
        for dim in dimensions:
            if dim.startswith("tag:"):
                key = dim[4:]
                if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key):
                    return 422, {"error": f"invalid tag dimension {dim}"}
                rows = list(
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
            elif dim in _ANALYTICS_ALLOWED_COLS:
                col = "customer__external_id" if dim == "customer" else dim
                base = qs if dim == "customer" else qs.exclude(**{col: ""})
                rows = list(
                    base.values(col)
                    .annotate(
                        event_count=Count("id"),
                        total_provider_cost_micros=Sum("provider_cost_micros"),
                        total_billed_cost_micros=Sum("billed_cost_micros"),
                    )
                    .order_by("-total_billed_cost_micros")
                )
                for r in rows:
                    r["dimension"] = r.pop(col)
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
    """Time-series spend rollup: daily or hourly COGS per tenant/customer."""
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


def _rate_card_to_out(c):
    return {
        "id": str(c.id),
        "lineage_id": str(c.lineage_id),
        "card_type": c.card_type,
        "metric_name": c.metric_name,
        "provider": c.provider,
        "event_type": c.event_type,
        "dimensions": c.dimensions,
        "pricing_model": c.pricing_model,
        "rate_per_unit_micros": c.rate_per_unit_micros,
        "unit_quantity": c.unit_quantity,
        "fixed_micros": c.fixed_micros,
        "currency": c.currency,
        "product_id": c.product_id,
        "customer_id": str(c.customer_id) if c.customer_id else None,
        "valid_from": c.valid_from.isoformat(),
        "valid_to": c.valid_to.isoformat() if c.valid_to else None,
    }


def _gate_card_type(request, card_type):
    _product_check(request)
    if card_type == "price":
        _billing_check(request)


@metering_api.get("/pricing/rate-cards", response=list[RateCardOut])
def list_rate_cards(request, card_type: str = None, include_history: bool = False,
                    as_of: datetime = None):
    _product_check(request)
    qs = RateCard.objects.filter(tenant=request.auth.tenant)
    if as_of is not None:
        qs = qs.filter(valid_from__lte=as_of).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
    elif not include_history:
        qs = qs.filter(valid_to__isnull=True)
    if card_type:
        qs = qs.filter(card_type=card_type)
    return [_rate_card_to_out(c) for c in qs.order_by(
        "card_type", "provider", "event_type", "metric_name", "-valid_from")]


@metering_api.post("/pricing/rate-cards", response={200: RateCardOut, 422: dict})
def create_rate_card(request, payload: RateCardIn):
    _gate_card_type(request, payload.card_type)
    valid_types = {c[0] for c in CARD_TYPE_CHOICES}
    valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
    if payload.card_type not in valid_types:
        return 422, {"error": f"card_type must be one of {sorted(valid_types)}"}
    if payload.pricing_model not in valid_models:
        return 422, {"error": f"pricing_model must be one of {sorted(valid_models)}"}
    customer = None
    if payload.customer_id:
        customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    card = RateCard.objects.create(
        tenant=request.auth.tenant,
        customer=customer,
        card_type=payload.card_type,
        metric_name=payload.metric_name,
        provider=payload.provider,
        event_type=payload.event_type,
        dimensions=payload.dimensions,
        pricing_model=payload.pricing_model,
        rate_per_unit_micros=payload.rate_per_unit_micros,
        unit_quantity=payload.unit_quantity,
        fixed_micros=payload.fixed_micros,
        currency=payload.currency,
        product_id=payload.product_id,
    )
    return 200, _rate_card_to_out(card)


@metering_api.post("/pricing/rate-cards/batch", response={200: dict, 422: dict})
def bulk_create_rate_cards(request, payload: RateCardBatchIn):
    cards = payload.cards
    if not cards or len(cards) > 100:
        return 422, {"error": "cards must be 1..100"}
    valid_types = {c[0] for c in CARD_TYPE_CHOICES}
    valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
    # Pre-validate EVERY card before creating any (all-or-nothing)
    for i, c in enumerate(cards):
        if c.card_type not in valid_types:
            return 422, {"error": f"cards[{i}].card_type invalid"}
        if c.pricing_model not in valid_models:
            return 422, {"error": f"cards[{i}].pricing_model invalid"}
        # Replicate product-gating from single-create: price cards need billing product
        if c.card_type == "price":
            _billing_check(request)
    created = []
    with transaction.atomic():
        for c in cards:
            customer = None
            if c.customer_id:
                customer = get_object_or_404(Customer, id=c.customer_id, tenant=request.auth.tenant)
            obj = RateCard.objects.create(
                tenant=request.auth.tenant,
                customer=customer,
                card_type=c.card_type,
                metric_name=c.metric_name,
                provider=c.provider,
                event_type=c.event_type,
                dimensions=c.dimensions,
                pricing_model=c.pricing_model,
                rate_per_unit_micros=c.rate_per_unit_micros,
                unit_quantity=c.unit_quantity,
                fixed_micros=c.fixed_micros,
                currency=c.currency,
                product_id=c.product_id,
            )
            created.append(str(obj.id))
    return 200, {"created": created, "count": len(created)}


_RATE_CARD_COPY_FIELDS = (
    "card_type", "metric_name", "provider", "event_type", "dimensions",
    "pricing_model", "rate_per_unit_micros", "unit_quantity", "fixed_micros",
    "currency", "product_id",
)


@metering_api.put("/pricing/rate-cards/{card_id}", response={200: RateCardOut, 422: dict})
def update_rate_card(request, card_id: UUID, payload: RateCardUpdateIn):
    # Resolve the target: by id (any version), falling back to the active card
    # sharing that lineage. Only active (valid_to IS NULL) versions are editable.
    changes = payload.dict(exclude_unset=True)

    with transaction.atomic():
        old = RateCard.objects.filter(
            id=card_id, tenant=request.auth.tenant, valid_to__isnull=True
        ).first()
        if old is None:
            target = get_object_or_404(RateCard, id=card_id, tenant=request.auth.tenant)
            old = RateCard.objects.filter(
                tenant=request.auth.tenant, lineage_id=target.lineage_id,
                valid_to__isnull=True,
            ).first()
            if old is None:
                from ninja.errors import HttpError
                raise HttpError(404, "No active version for this rate card")

        # Build the new version: copy all fields from old, apply request changes.
        new_values = {f: getattr(old, f) for f in _RATE_CARD_COPY_FIELDS}
        for f in _RATE_CARD_COPY_FIELDS:
            if f in changes:
                new_values[f] = changes[f]

        customer = old.customer
        if "customer_id" in changes:
            if changes["customer_id"]:
                customer = get_object_or_404(
                    Customer, id=changes["customer_id"], tenant=request.auth.tenant)
            else:
                customer = None

        # Preserve the Wave 1 enum validation.
        valid_types = {c[0] for c in CARD_TYPE_CHOICES}
        valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
        if new_values["card_type"] not in valid_types:
            return 422, {"error": f"card_type must be one of {sorted(valid_types)}"}
        if new_values["pricing_model"] not in valid_models:
            return 422, {"error": f"pricing_model must be one of {sorted(valid_models)}"}

        _gate_card_type(request, new_values["card_type"])

        # Close the old version, then open the new one. valid_from on the new row
        # (auto_now_add) is >= the old row's valid_to, so the windows never overlap
        # and the active-row partial unique constraint always sees exactly one.
        old.valid_to = timezone.now()
        old.save(update_fields=["valid_to", "updated_at"])

        card = RateCard.objects.create(
            tenant=request.auth.tenant,
            customer=customer,
            lineage_id=old.lineage_id,
            **new_values,
        )
    return 200, _rate_card_to_out(card)


@metering_api.get("/pricing/rate-cards/{lineage_id}/history", response=list[RateCardOut])
def rate_card_history(request, lineage_id: UUID):
    _product_check(request)
    qs = RateCard.objects.filter(
        tenant=request.auth.tenant, lineage_id=lineage_id).order_by("-valid_from")
    return [_rate_card_to_out(c) for c in qs]


@metering_api.delete("/pricing/rate-cards/{card_id}")
def delete_rate_card(request, card_id: UUID):
    _product_check(request)
    card = get_object_or_404(RateCard, id=card_id, tenant=request.auth.tenant, valid_to__isnull=True)
    card.valid_to = timezone.now()
    card.save(update_fields=["valid_to", "updated_at"])
    return {"status": "deleted"}
