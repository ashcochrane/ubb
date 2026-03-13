from typing import Optional

from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Schema

from api.v1.pagination import apply_cursor_filter, encode_cursor
from core.auth import ApiKeyAuth
from core.clerk_auth import ClerkJWTAuth
from apps.platform.customers.models import Customer


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
