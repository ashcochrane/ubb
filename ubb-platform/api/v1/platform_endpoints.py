from typing import Optional

from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Schema

from api.v1.pagination import apply_cursor_filter, encode_cursor
from api.v1.schemas import CreateGroupRequest, UpdateGroupRequest, GroupResponse, GroupListResponse
from core.auth import ApiKeyAuth
from core.clerk_auth import ClerkJWTAuth
from apps.platform.customers.models import Customer
from apps.platform.groups.models import Group
from apps.billing.wallets.models import Wallet


class CreateCustomerRequest(Schema):
    external_id: str
    stripe_customer_id: str = ""
    metadata: dict = {}


class UpdateCustomerRequest(Schema):
    status: Optional[str] = None
    metadata: Optional[dict] = None
    stripe_customer_id: Optional[str] = None
    min_balance_micros: Optional[int] = None


class CustomerResponse(Schema):
    id: str
    external_id: str
    stripe_customer_id: str
    status: str


class CustomerDetailResponse(Schema):
    id: str
    external_id: str
    stripe_customer_id: str
    status: str
    metadata: dict
    min_balance_micros: Optional[int] = None
    created_at: str
    updated_at: str


class CustomerListResponse(Schema):
    data: list[CustomerDetailResponse]
    next_cursor: Optional[str] = None
    has_more: bool


platform_api = NinjaAPI(auth=[ApiKeyAuth(), ClerkJWTAuth()], urls_namespace="ubb_platform_v1")


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
    customer = get_object_or_404(
        Customer, id=customer_id, tenant=request.auth.tenant
    )
    return _customer_to_detail(customer)


@platform_api.patch("/customers/{customer_id}", response=CustomerDetailResponse)
def update_customer(request, customer_id: str, payload: UpdateCustomerRequest):
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
    customer = get_object_or_404(
        Customer, id=customer_id, tenant=request.auth.tenant
    )
    customer.soft_delete()
    return platform_api.create_response(request, "", status=204)


@platform_api.get("/wallets")
def list_wallets(request, max_balance_micros: int = None, cursor: str = None, limit: int = 50):
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
    group = get_object_or_404(
        Group, id=group_id, tenant=request.auth.tenant
    )
    return _group_to_response(group)


@platform_api.patch("/groups/{group_id}", response=GroupResponse)
def update_group(request, group_id: str, payload: UpdateGroupRequest):
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
    group = get_object_or_404(
        Group, id=group_id, tenant=request.auth.tenant
    )
    group.status = "archived"
    group.save(update_fields=["status", "updated_at"])
    return _group_to_response(group)
