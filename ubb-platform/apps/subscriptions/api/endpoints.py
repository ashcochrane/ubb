import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from ninja import Router

from apps.billing.stripe.models import WEBHOOK_RECEIVER_SUBSCRIPTIONS
from apps.billing.stripe.receiver import receive_stripe_event
from core.identifiers import UUIDIdentifier
from core.problems import Problem, ProblemOut

from core.pagination import paginate
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import PaymentRailClosed
from apps.platform.plans import queries as plan_queries
from apps.subscriptions.api.schemas import (
    SyncResponse,
    StripeSubscriptionOut,
    PaginatedInvoicesResponse,
    SeatsIn,
    SubscribeIn,
    SubscriptionCancelIn,
)
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from core.auth import ApiKeyAuth, ProductAccess, READ, WRITE, role_floor

subscriptions_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("billing")


# ---------- Sync ----------


@subscriptions_router.post("/sync", response=SyncResponse)
@role_floor(WRITE)
def trigger_sync(request):
    _product_check(request)
    from apps.subscriptions.stripe.sync import sync_subscriptions

    result = sync_subscriptions(request.auth.tenant)
    return result


# ---------- Subscription Data (read-only) ----------


@subscriptions_router.get(
    "/customers/{customer_id}/subscription",
    response={200: StripeSubscriptionOut, 404: ProblemOut},
)
@role_floor(READ)
def get_subscription(request, customer_id: UUIDIdentifier):
    _product_check(request)
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)

    sub = StripeSubscription.objects.filter(
        tenant=tenant, customer=customer,
    ).order_by("-created_at").first()

    if not sub:
        raise Problem("not_found", "No subscription for this customer")

    return {
        "id": str(sub.id),
        "stripe_subscription_id": sub.stripe_subscription_id,
        "stripe_product_name": sub.stripe_product_name,
        "status": sub.status,
        "amount_micros": sub.amount_micros,
        "currency": sub.currency,
        "source_amount_minor": sub.source_amount_minor,
        "interval": sub.interval,
        "current_period_start": sub.current_period_start.isoformat(),
        "current_period_end": sub.current_period_end.isoformat(),
        "last_synced_at": sub.last_synced_at.isoformat(),
    }


@subscriptions_router.get(
    "/customers/{customer_id}/invoices",
    response={200: PaginatedInvoicesResponse, 400: ProblemOut, 404: ProblemOut},
)
@role_floor(READ)
def get_invoices(request, customer_id: UUIDIdentifier, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)

    # Only paid invoices surface here (this is the revenue listing). Since the AR
    # reconcile now also persists open/void/uncollectible rows with a NULL paid_at,
    # exclude them — they have no paid_at to order/serialize on.
    invoices, next_cursor, has_more = paginate(
        SubscriptionInvoice.objects.filter(
            tenant=tenant, customer=customer, paid_at__isnull=False),
        cursor, limit, time_field="paid_at")

    return {
        "data": [
            {
                "id": str(inv.id),
                "stripe_invoice_id": inv.stripe_invoice_id,
                "amount_paid_micros": inv.amount_paid_micros,
                "currency": inv.currency,
                "source_amount_paid_minor": inv.source_amount_paid_minor,
                "period_start": inv.period_start.isoformat(),
                "period_end": inv.period_end.isoformat(),
                "paid_at": inv.paid_at.isoformat(),
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ---------- Stripe Webhook ----------

logger = logging.getLogger(__name__)

from apps.subscriptions.api.webhooks import (
    handle_subscription_created,
    handle_subscription_updated,
    handle_subscription_deleted,
)
from core.vocabulary import (
    AUDIT_ACTION_PLAN_ASSIGNED,
    AUDIT_ACTION_SUBSCRIPTION_CANCELED,
    AUDIT_ACTION_SUBSCRIPTION_CREATED,
    AUDIT_ACTION_SUBSCRIPTION_PAUSED,
    AUDIT_ACTION_SUBSCRIPTION_RESUMED,
    AUDIT_ACTION_SUBSCRIPTION_SEATS_CHANGED,
    AUDIT_RESOURCE_TYPE_CUSTOMER,
    AUDIT_RESOURCE_TYPE_SUBSCRIPTION,
)

# This endpoint handles customer.subscription.* ONLY. ALL invoice.* reconcile
# (including subscription-invoice status) lives on api/v1 — see api/v1/webhooks.py.
# Since C1b (F-17) the dedup table is scoped PER RECEIVER, so a type registered
# on both endpoints is processed by its owner and recorded `skipped` by the
# other, independently; keep the maps disjoint anyway — one owner per type.
SUBSCRIPTIONS_WEBHOOK_HANDLERS = {
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}


@csrf_exempt
@require_POST
def subscriptions_stripe_webhook(request):
    """Stripe LIVE-mode webhook endpoint — the SUBSCRIPTIONS receiver.

    This is the authoritative seat-quantity confirm path for Wave-4 orchestration,
    so it must process each Stripe event at most once. The body is the shared
    receiver core (`apps/billing/stripe/receiver.py`, C1b): get_or_create +
    IntegrityError fallback + CAS-guarded retry of retryable failures / stale
    processing, deduplicated per receiver.

    Verified with THIS receiver's own secret, STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET
    (R-3: each live endpoint registered with Stripe has its own signing secret).
    Fails closed on an unset or blank one, as the billing receiver does
    (W7 preparation finding F5): an empty secret must never verify. There is
    NO fallback to STRIPE_WEBHOOK_SECRET — the billing receiver's secret does
    not verify deliveries to this endpoint. Refused before anything is verified
    or persisted.
    """
    secret = getattr(settings, "STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET", "")
    if not (secret or "").strip():
        return HttpResponse(status=400)
    return _subscriptions_stripe_webhook(request, secret=secret, is_test_endpoint=False)


@csrf_exempt
@require_POST
def subscriptions_stripe_webhook_test(request):
    """Stripe TEST-mode subscriptions webhook (F4.4) — sandbox tenants' events.

    Verified with STRIPE_SUBSCRIPTIONS_TEST_WEBHOOK_SECRET (this receiver's own
    test-mode secret, never the billing receiver's); 400 when it is unset or
    blank or the event is livemode=True. Same handlers — the livemode filters
    inside them bind every lookup to sandbox tenants.
    """
    secret = getattr(settings, "STRIPE_SUBSCRIPTIONS_TEST_WEBHOOK_SECRET", "")
    if not (secret or "").strip():
        return HttpResponse(status=400)
    return _subscriptions_stripe_webhook(request, secret=secret, is_test_endpoint=True)


def _subscriptions_stripe_webhook(request, *, secret, is_test_endpoint):
    return receive_stripe_event(
        request, receiver=WEBHOOK_RECEIVER_SUBSCRIPTIONS,
        handlers=SUBSCRIPTIONS_WEBHOOK_HANDLERS, secret=secret,
        is_test_endpoint=is_test_endpoint,
        # This receiver never moves wallet money, so a wallet-subject refusal
        # here is not a named outcome: it takes the core's generic arm.
        refuses_without_a_wallet_subject=False)


# ---------- Lifecycle (moved from platform_router, design doc §6) ----------

_LIFECYCLE_AUDIT_ACTION = {
    "cancel": AUDIT_ACTION_SUBSCRIPTION_CANCELED,
    "pause": AUDIT_ACTION_SUBSCRIPTION_PAUSED,
    "resume": AUDIT_ACTION_SUBSCRIPTION_RESUMED,
}


def _lifecycle_call(request, external_id, verb_kwargs):
    """Shared problem mapping for the subscription lifecycle verbs."""
    from apps.subscriptions.orchestration.service import (
        NoActiveSubscription, OrchestrationError, SubscriptionOrchestrator,
    )
    from core.exceptions import StripeFatalError

    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    verb = verb_kwargs.pop("verb")
    change_event_id = str(uuid.uuid4())
    try:
        mirror = getattr(SubscriptionOrchestrator, verb)(
            tenant, customer, change_event_id=change_event_id, **verb_kwargs)
    except NoActiveSubscription as e:
        raise Problem("not_found", str(e))
    except PaymentRailClosed:
        raise  # G27, answered by name (`problems.py`)
    except (OrchestrationError, StripeFatalError) as e:
        raise Problem("validation_error", str(e))

    audit_record(
        action=_LIFECYCLE_AUDIT_ACTION[verb], tenant_id=tenant.id,
        resource_type=AUDIT_RESOURCE_TYPE_SUBSCRIPTION, resource_id=mirror.stripe_subscription_id,
        metadata={"external_id": customer.external_id, "status": mirror.status,
                  "cancel_at_period_end": mirror.cancel_at_period_end,
                  "paused": mirror.paused, "change_event_id": change_event_id})
    return 200, {
        "subscription_id": mirror.stripe_subscription_id,
        "status": mirror.status,
        "cancel_at_period_end": mirror.cancel_at_period_end,
        "paused": mirror.paused,
    }


@subscriptions_router.post("/customers/{external_id}/subscribe",
                           response={200: dict, 404: ProblemOut, 409: ProblemOut,
                                     422: ProblemOut})
@role_floor(WRITE)
@records_audit(AUDIT_ACTION_PLAN_ASSIGNED, AUDIT_ACTION_SUBSCRIPTION_CREATED)
def subscribe_customer(request, external_id: str, payload: SubscribeIn):
    """Assign the customer to the plan and, if the plan has fee axes, start the
    Stripe subscription.

    A markup-only plan assigns and returns subscription_id=None — there is
    nothing for Stripe to bill.
    """
    from apps.platform.plans.services import PlanService
    from apps.subscriptions.orchestration.service import (
        OrchestrationError, SubscriptionOrchestrator,
    )
    from core.exceptions import StripeFatalError

    _product_check(request)
    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    plan = plan_queries.get_plan_by_key(tenant.id, payload.plan_key)
    if plan is None or plan.archived_at is not None:
        raise Problem("not_found", f"plan with key '{payload.plan_key}' not found")

    # PlanService.assign is a pure-DB operation (no Stripe call): commit it and
    # its audit entry together, before the Stripe branch runs (mirrors
    # POST /plans/customers/{external_id}/plan). The assignment's fate must
    # never depend on what the Stripe call below does next — a subscribe
    # failure below must not silently drop this already-durable change from
    # the audit trail.
    with transaction.atomic():
        PlanService.assign(tenant, customer, plan)
        audit_record(
            action=AUDIT_ACTION_PLAN_ASSIGNED, tenant_id=tenant.id,
            resource_type=AUDIT_RESOURCE_TYPE_CUSTOMER, resource_id=customer.external_id,
            metadata={"external_id": customer.external_id, "plan_key": plan.key})

    try:
        mirror = SubscriptionOrchestrator.subscribe(customer, plan, payload.seats)
    except PaymentRailClosed:
        raise  # G27, answered by name (`problems.py`)
    except (OrchestrationError, StripeFatalError) as e:
        raise Problem("validation_error", str(e))

    if mirror is None:
        # Markup-only plan: nothing for Stripe to bill, so there is no Stripe
        # object to audit — the assignment above already recorded the change.
        return 200, {"subscription_id": None, "amount_micros": 0, "quantity": 0}

    # Recorded after the orchestrator commits (it owns its transaction + a
    # Stripe call — a DB transaction can't wrap the external call).
    audit_record(
        action=AUDIT_ACTION_SUBSCRIPTION_CREATED, tenant_id=tenant.id,
        resource_type=AUDIT_RESOURCE_TYPE_SUBSCRIPTION, resource_id=mirror.stripe_subscription_id,
        metadata={"external_id": customer.external_id, "plan_key": plan.key,
                  "seats": payload.seats, "quantity": mirror.quantity,
                  "amount_micros": mirror.amount_micros})
    return 200, {
        "subscription_id": mirror.stripe_subscription_id,
        "amount_micros": mirror.amount_micros,
        "quantity": mirror.quantity,
    }


@subscriptions_router.post("/customers/{external_id}/seats",
                           response={200: dict, 404: ProblemOut, 409: ProblemOut,
                                     422: ProblemOut})
@role_floor(WRITE)
@records_audit(AUDIT_ACTION_SUBSCRIPTION_SEATS_CHANGED)
def set_customer_seats(request, external_id: str, payload: SeatsIn):
    from apps.subscriptions.models import CustomerSubscriptionItem
    from apps.subscriptions.orchestration.service import (
        OrchestrationError, SubscriptionOrchestrator,
    )

    _product_check(request)
    tenant = request.auth.tenant
    customer = Customer.objects.filter(tenant=tenant, external_id=external_id).first()
    if customer is None:
        raise Problem("not_found", "customer not found")

    business = customer.resolve_billing_owner()
    seat_item = (
        CustomerSubscriptionItem.objects.filter(customer=business, axis="seat")
        .order_by("-created_at").first()
    )
    if seat_item is None or seat_item.plan is None:
        raise Problem("not_found", "no seat subscription item for this customer")

    change_event_id = str(uuid.uuid4())
    try:
        SubscriptionOrchestrator.set_seats(
            business, seat_item.plan, payload.seats, change_event_id=change_event_id)
    except OrchestrationError as e:
        raise Problem("validation_error", str(e))

    audit_record(
        action=AUDIT_ACTION_SUBSCRIPTION_SEATS_CHANGED, tenant_id=tenant.id,
        resource_type=AUDIT_RESOURCE_TYPE_SUBSCRIPTION, resource_id=business.external_id,
        metadata={"external_id": business.external_id, "seats": payload.seats,
                  "change_event_id": change_event_id})
    return 200, {"seats": payload.seats}


@subscriptions_router.post("/customers/{external_id}/subscription/cancel",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit(AUDIT_ACTION_SUBSCRIPTION_CANCELED)
def cancel_subscription(request, external_id: str, payload: SubscriptionCancelIn = None):
    """Cancel the customer's subscription (default: at period end).

    Trials and coupons are deliberate non-goals: Stripe owns those levers.
    """
    _product_check(request)
    at_period_end = payload.at_period_end if payload is not None else True
    return _lifecycle_call(request, external_id,
                           {"verb": "cancel", "at_period_end": at_period_end})


@subscriptions_router.post("/customers/{external_id}/subscription/pause",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit(AUDIT_ACTION_SUBSCRIPTION_PAUSED)
def pause_subscription(request, external_id: str):
    """Pause collection (void) — the subscription stays active but stops billing."""
    _product_check(request)
    return _lifecycle_call(request, external_id, {"verb": "pause"})


@subscriptions_router.post("/customers/{external_id}/subscription/resume",
                           response={200: dict, 404: ProblemOut, 409: ProblemOut,
                                     422: ProblemOut})
@role_floor(WRITE)
@records_audit(AUDIT_ACTION_SUBSCRIPTION_RESUMED)
def resume_subscription(request, external_id: str):
    """Resume billing: clears a pause AND any pending at-period-end cancel."""
    _product_check(request)
    return _lifecycle_call(request, external_id, {"verb": "resume"})
