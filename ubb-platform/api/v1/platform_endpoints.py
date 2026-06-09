from django.db import IntegrityError
from ninja import NinjaAPI, Schema

from core.auth import ApiKeyAuth
from apps.platform.customers.models import Customer


class CreateCustomerRequest(Schema):
    external_id: str
    stripe_customer_id: str = ""
    metadata: dict = {}
    account_type: str = "individual"
    parent_external_id: str = ""
    billing_topology: str = ""


class CustomerResponse(Schema):
    id: str
    external_id: str
    stripe_customer_id: str
    status: str


platform_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_platform_v1")


@platform_api.post("/customers", response={201: CustomerResponse, 409: dict, 422: dict})
def create_customer(request, payload: CreateCustomerRequest):
    tenant = request.auth.tenant
    at = payload.account_type or "individual"
    if at not in ("individual", "business", "seat"):
        return 422, {"error": f"invalid account_type {at}"}
    parent = None
    topology = ""
    if at == "seat":
        if not payload.parent_external_id:
            return 422, {"error": "seat requires parent_external_id"}
        parent = Customer.objects.filter(
            tenant=tenant, external_id=payload.parent_external_id, account_type="business"
        ).first()
        if parent is None:
            return 422, {"error": "parent business not found"}
    elif at == "business":
        if payload.billing_topology not in ("pooled", "allocated"):
            return 422, {"error": "business requires billing_topology pooled|allocated"}
        topology = payload.billing_topology
    try:
        customer = Customer.objects.create(
            tenant=tenant,
            external_id=payload.external_id,
            stripe_customer_id=payload.stripe_customer_id,
            metadata=payload.metadata,
            account_type=at,
            parent=parent,
            billing_topology=topology,
        )
        return 201, {
            "id": str(customer.id),
            "external_id": customer.external_id,
            "stripe_customer_id": customer.stripe_customer_id,
            "status": customer.status,
        }
    except IntegrityError:
        return 409, {"error": "Customer with this external_id already exists"}


@platform_api.get("/accounts/business/{external_id}", response={200: dict, 404: dict})
def get_business(request, external_id: str):
    from apps.billing.wallets.models import Wallet

    biz = Customer.objects.filter(
        tenant=request.auth.tenant, external_id=external_id, account_type="business"
    ).first()
    if biz is None:
        return 404, {"error": "business not found"}
    pooled_balance = None
    if biz.billing_topology == "pooled":
        w = Wallet.objects.filter(customer=biz).first()
        pooled_balance = w.balance_micros if w else 0
    seats = [
        {"external_id": s.external_id, "id": str(s.id), "status": s.status}
        for s in biz.seats.all().order_by("external_id")
    ]
    return 200, {
        "external_id": biz.external_id,
        "id": str(biz.id),
        "billing_topology": biz.billing_topology,
        "pooled_balance_micros": pooled_balance,
        "seats": seats,
    }
