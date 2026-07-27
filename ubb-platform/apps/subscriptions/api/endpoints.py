import logging
import uuid
from datetime import timedelta

import stripe
from stripe import SignatureVerificationError as StripeSignatureError

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from ninja import Router

from apps.billing.stripe.models import StripeWebhookEvent
from core.exceptions import StripeFatalError
from core.identifiers import UUIDIdentifier
from core.problems import Problem, ProblemOut

from core.pagination import paginate
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer
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

# This endpoint handles customer.subscription.* ONLY. ALL invoice.* reconcile
# (including subscription-invoice status) lives on api/v1 — see api/v1/webhooks.py.
# Never register an invoice.* type here: both endpoints share the
# StripeWebhookEvent dedup table, so the first to handle an event wins the dedup
# row and the second silently skips (C-1).
SUBSCRIPTIONS_WEBHOOK_HANDLERS = {
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}

PROCESSING_TTL_MINUTES = 30


@csrf_exempt
@require_POST
def subscriptions_stripe_webhook(request):
    """Stripe webhook endpoint for subscription events.

    This is the authoritative seat-quantity confirm path for Wave-4 orchestration,
    so it must process each Stripe event at most once. Deduplication mirrors the
    api/v1 webhook: StripeWebhookEvent get_or_create + IntegrityError fallback +
    CAS-guarded retry of retryable failures / stale processing.
    """
    secret = (
        settings.STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET
        if hasattr(settings, "STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET")
        else settings.STRIPE_WEBHOOK_SECRET
    )
    return _subscriptions_stripe_webhook(request, secret=secret, is_test_endpoint=False)


@csrf_exempt
@require_POST
def subscriptions_stripe_webhook_test(request):
    """Stripe TEST-mode subscriptions webhook (F4.4) — sandbox tenants' events.

    Verified with STRIPE_TEST_WEBHOOK_SECRET; 400 when that secret is unset or
    the event is livemode=True. Same handlers — the livemode filters inside
    them bind every lookup to sandbox tenants.
    """
    if not settings.STRIPE_TEST_WEBHOOK_SECRET:
        return HttpResponse(status=400)
    return _subscriptions_stripe_webhook(
        request, secret=settings.STRIPE_TEST_WEBHOOK_SECRET, is_test_endpoint=True)


def _subscriptions_stripe_webhook(request, *, secret, is_test_endpoint):
    from apps.billing.connectors.stripe.invoice_routing import reject_for_mode

    # 1. Verify signature
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, StripeSignatureError):
        return HttpResponse(status=400)

    # 1b. Mode gate (F4.4) — same policy as the api/v1 endpoint.
    if reject_for_mode(event, is_test_endpoint=is_test_endpoint):
        return HttpResponse(status=400)

    # 2. Event-level dedup with IntegrityError handling
    try:
        with transaction.atomic():
            webhook_event, created = StripeWebhookEvent.objects.get_or_create(
                stripe_event_id=event.id,
                defaults={"event_type": event.type, "status": "processing"},
            )
    except IntegrityError:
        StripeWebhookEvent.objects.filter(stripe_event_id=event.id).update(
            duplicate_count=F("duplicate_count") + 1,
            last_seen_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return JsonResponse({"status": "already_received"})

    if not created:
        processing_ttl = timezone.now() - timedelta(minutes=PROCESSING_TTL_MINUTES)

        # CAS: allow retry of retryable failures or stale processing
        if (
            (webhook_event.status == "failed"
             and webhook_event.failure_reason
             and webhook_event.failure_reason.get("retryable") is True)
            or (webhook_event.status == "processing"
                and webhook_event.updated_at < processing_ttl)
        ):
            rows_updated = StripeWebhookEvent.objects.filter(
                id=webhook_event.id,
                status=webhook_event.status,
                updated_at=webhook_event.updated_at,
            ).update(
                status="processing",
                failure_reason=None,
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            if rows_updated == 0:
                return JsonResponse({"status": "already_processing"})
            # Won CAS — fall through to handler
        else:
            StripeWebhookEvent.objects.filter(stripe_event_id=event.id).update(
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            return JsonResponse({"status": "already_processed"})

    # 3. Dispatch
    handler = SUBSCRIPTIONS_WEBHOOK_HANDLERS.get(event.type)
    if not handler:
        webhook_event.status = "skipped"
        webhook_event.save(update_fields=["status", "updated_at"])
        return JsonResponse({"status": "ok"})

    # 4. Execute with error classification
    try:
        handler(event)
        webhook_event.status = "succeeded"
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "processed_at", "updated_at"])
    except ObjectDoesNotExist as e:
        logger.warning(
            "Subscriptions webhook handler ObjectDoesNotExist (likely out-of-order)",
            extra={"data": {"event_id": event.id, "event_type": event.type, "error": str(e)}},
        )
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": True
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return HttpResponse(status=500)  # Stripe retries
    except StripeFatalError as e:
        logger.error(
            "Subscriptions webhook handler fatal error",
            extra={"data": {"event_id": event.id, "event_type": event.type, "error": str(e)}},
        )
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": False
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return JsonResponse({"status": "failed"})  # 200 — no Stripe retry
    except Exception as e:
        logger.exception(
            "Subscriptions webhook handler failed",
            extra={"data": {"event_id": event.id, "event_type": event.type}},
        )
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": True
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return HttpResponse(status=500)  # Stripe retries

    return JsonResponse({"status": "ok"})


# ---------- Lifecycle (moved from platform_router, design doc §6) ----------

_LIFECYCLE_AUDIT_ACTION = {
    "cancel": "subscription.canceled",
    "pause": "subscription.paused",
    "resume": "subscription.resumed",
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
    except (OrchestrationError, StripeFatalError) as e:
        raise Problem("validation_error", str(e))

    audit_record(
        action=_LIFECYCLE_AUDIT_ACTION[verb], tenant_id=tenant.id,
        resource_type="subscription", resource_id=mirror.stripe_subscription_id,
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
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("plan.assigned", "subscription.created")
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
            action="plan.assigned", tenant_id=tenant.id,
            resource_type="customer", resource_id=customer.external_id,
            metadata={"external_id": customer.external_id, "plan_key": plan.key})

    try:
        mirror = SubscriptionOrchestrator.subscribe(customer, plan, payload.seats)
    except (OrchestrationError, StripeFatalError) as e:
        raise Problem("validation_error", str(e))

    if mirror is None:
        # Markup-only plan: nothing for Stripe to bill, so there is no Stripe
        # object to audit — the assignment above already recorded the change.
        return 200, {"subscription_id": None, "amount_micros": 0, "quantity": 0}

    # Recorded after the orchestrator commits (it owns its transaction + a
    # Stripe call — a DB transaction can't wrap the external call).
    audit_record(
        action="subscription.created", tenant_id=tenant.id,
        resource_type="subscription", resource_id=mirror.stripe_subscription_id,
        metadata={"external_id": customer.external_id, "plan_key": plan.key,
                  "seats": payload.seats, "quantity": mirror.quantity,
                  "amount_micros": mirror.amount_micros})
    return 200, {
        "subscription_id": mirror.stripe_subscription_id,
        "amount_micros": mirror.amount_micros,
        "quantity": mirror.quantity,
    }


@subscriptions_router.post("/customers/{external_id}/seats",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("subscription.seats_changed")
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
        action="subscription.seats_changed", tenant_id=tenant.id,
        resource_type="subscription", resource_id=business.external_id,
        metadata={"external_id": business.external_id, "seats": payload.seats,
                  "change_event_id": change_event_id})
    return 200, {"seats": payload.seats}


@subscriptions_router.post("/customers/{external_id}/subscription/cancel",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("subscription.canceled")
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
@records_audit("subscription.paused")
def pause_subscription(request, external_id: str):
    """Pause collection (void) — the subscription stays active but stops billing."""
    _product_check(request)
    return _lifecycle_call(request, external_id, {"verb": "pause"})


@subscriptions_router.post("/customers/{external_id}/subscription/resume",
                           response={200: dict, 404: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
@records_audit("subscription.resumed")
def resume_subscription(request, external_id: str):
    """Resume billing: clears a pause AND any pending at-period-end cancel."""
    _product_check(request)
    return _lifecycle_call(request, external_id, {"verb": "resume"})
