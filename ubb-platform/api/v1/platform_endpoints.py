import calendar
import csv
import io
import uuid as _uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from django.db import IntegrityError
from django.db.models import Q, Sum, Count, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI, Query, Router, Schema
from ninja.errors import HttpError

from api.v1.middleware import CamelCaseRenderer
from api.v1.pagination import apply_cursor_filter, encode_cursor
from api.v1.schemas import (
    CamelSchema,
    CreateGroupRequest, UpdateGroupRequest, GroupResponse, GroupListResponse,
    EventsListRequest, StagedEventIn, PushEventsRequest,
    DashboardStatsResponse,
    DashboardChartsResponse,
    DashboardCustomersResponse,
    EventFilterOptionsResponse,
    EventsListResponse,
    PushEventsResponse,
    EventBatchOut,
    TenantDefaultMarginResponse, UpdateTenantDefaultMarginRequest,
    MeResponse, MeTenantResponse, MeTenantUserResponse,
    CreateTenantRequest, CreateTenantResponse,
    UpdateTenantRequest,
)
from core.auth import ApiKeyAuth
from core.clerk_auth import ClerkJWTAuth
from core.clerk_api import ClerkAPIError
from apps.platform.tenants.models import TenantUser
from apps.platform.tenants.services import provision_tenant_for_clerk_user
from apps.platform.customers.models import Customer
from apps.platform.groups.models import Group
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.models import Card, Rate
from apps.metering.usage.models import UsageEvent, EventBatch
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.pricing.services.pricing_service import PricingError


class CreateCustomerRequest(CamelSchema):
    external_id: str
    stripe_customer_id: str = ""
    metadata: dict = {}


class UpdateCustomerRequest(CamelSchema):
    status: Optional[str] = None
    metadata: Optional[dict] = None
    stripe_customer_id: Optional[str] = None
    min_balance_micros: Optional[int] = None


class CustomerResponse(CamelSchema):
    id: str
    external_id: str
    stripe_customer_id: str
    status: str


class CustomerDetailResponse(CamelSchema):
    id: str
    external_id: str
    stripe_customer_id: str
    status: str
    metadata: dict
    min_balance_micros: Optional[int] = None
    created_at: str
    updated_at: str


class CustomerListResponse(CamelSchema):
    data: list[CustomerDetailResponse]
    next_cursor: Optional[str] = None
    has_more: bool


platform_api = NinjaAPI(auth=[ApiKeyAuth(), ClerkJWTAuth()], urls_namespace="ubb_platform_v1", renderer=CamelCaseRenderer(), default_router=Router(by_alias=True))


@platform_api.get("/me", response=MeResponse, auth=ClerkJWTAuth())
def get_me(request):
    tu = getattr(request, "tenant_user", None)
    if tu is None:
        return {
            "tenant_user": None,
            "tenant": None,
            "onboarding_completed": False,
        }

    tenant = tu.tenant
    cards_count = Card.objects.filter(tenant=tenant).count()
    events_count = UsageEvent.objects.filter(tenant=tenant).count()
    return {
        "tenant_user": {
            "id": str(tu.id),
            "email": tu.email,
            "role": tu.role,
        },
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "products": tenant.products,
            "pricing_cards_count": cards_count,
            "usage_events_count": events_count,
        },
        "onboarding_completed": tenant.onboarding_completed_at is not None,
    }


@platform_api.post(
    "/tenant",
    response={201: CreateTenantResponse, 200: CreateTenantResponse},
    auth=ClerkJWTAuth(),
)
def create_tenant(request, payload: CreateTenantRequest):
    clerk_user_id = getattr(request, "clerk_user_id", None)
    if not clerk_user_id:
        raise HttpError(401, "Clerk authentication required")

    existed_before = TenantUser.objects.filter(clerk_user_id=clerk_user_id).exists()

    try:
        tenant, tu, raw_key = provision_tenant_for_clerk_user(
            clerk_user_id=clerk_user_id,
            tenant_name=payload.name,
        )
    except ClerkAPIError as exc:
        raise HttpError(503, f"Account verification failed: {exc}") from exc

    status_code = 200 if existed_before else 201
    return status_code, {
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "products": tenant.products,
            "pricing_cards_count": 0,
            "usage_events_count": 0,
        },
        "api_key": raw_key,
    }


@platform_api.patch("/tenant", response=MeTenantResponse, auth=ClerkJWTAuth())
def update_tenant(request, payload: UpdateTenantRequest):
    _require_tenant_user(request)

    tenant = request.tenant
    fields_to_update = ["updated_at"]

    if payload.name is not None:
        tenant.name = payload.name
        fields_to_update.append("name")

    if payload.complete_onboarding and tenant.onboarding_completed_at is None:
        tenant.onboarding_completed_at = timezone.now()
        fields_to_update.append("onboarding_completed_at")

    tenant.save(update_fields=fields_to_update)

    cards_count = Card.objects.filter(tenant=tenant).count()
    events_count = UsageEvent.objects.filter(tenant=tenant).count()
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "products": tenant.products,
        "pricing_cards_count": cards_count,
        "usage_events_count": events_count,
    }


def _require_tenant_user(request):
    """Raise 403 if the request was authenticated via Clerk JWT but has no TenantUser yet.

    This guards against a valid Clerk JWT (e.g. a new user mid-onboarding) hitting
    endpoints that require a fully provisioned tenant.
    """
    if getattr(request, "tenant_user", None) is None and isinstance(request.auth, str):
        raise HttpError(403, "Tenant user required for this operation")


def _customer_to_detail(c: Customer) -> dict:
    return {
        "id": str(c.id),
        "external_id": c.external_id,
        "stripe_customer_id": c.stripe_customer_id,
        "status": c.status,
        "metadata": c.metadata,
        "min_balance_micros": c.min_balance_micros,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


@platform_api.post("/customers", response={201: CustomerResponse, 409: dict})
def create_customer(request, payload: CreateCustomerRequest):
    _require_tenant_user(request)
    try:
        customer = Customer.objects.create(
            tenant=request.auth.tenant,
            external_id=payload.external_id,
            stripe_customer_id=payload.stripe_customer_id,
            metadata=payload.metadata,
        )
        return 201, {
            "id": str(customer.id),
            "external_id": customer.external_id,
            "stripe_customer_id": customer.stripe_customer_id,
            "status": customer.status,
        }
    except IntegrityError:
        return 409, {"error": "Customer with this external_id already exists"}


@platform_api.get("/customers", response=CustomerListResponse)
def list_customers(
    request,
    status: str = None,
    search: str = None,
    cursor: str = None,
    limit: int = 50,
):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = Customer.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if status:
        qs = qs.filter(status=status)

    if search:
        qs = qs.filter(
            Q(external_id__icontains=search)
            | Q(stripe_customer_id__icontains=search)
        )

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return platform_api.create_response(
                request, {"error": "Invalid cursor"}, status=400
            )

    customers = list(qs[: limit + 1])
    has_more = len(customers) > limit
    customers = customers[:limit]

    next_cursor = None
    if has_more and customers:
        last = customers[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [_customer_to_detail(c) for c in customers],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@platform_api.get("/customers/{customer_id}", response=CustomerDetailResponse)
def get_customer(request, customer_id: str):
    _require_tenant_user(request)
    customer = get_object_or_404(
        Customer, id=customer_id, tenant=request.auth.tenant
    )
    return _customer_to_detail(customer)


@platform_api.patch("/customers/{customer_id}", response=CustomerDetailResponse)
def update_customer(request, customer_id: str, payload: UpdateCustomerRequest):
    _require_tenant_user(request)
    customer = get_object_or_404(
        Customer, id=customer_id, tenant=request.auth.tenant
    )

    update_fields = ["updated_at"]
    if payload.status is not None:
        customer.status = payload.status
        update_fields.append("status")
    if payload.metadata is not None:
        customer.metadata = payload.metadata
        update_fields.append("metadata")
    if payload.stripe_customer_id is not None:
        customer.stripe_customer_id = payload.stripe_customer_id
        update_fields.append("stripe_customer_id")
    if payload.min_balance_micros is not None:
        customer.min_balance_micros = payload.min_balance_micros
        update_fields.append("min_balance_micros")

    if len(update_fields) > 1:
        customer.save(update_fields=update_fields)

    return _customer_to_detail(customer)


@platform_api.delete("/customers/{customer_id}")
def delete_customer(request, customer_id: str):
    _require_tenant_user(request)
    customer = get_object_or_404(
        Customer, id=customer_id, tenant=request.auth.tenant
    )
    customer.soft_delete()
    return platform_api.create_response(request, "", status=204)


@platform_api.get("/wallets")
def list_wallets(request, max_balance_micros: int = None, cursor: str = None, limit: int = 50):
    _require_tenant_user(request)
    qs = Wallet.objects.filter(
        customer__tenant=request.auth.tenant
    ).select_related("customer").order_by("-created_at", "-id")

    if max_balance_micros is not None:
        qs = qs.filter(balance_micros__lte=max_balance_micros)

    limit = min(max(limit, 1), 100)

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return platform_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    wallets = list(qs[:limit + 1])
    has_more = len(wallets) > limit
    wallets = wallets[:limit]

    next_cursor = None
    if has_more and wallets:
        last = wallets[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [{
            "id": str(w.id),
            "customer_id": str(w.customer_id),
            "customer_external_id": w.customer.external_id,
            "balance_micros": w.balance_micros,
            "currency": w.currency,
            "created_at": w.created_at.isoformat(),
        } for w in wallets],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ── Group endpoints ──────────────────────────────────────────────────────


def _group_to_response(g):
    return {
        "id": str(g.id),
        "name": g.name,
        "slug": g.slug,
        "description": g.description,
        "margin_pct": float(g.margin_pct) if g.margin_pct is not None else None,
        "status": g.status,
        "parent_id": str(g.parent_id) if g.parent_id else None,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
    }


@platform_api.post("/groups", response={201: GroupResponse, 409: dict})
def create_group(request, payload: CreateGroupRequest):
    _require_tenant_user(request)
    kwargs = {
        "tenant": request.auth.tenant,
        "name": payload.name,
        "slug": payload.slug,
        "description": payload.description,
    }
    if payload.margin_pct is not None:
        kwargs["margin_pct"] = payload.margin_pct
    if payload.parent_id is not None:
        parent = get_object_or_404(
            Group, id=payload.parent_id, tenant=request.auth.tenant
        )
        kwargs["parent"] = parent

    try:
        group = Group.objects.create(**kwargs)
    except IntegrityError:
        return 409, {"error": "Group with this slug already exists"}

    return 201, _group_to_response(group)


@platform_api.get("/groups", response=GroupListResponse)
def list_groups(
    request,
    status: str = None,
    cursor: str = None,
    limit: int = 50,
):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = Group.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if status:
        qs = qs.filter(status=status)

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return platform_api.create_response(
                request, {"error": "Invalid cursor"}, status=400
            )

    groups = list(qs[: limit + 1])
    has_more = len(groups) > limit
    groups = groups[:limit]

    next_cursor = None
    if has_more and groups:
        last = groups[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [_group_to_response(g) for g in groups],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@platform_api.get("/groups/{group_id}", response=GroupResponse)
def get_group(request, group_id: str):
    _require_tenant_user(request)
    group = get_object_or_404(
        Group, id=group_id, tenant=request.auth.tenant
    )
    return _group_to_response(group)


@platform_api.patch("/groups/{group_id}", response=GroupResponse)
def update_group(request, group_id: str, payload: UpdateGroupRequest):
    _require_tenant_user(request)
    group = get_object_or_404(
        Group, id=group_id, tenant=request.auth.tenant
    )

    update_fields = ["updated_at"]
    if payload.name is not None:
        group.name = payload.name
        update_fields.append("name")
    if payload.description is not None:
        group.description = payload.description
        update_fields.append("description")
    if payload.margin_pct is not None:
        group.margin_pct = payload.margin_pct
        update_fields.append("margin_pct")
    if payload.status is not None:
        group.status = payload.status
        update_fields.append("status")

    if len(update_fields) > 1:
        group.save(update_fields=update_fields)

    return _group_to_response(group)


@platform_api.delete("/groups/{group_id}")
def delete_group(request, group_id: str):
    _require_tenant_user(request)
    group = get_object_or_404(
        Group, id=group_id, tenant=request.auth.tenant
    )
    group.status = "archived"
    group.save(update_fields=["status", "updated_at"])
    return _group_to_response(group)


# ── Dashboard helpers ────────────────────────────────────────────────────

def _parse_range(range_str: str):
    """Return (start, end, prev_start, prev_end) datetimes for a given range string."""
    now = timezone.now()
    today = now.date()

    if range_str == "YTD":
        start = date(today.year, 1, 1)
        end = today
        prev_start = date(today.year - 1, 1, 1)
        # Fix: clamp day to valid range for previous year (handles Feb 29 in leap years)
        max_day = calendar.monthrange(today.year - 1, today.month)[1]
        prev_end = date(today.year - 1, today.month, min(today.day, max_day))
    else:
        days_map = {"7d": 7, "30d": 30, "90d": 90}
        days = days_map.get(range_str, 30)
        end = today
        start = today - timedelta(days=days)
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)

    # Convert to timezone-aware datetimes for filtering
    from datetime import datetime, time as dt_time
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start, dt_time.min), tz)
    end_dt = timezone.make_aware(datetime.combine(end, dt_time.max), tz)
    prev_start_dt = timezone.make_aware(datetime.combine(prev_start, dt_time.min), tz)
    prev_end_dt = timezone.make_aware(datetime.combine(prev_end, dt_time.max), tz)

    return start_dt, end_dt, prev_start_dt, prev_end_dt


def _pct_change(current, prev):
    if prev == 0 and current == 0:
        return 0.0
    if prev == 0:
        return 100.0
    return round((current - prev) / abs(prev) * 100, 1)


def _revenue_expr():
    """Coalesce(billed_cost_micros, cost_micros) as the effective revenue expression."""
    return Coalesce("billed_cost_micros", "cost_micros", output_field=None)


def _aggregate_period(tenant, start_dt, end_dt):
    """Aggregate revenue, costs, margin for a tenant in a date range."""
    qs = UsageEvent.objects.filter(
        tenant=tenant,
        effective_at__gte=start_dt,
        effective_at__lte=end_dt,
    )
    agg = qs.aggregate(
        revenue=Sum(Coalesce("billed_cost_micros", "cost_micros")),
        api_costs=Sum("provider_cost_micros"),
    )
    revenue = agg["revenue"] or 0
    api_costs = agg["api_costs"] or 0
    margin = revenue - api_costs
    return revenue, api_costs, margin


# ── Dashboard endpoints ──────────────────────────────────────────────────


@platform_api.get("/dashboard/stats", response=DashboardStatsResponse)
def dashboard_stats(request, range: str = "30d"):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    start_dt, end_dt, prev_start_dt, prev_end_dt = _parse_range(range)

    revenue, api_costs, margin = _aggregate_period(tenant, start_dt, end_dt)
    prev_revenue, prev_api_costs, prev_margin = _aggregate_period(
        tenant, prev_start_dt, prev_end_dt
    )

    margin_pct = round(margin / revenue * 100, 1) if revenue else 0.0
    prev_margin_pct = round(prev_margin / prev_revenue * 100, 1) if prev_revenue else 0.0
    cost_per_rev = round(api_costs / revenue, 4) if revenue else 0.0
    prev_cost_per_rev = round(prev_api_costs / prev_revenue, 4) if prev_revenue else 0.0

    # Sparklines: daily values
    daily_qs = (
        UsageEvent.objects.filter(
            tenant=tenant,
            effective_at__gte=start_dt,
            effective_at__lte=end_dt,
        )
        .annotate(day=TruncDate("effective_at"))
        .values("day")
        .annotate(
            revenue=Sum(Coalesce("billed_cost_micros", "cost_micros")),
            api_costs=Sum("provider_cost_micros"),
        )
        .order_by("day")
    )

    spark_revenue = []
    spark_api_costs = []
    spark_margin = []
    spark_margin_pct = []
    spark_cost_per_rev = []

    for row in daily_qs:
        r = row["revenue"] or 0
        c = row["api_costs"] or 0
        m = r - c
        spark_revenue.append(r)
        spark_api_costs.append(c)
        spark_margin.append(m)
        spark_margin_pct.append(round(m / r * 100, 1) if r else 0.0)
        spark_cost_per_rev.append(round(c / r, 4) if r else 0.0)

    return {
        "revenue_micros": revenue,
        "api_costs_micros": api_costs,
        "gross_margin_micros": margin,
        "margin_percentage": margin_pct,
        "cost_per_dollar_revenue": cost_per_rev,
        "revenue_prev_change": _pct_change(revenue, prev_revenue),
        "costs_prev_change": _pct_change(api_costs, prev_api_costs),
        "margin_prev_change": _pct_change(margin, prev_margin),
        "margin_pct_prev_change": round(margin_pct - prev_margin_pct, 1),
        "cost_per_rev_prev_change": round(cost_per_rev - prev_cost_per_rev, 4),
        "sparklines": {
            "revenue": spark_revenue,
            "api_costs": spark_api_costs,
            "gross_margin": spark_margin,
            "margin_pct": spark_margin_pct,
            "cost_per_rev": spark_cost_per_rev,
        },
    }


@platform_api.get("/dashboard/charts", response=DashboardChartsResponse)
def dashboard_charts(request, range: str = "30d"):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    start_dt, end_dt, _, _ = _parse_range(range)

    base_qs = UsageEvent.objects.filter(
        tenant=tenant,
        effective_at__gte=start_dt,
        effective_at__lte=end_dt,
    )

    # 1. Revenue time series (daily)
    daily_qs = (
        base_qs.annotate(day=TruncDate("effective_at"))
        .values("day")
        .annotate(
            revenue_micros=Sum(Coalesce("billed_cost_micros", "cost_micros")),
            api_costs_micros=Sum("provider_cost_micros"),
        )
        .order_by("day")
    )

    revenue_time_series = []
    for row in daily_qs:
        r = row["revenue_micros"] or 0
        c = row["api_costs_micros"] or 0
        revenue_time_series.append({
            "date": row["day"].isoformat(),
            "revenue_micros": r,
            "api_costs_micros": c,
            "margin_micros": r - c,
        })

    # 2. Cost by group (stacked daily series)
    cost_by_group = _build_stacked_series(
        base_qs, group_field="group", value_expr=Sum("provider_cost_micros"),
        label_fn=lambda key: key or "ungrouped",
    )

    # 3. Cost by card (stacked daily series)
    cost_by_card = _build_stacked_series(
        base_qs, group_field="card__slug", value_expr=Sum("provider_cost_micros"),
        label_field="card__name",
    )

    # 4. Revenue by group (pie/donut data)
    revenue_by_group = _build_breakdown(
        base_qs, group_field="group",
        value_expr=Sum(Coalesce("billed_cost_micros", "cost_micros")),
        label_fn=lambda key: key or "ungrouped",
    )

    # 5. Margin by group
    margin_by_group_raw = (
        base_qs.values("group")
        .annotate(
            revenue=Sum(Coalesce("billed_cost_micros", "cost_micros")),
            costs=Sum("provider_cost_micros"),
        )
    )
    margin_items = []
    total_margin = 0
    for row in margin_by_group_raw:
        r = row["revenue"] or 0
        c = row["costs"] or 0
        m = r - c
        margin_items.append({
            "key": row["group"] or "ungrouped",
            "label": row["group"] or "ungrouped",
            "value_micros": m,
        })
        total_margin += m

    for item in margin_items:
        item["percentage"] = (
            round(item["value_micros"] / total_margin * 100, 1) if total_margin else 0.0
        )

    return {
        "revenue_time_series": revenue_time_series,
        "cost_by_group": cost_by_group,
        "cost_by_card": cost_by_card,
        "revenue_by_group": revenue_by_group,
        "margin_by_group": margin_items,
    }


def _build_stacked_series(base_qs, group_field, value_expr, label_fn=None, label_field=None):
    """Build stacked daily series for a given group field."""
    daily_grouped = (
        base_qs.annotate(day=TruncDate("effective_at"))
        .values("day", group_field)
    )
    if label_field:
        daily_grouped = daily_grouped.annotate(label_val=Coalesce(label_field, Value("")))

    daily_grouped = daily_grouped.annotate(value=value_expr).order_by("day", group_field)

    # Collect unique keys and labels
    key_labels = {}
    date_data = defaultdict(dict)

    for row in daily_grouped:
        key = row[group_field] or "unknown"
        day_str = row["day"].isoformat()
        val = row["value"] or 0

        if key not in key_labels:
            if label_field:
                key_labels[key] = row.get("label_val") or key
            elif label_fn:
                key_labels[key] = label_fn(key)
            else:
                key_labels[key] = key

        date_data[day_str][key] = val

    series = [{"key": k, "label": v} for k, v in key_labels.items()]
    all_keys = list(key_labels.keys())

    data = []
    for day_str in sorted(date_data.keys()):
        row = {"date": day_str}
        for k in all_keys:
            row[k] = date_data[day_str].get(k, 0)
        data.append(row)

    return {"series": series, "data": data}


def _build_breakdown(base_qs, group_field, value_expr, label_fn=None):
    """Build breakdown list (for pie/donut charts)."""
    grouped = (
        base_qs.values(group_field)
        .annotate(value_micros=value_expr)
        .order_by("-value_micros")
    )

    total = sum((row["value_micros"] or 0) for row in grouped)
    items = []
    for row in grouped:
        key = row[group_field] or "ungrouped"
        val = row["value_micros"] or 0
        items.append({
            "key": key,
            "label": label_fn(key) if label_fn else key,
            "value_micros": val,
            "percentage": round(val / total * 100, 1) if total else 0.0,
        })
    return items


@platform_api.get("/dashboard/customers", response=DashboardCustomersResponse)
def dashboard_customers(request, range: str = "30d"):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    start_dt, end_dt, _, _ = _parse_range(range)

    qs = (
        UsageEvent.objects.filter(
            tenant=tenant,
            effective_at__gte=start_dt,
            effective_at__lte=end_dt,
        )
        .values("customer_id", "customer__external_id")
        .annotate(
            revenue_micros=Sum(Coalesce("billed_cost_micros", "cost_micros")),
            api_costs_micros=Sum("provider_cost_micros"),
            event_count=Count("id"),
        )
        .order_by("-revenue_micros")[:50]
    )

    customers = []
    for row in qs:
        r = row["revenue_micros"] or 0
        c = row["api_costs_micros"] or 0
        m = r - c
        customers.append({
            "customer_id": str(row["customer_id"]),
            "external_id": row["customer__external_id"],
            "revenue_micros": r,
            "api_costs_micros": c,
            "margin_micros": m,
            "margin_percentage": round(m / r * 100, 1) if r else 0.0,
            "event_count": row["event_count"],
        })

    return {"customers": customers}


# ── Event management endpoints ──────────────────────────────────────────


@platform_api.get("/events/filter-options", response=EventFilterOptionsResponse)
def event_filter_options(request):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    base_qs = UsageEvent.objects.filter(tenant=tenant)

    customers = list(
        base_qs.values("customer__external_id")
        .annotate(event_count=Count("id"))
        .order_by("-event_count")
    )
    groups = list(
        base_qs.exclude(Q(group__isnull=True) | Q(group=""))
        .values("group")
        .annotate(event_count=Count("id"))
        .order_by("-event_count")
    )
    cards = list(
        base_qs.filter(card__isnull=False)
        .values("card__slug")
        .annotate(event_count=Count("id"))
        .order_by("-event_count")
    )
    ungrouped_count = base_qs.filter(Q(group__isnull=True) | Q(group="")).count()

    # Card dimensions and dimension prices from Card/Rate models
    active_cards = Card.objects.filter(
        tenant=tenant, status__in=["active", "draft"]
    ).prefetch_related("rates")
    card_dimensions = {}
    dimension_prices = {}
    for card in active_cards:
        active_rates = card.rates.filter(valid_to__isnull=True)
        card_dimensions[card.slug] = [r.metric_name for r in active_rates]
        for r in active_rates:
            dimension_prices[r.metric_name] = {
                "cost_per_unit_micros": r.cost_per_unit_micros,
                "unit_quantity": r.unit_quantity,
                "pricing_type": r.pricing_type,
            }

    return {
        "customers": [
            {"key": row["customer__external_id"], "event_count": row["event_count"]}
            for row in customers
        ],
        "groups": [
            {"key": row["group"], "event_count": row["event_count"]}
            for row in groups
        ],
        "cards": [
            {"key": row["card__slug"], "event_count": row["event_count"]}
            for row in cards
        ],
        "ungrouped_count": ungrouped_count,
        "card_dimensions": card_dimensions,
        "dimension_prices": dimension_prices,
    }


@platform_api.post("/events/list", response=EventsListResponse)
def list_events(request, payload: EventsListRequest):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    limit = min(max(payload.limit, 1), 100)

    qs = (
        UsageEvent.objects.filter(tenant=tenant)
        .select_related("customer", "card")
        .order_by("-effective_at", "-id")
    )

    if payload.date_from:
        qs = qs.filter(effective_at__date__gte=payload.date_from)
    if payload.date_to:
        qs = qs.filter(effective_at__date__lte=payload.date_to)
    if payload.customer_id:
        qs = qs.filter(customer_id=payload.customer_id)
    if payload.group:
        qs = qs.filter(group=payload.group)
    if payload.card_slug:
        qs = qs.filter(card__slug=payload.card_slug)

    # Total count and cost before pagination
    agg = qs.aggregate(
        total_count=Count("id"),
        total_cost_micros=Coalesce(Sum(Coalesce("billed_cost_micros", "cost_micros")), 0),
    )

    if payload.cursor:
        try:
            qs = apply_cursor_filter(qs, payload.cursor, time_field="effective_at")
        except ValueError:
            raise HttpError(400, "Invalid cursor")

    events = list(qs[: limit + 1])
    has_more = len(events) > limit
    events = events[:limit]

    next_cursor = None
    if has_more and events:
        last = events[-1]
        next_cursor = encode_cursor(last.effective_at, last.id)

    return {
        "events": [
            {
                "id": str(e.id),
                "effective_at": e.effective_at.isoformat(),
                "customer_id": str(e.customer_id),
                "customer_external_id": e.customer.external_id,
                "group": e.group or "",
                "card_id": str(e.card_id) if e.card_id else None,
                "card_slug": e.card_slug or (e.card.slug if e.card else None),
                "card_name": e.card_name or (e.card.name if e.card else None),
                "provider": e.provider,
                "usage_metrics": e.usage_metrics,
                "provider_cost_micros": e.provider_cost_micros,
                "billed_cost_micros": e.billed_cost_micros,
            }
            for e in events
        ],
        "total_count": agg["total_count"],
        "total_cost_micros": agg["total_cost_micros"],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@platform_api.post("/events/push", response=PushEventsResponse)
def push_events(request, payload: PushEventsRequest):
    _require_tenant_user(request)
    tenant = request.auth.tenant

    batch = EventBatch.objects.create(
        tenant=tenant,
        action="added",
        reason=payload.reason,
        row_count=0,
        author=str(request.auth.id) if hasattr(request.auth, "id") else "api",
    )

    pushed = 0
    errors = []
    pricing_error_count = 0
    for i, staged in enumerate(payload.events):
        customer = Customer.objects.filter(
            tenant=tenant, external_id=staged.customer_external_id
        ).first()
        if not customer:
            continue

        idem_key = staged.idempotency_key or f"batch_{batch.id}_{i}"

        try:
            result = UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id=f"batch_{batch.id}_{i}",
                idempotency_key=idem_key,
                usage_metrics=staged.usage_metrics,
                group=staged.group or None,
                pricing_card=staged.pricing_card,
            )
        except (PricingError, ValueError) as e:
            errors.append({"index": i, "error": str(e)})
            pricing_error_count += 1
            continue

        # Link event to batch (UsageEvent is immutable so use .update())
        UsageEvent.objects.filter(id=result["event_id"]).update(batch=batch)
        pushed += 1

    batch.row_count = pushed
    batch.save(update_fields=["row_count", "updated_at"])

    if errors and pushed == 0 and pricing_error_count == len(payload.events):
        raise HttpError(422, f"All events failed: {errors[0]['error']}")

    return {"pushed_count": pushed, "batch_id": str(batch.id), "errors": errors}


@platform_api.get("/events/audit-trail", response=list[EventBatchOut])
def event_audit_trail(request):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    batches = EventBatch.objects.filter(tenant=tenant).order_by("-created_at")[:50]
    return [
        {
            "id": str(b.id),
            "action": b.action,
            "reason": b.reason,
            "row_count": b.row_count,
            "author": b.author,
            "created_at": b.created_at.isoformat(),
            "reversed_at": b.reversed_at.isoformat() if b.reversed_at else None,
        }
        for b in batches
    ]


@platform_api.post("/events/audit-trail/{batch_id}/reverse")
def reverse_audit_entry(request, batch_id: str):
    _require_tenant_user(request)
    from django.db import transaction
    from apps.metering.usage.models import Refund
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction

    tenant = request.auth.tenant
    batch = get_object_or_404(EventBatch, id=batch_id, tenant=tenant)

    if batch.reversed_at:
        raise HttpError(400, "Batch already reversed")

    events = list(UsageEvent.objects.filter(batch=batch).select_related("customer"))

    with transaction.atomic():
        for event in events:
            try:
                event.refund  # noqa: B018 -- check if refund already exists
            except Refund.DoesNotExist:
                # Fix: use explicit None-check so zero-cost events are handled correctly
                refund_amount = (
                    event.billed_cost_micros
                    if event.billed_cost_micros is not None
                    else event.cost_micros
                )
                Refund.objects.create(
                    tenant=tenant,
                    customer=event.customer,
                    usage_event=event,
                    amount_micros=refund_amount,
                    reason=f"Batch reversal: {batch.reason}",
                )
                # Credit the wallet for the refunded amount
                if refund_amount:
                    wallet, _ = lock_for_billing(event.customer_id)
                    wallet.balance_micros += refund_amount
                    wallet.save(update_fields=["balance_micros", "updated_at"])
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type="REFUND",
                        amount_micros=refund_amount,
                        balance_after_micros=wallet.balance_micros,
                        description=f"Batch reversal: {batch.reason}",
                        reference_id=str(event.id),
                    )

        batch.reversed_at = timezone.now()
        batch.save(update_fields=["reversed_at", "updated_at"])

    return {"status": "reversed", "batch_id": str(batch.id)}


@platform_api.post("/events/export")
def export_events(request, payload: EventsListRequest):
    _require_tenant_user(request)
    tenant = request.auth.tenant
    qs = (
        UsageEvent.objects.filter(tenant=tenant)
        .select_related("customer", "card")
        .order_by("-effective_at")
    )

    if payload.date_from:
        qs = qs.filter(effective_at__date__gte=payload.date_from)
    if payload.date_to:
        qs = qs.filter(effective_at__date__lte=payload.date_to)
    if payload.customer_id:
        qs = qs.filter(customer_id=payload.customer_id)
    if payload.group:
        qs = qs.filter(group=payload.group)
    if payload.card_slug:
        qs = qs.filter(card__slug=payload.card_slug)

    events = qs[:50_000]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "effective_at", "customer_external_id", "group", "card_slug",
        "provider", "usage_metrics", "provider_cost_micros",
        "billed_cost_micros",
    ])
    for e in events:
        writer.writerow([
            str(e.id),
            e.effective_at.isoformat(),
            e.customer.external_id,
            e.group or "",
            e.card_slug or (e.card.slug if e.card else ""),
            e.provider,
            str(e.usage_metrics),
            e.provider_cost_micros,
            e.billed_cost_micros,
        ])

    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="events_export.csv"'
    return response


# --- Tenant default margin (UX default for card creation wizard) ---


@platform_api.get("/tenant/default-margin", response=TenantDefaultMarginResponse)
def get_default_margin(request):
    _require_tenant_user(request)
    t = request.auth.tenant
    return {"default_margin_pct": float(t.default_margin_pct)}


@platform_api.patch("/tenant/default-margin", response=TenantDefaultMarginResponse)
def update_default_margin(request, payload: UpdateTenantDefaultMarginRequest):
    _require_tenant_user(request)
    t = request.auth.tenant
    t.default_margin_pct = payload.default_margin_pct
    t.save(update_fields=["default_margin_pct", "updated_at"])
    return {"default_margin_pct": float(t.default_margin_pct)}
