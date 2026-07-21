import uuid

from django.db import IntegrityError
from ninja import Router, Schema

from core.auth import ADMIN, ApiKeyAuth, READ, WRITE, role_floor
from core.problems import Problem, ProblemOut
from apps.platform.customers.models import Customer
from api.v1.schemas import (
    PlanIn,
    PlanOut,
    PlanUpdateIn,
    SeatsIn,
    SubscribeIn,
    SubscriptionCancelIn,
)


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


platform_router = Router(auth=ApiKeyAuth())


@platform_router.post("/customers", response={201: CustomerResponse, 409: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
def create_customer(request, payload: CreateCustomerRequest):
    tenant = request.auth.tenant
    at = payload.account_type or "individual"
    if at not in ("individual", "business", "seat"):
        raise Problem("validation_error", f"invalid account_type {at}")
    parent = None
    topology = ""
    if at == "seat":
        if not payload.parent_external_id:
            raise Problem("validation_error", "seat requires parent_external_id")
        parent = Customer.objects.filter(
            tenant=tenant, external_id=payload.parent_external_id, account_type="business"
        ).first()
        if parent is None:
            raise Problem("validation_error", "parent business not found")
    elif at == "business":
        if payload.billing_topology not in ("pooled", "allocated"):
            raise Problem("validation_error",
                          "business requires billing_topology pooled|allocated")
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
        raise Problem("conflict", "customer with this external_id already exists")


@platform_router.get("/accounts/business/{external_id}", response={200: dict, 404: ProblemOut})
@role_floor(READ)
def get_business(request, external_id: str):
    from apps.billing.wallets.models import Wallet

    biz = Customer.objects.filter(
        tenant=request.auth.tenant, external_id=external_id, account_type="business"
    ).first()
    if biz is None:
        raise Problem("not_found", "business not found")
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
    }


@platform_router.post("/plans", response={201: PlanOut, 409: ProblemOut})
@role_floor(ADMIN)
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
        )
    except IntegrityError:
        raise Problem("conflict", f"plan with key '{payload.key}' already exists")
    return 201, _plan_out(plan)


@platform_router.patch("/plans/{key}", response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
def update_plan(request, key: str, payload: PlanUpdateIn):
    """Edit plan fees (F5.4). Provisioned axes get a NEW versioned Stripe Price;
    existing subscriptions are grandfathered on their old price unless
    migrate_existing=true (repointed with proration_behavior="none").

    Trials and coupons are deliberate non-goals: Stripe owns those levers.
    """
    from apps.subscriptions.models import TenantBillingPlan
    from apps.subscriptions.orchestration.service import (
        SubscriptionOrchestrator,
        OrchestrationError,
    )
    from core.exceptions import StripeFatalError

    tenant = request.auth.tenant
    if not TenantBillingPlan.objects.filter(tenant=tenant, key=key).exists():
        raise Problem("not_found", f"plan with key '{key}' not found")

    try:
        plan = SubscriptionOrchestrator.update_plan_prices(
            tenant, key,
            access_fee_micros=payload.access_fee_micros,
            per_seat_micros=payload.per_seat_micros,
            migrate_existing=payload.migrate_existing,
        )
    except OrchestrationError as e:
        raise Problem("validation_error", str(e))
    except StripeFatalError as e:
        raise Problem("validation_error", str(e))

    return 200, {**_plan_out(plan), "pricing_version": plan.pricing_version}


def _lifecycle_call(request, external_id, verb_kwargs):
    """Shared problem mapping for the subscription lifecycle verbs (F5.4)."""
    from apps.subscriptions.orchestration.service import (
        SubscriptionOrchestrator,
        OrchestrationError,
        NoActiveSubscription,
    )
    from core.exceptions import StripeFatalError

    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    verb = verb_kwargs.pop("verb")
    try:
        mirror = getattr(SubscriptionOrchestrator, verb)(
            tenant, customer, change_event_id=str(uuid.uuid4()), **verb_kwargs
        )
    except NoActiveSubscription as e:
        raise Problem("not_found", str(e))
    except OrchestrationError as e:
        raise Problem("validation_error", str(e))
    except StripeFatalError as e:
        raise Problem("validation_error", str(e))

    return 200, {
        "subscription_id": mirror.stripe_subscription_id,
        "status": mirror.status,
        "cancel_at_period_end": mirror.cancel_at_period_end,
        "paused": mirror.paused,
    }


@platform_router.post(
    "/customers/{external_id}/subscription/cancel",
    response={200: dict, 404: ProblemOut, 422: ProblemOut},
)
@role_floor(WRITE)
def cancel_subscription(request, external_id: str, payload: SubscriptionCancelIn = None):
    """Cancel the customer's subscription (default: at period end).

    Trials and coupons are deliberate non-goals: Stripe owns those levers.
    """
    at_period_end = payload.at_period_end if payload is not None else True
    return _lifecycle_call(request, external_id,
                           {"verb": "cancel", "at_period_end": at_period_end})


@platform_router.post(
    "/customers/{external_id}/subscription/pause",
    response={200: dict, 404: ProblemOut, 422: ProblemOut},
)
@role_floor(WRITE)
def pause_subscription(request, external_id: str):
    """Pause collection (void) — the subscription stays active but stops billing.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.
    """
    return _lifecycle_call(request, external_id, {"verb": "pause"})


@platform_router.post(
    "/customers/{external_id}/subscription/resume",
    response={200: dict, 404: ProblemOut, 422: ProblemOut},
)
@role_floor(WRITE)
def resume_subscription(request, external_id: str):
    """Resume billing: clears a pause AND any pending at-period-end cancel.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.
    """
    return _lifecycle_call(request, external_id, {"verb": "resume"})


@platform_router.post("/customers/{external_id}/subscribe", response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
def subscribe_customer(request, external_id: str, payload: SubscribeIn):
    from apps.subscriptions.models import TenantBillingPlan
    from apps.subscriptions.orchestration.service import (
        SubscriptionOrchestrator,
        OrchestrationError,
    )

    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    plan = TenantBillingPlan.objects.filter(tenant=tenant, key=payload.plan_key).first()
    if plan is None:
        raise Problem("not_found", f"plan with key '{payload.plan_key}' not found")

    from core.exceptions import StripeFatalError
    try:
        mirror = SubscriptionOrchestrator.subscribe(customer, plan, payload.seats)
    except OrchestrationError as e:
        raise Problem("validation_error", str(e))
    except StripeFatalError as e:
        # F5.3: a non-retryable Stripe rejection (e.g. automatic_tax enabled
        # but Stripe Tax not configured on the connected account) is a tenant
        # config problem — surface Stripe's message as 422, not a 500.
        raise Problem("validation_error", str(e))

    return 200, {
        "subscription_id": mirror.stripe_subscription_id,
        "amount_micros": mirror.amount_micros,
        "quantity": mirror.quantity,
    }


@platform_router.post("/customers/{external_id}/seats", response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
def set_customer_seats(request, external_id: str, payload: SeatsIn):
    from apps.subscriptions.models import CustomerSubscriptionItem
    from apps.subscriptions.orchestration.service import (
        SubscriptionOrchestrator,
        OrchestrationError,
    )

    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    business = customer.resolve_billing_owner()
    seat_item = (
        CustomerSubscriptionItem.objects.filter(customer=business, axis="seat")
        .order_by("-created_at")
        .first()
    )
    if seat_item is None or seat_item.plan is None:
        raise Problem("not_found", "no seat subscription item for this customer")

    change_event_id = str(uuid.uuid4())
    try:
        SubscriptionOrchestrator.set_seats(
            business, seat_item.plan, payload.seats, change_event_id=change_event_id
        )
    except OrchestrationError as e:
        raise Problem("validation_error", str(e))

    return 200, {"seats": payload.seats}
