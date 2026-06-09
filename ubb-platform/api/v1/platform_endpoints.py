import uuid

from django.db import IntegrityError
from ninja import NinjaAPI, Schema

from core.auth import ApiKeyAuth
from apps.platform.customers.models import Customer
from api.v1.schemas import PlanIn, PlanOut, SubscribeIn, SeatsIn


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
        from django.db import transaction
        with transaction.atomic():
            customer = Customer.objects.create(
                tenant=tenant,
                external_id=payload.external_id,
                stripe_customer_id=payload.stripe_customer_id,
                metadata=payload.metadata,
                account_type=at,
                parent=parent,
                billing_topology=topology,
            )
            # Roster grew: push the new live seat count to Stripe on commit so the
            # subscription's per-seat quantity stays in lock-step with the roster.
            if at == "seat" and parent is not None:
                from apps.subscriptions.orchestration.seats import sync_seat_quantity_on_commit
                sync_seat_quantity_on_commit(parent)
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


def _plan_out(plan):
    return {
        "id": str(plan.id),
        "key": plan.key,
        "name": plan.name,
        "access_fee_micros": plan.access_fee_micros,
        "per_seat_micros": plan.per_seat_micros,
        "interval": plan.interval,
        "usage_mode": plan.usage_mode,
    }


@platform_api.post("/plans", response={201: PlanOut, 422: dict})
def create_plan(request, payload: PlanIn):
    from apps.subscriptions.models import TenantBillingPlan

    try:
        plan = TenantBillingPlan.objects.create(
            tenant=request.auth.tenant,
            key=payload.key,
            name=payload.name,
            access_fee_micros=payload.access_fee_micros,
            per_seat_micros=payload.per_seat_micros,
            interval=payload.interval,
            usage_mode=payload.usage_mode,
        )
    except IntegrityError:
        return 422, {"error": f"plan with key '{payload.key}' already exists"}
    return 201, _plan_out(plan)


@platform_api.post("/customers/{external_id}/subscribe", response={200: dict, 404: dict, 422: dict})
def subscribe_customer(request, external_id: str, payload: SubscribeIn):
    from apps.subscriptions.models import TenantBillingPlan
    from apps.subscriptions.orchestration.service import (
        SubscriptionOrchestrator,
        OrchestrationError,
    )

    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        return 404, {"error": "customer not found"}

    plan = TenantBillingPlan.objects.filter(tenant=tenant, key=payload.plan_key).first()
    if plan is None:
        return 404, {"error": f"plan with key '{payload.plan_key}' not found"}

    try:
        mirror = SubscriptionOrchestrator.subscribe(customer, plan, payload.seats)
    except OrchestrationError as e:
        return 422, {"error": str(e)}

    return 200, {
        "subscription_id": mirror.stripe_subscription_id,
        "amount_micros": mirror.amount_micros,
        "quantity": mirror.quantity,
    }


@platform_api.post("/customers/{external_id}/seats", response={200: dict, 404: dict, 422: dict})
def set_customer_seats(request, external_id: str, payload: SeatsIn):
    from apps.subscriptions.models import CustomerSubscriptionItem
    from apps.subscriptions.orchestration.service import (
        SubscriptionOrchestrator,
        OrchestrationError,
    )

    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        return 404, {"error": "customer not found"}

    business = customer.resolve_billing_owner()
    seat_item = (
        CustomerSubscriptionItem.objects.filter(customer=business, axis="seat")
        .order_by("-created_at")
        .first()
    )
    if seat_item is None or seat_item.plan is None:
        return 404, {"error": "no seat subscription item for this customer"}

    change_event_id = str(uuid.uuid4())
    try:
        SubscriptionOrchestrator.set_seats(
            business, seat_item.plan, payload.seats, change_event_id=change_event_id
        )
    except OrchestrationError as e:
        return 422, {"error": str(e)}

    return 200, {"seats": payload.seats}
