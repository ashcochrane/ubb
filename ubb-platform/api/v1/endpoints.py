import redis

from django.conf import settings
from django.db import IntegrityError, connection
from ninja import NinjaAPI
from core.auth import ApiKeyAuth
from api.v1.schemas import (
    PreCheckRequest, PreCheckResponse,
    RecordUsageRequest, RecordUsageResponse,
    CreateCustomerRequest, CustomerResponse,
    BalanceResponse, UsageEventOut,
    ConfigureAutoTopUpRequest,
    CreateTopUpRequest,
    PaginatedUsageResponse,
    WithdrawRequest,
    RefundRequest,
)
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.platform.customers.models import Customer, AutoTopUpConfig
from apps.usage.services.usage_service import UsageService
from apps.gating.services.risk_service import RiskService
from apps.stripe_integration.services.stripe_service import StripeService
from django.shortcuts import get_object_or_404

api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_v1")


@api.get("/health", auth=None)
def health(request):
    return {"status": "ok"}


@api.get("/ready", auth=None)
def ready(request):
    checks = {}
    # Check database connectivity
    try:
        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    # Check Redis connectivity
    try:
        r = redis.from_url(settings.REDIS_URL)
        try:
            r.ping()
            checks["redis"] = "ok"
        finally:
            r.close()
    except Exception:
        checks["redis"] = "error"
    all_ok = all(v == "ok" for v in checks.values())
    return api.create_response(
        request,
        {"status": "ready" if all_ok else "not_ready", "checks": checks},
        status=200 if all_ok else 503,
    )


@api.post("/pre-check", response=PreCheckResponse)
def pre_check(request, payload: PreCheckRequest):
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    result = RiskService.check(customer)
    return result


@api.post("/usage", response=RecordUsageResponse)
def record_usage(request, payload: RecordUsageRequest):
    from apps.pricing.services.pricing_service import PricingError

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    try:
        result = UsageService.record_usage(
            tenant=request.auth.tenant,
            customer=customer,
            request_id=payload.request_id,
            idempotency_key=payload.idempotency_key,
            cost_micros=payload.cost_micros,
            metadata=payload.metadata,
            event_type=payload.event_type,
            provider=payload.provider,
            usage_metrics=payload.usage_metrics,
            properties=payload.properties,
            group_keys=payload.group_keys,
        )
    except PricingError as e:
        return api.create_response(request, {"error": str(e)}, status=422)
    except ValueError as e:
        return api.create_response(request, {"error": str(e)}, status=422)
    return result


@api.post("/customers", response={201: CustomerResponse, 409: dict})
def create_customer(request, payload: CreateCustomerRequest):
    try:
        customer = Customer.objects.create(
            tenant=request.auth.tenant,
            external_id=payload.external_id,
            stripe_customer_id=payload.stripe_customer_id,
            metadata=payload.metadata,
        )
        return 201, customer
    except IntegrityError:
        return 409, {"error": "Customer with this external_id already exists"}


@api.get("/customers/{customer_id}/balance", response=BalanceResponse)
def get_balance(request, customer_id: str):
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    return {"balance_micros": customer.wallet.balance_micros, "currency": customer.wallet.currency}


@api.get("/customers/{customer_id}/usage", response=PaginatedUsageResponse)
def get_usage(request, customer_id: str, cursor: str = None, limit: int = 50,
              group_key: str = None, group_value: str = None):
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)  # Clamp between 1 and 100

    qs = customer.usage_events.all().order_by("-effective_at", "-id")

    if group_key and group_value:
        qs = qs.filter(group_keys__contains={group_key: group_value})

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor)
        except ValueError:
            return api.create_response(request, {"error": "Invalid cursor"}, status=400)

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
                "event_type": e.event_type,
                "provider": e.provider,
                "provider_cost_micros": e.provider_cost_micros,
                "billed_cost_micros": e.billed_cost_micros,
                "metadata": e.metadata,
                "effective_at": e.effective_at.isoformat(),
            }
            for e in events
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@api.put("/customers/{customer_id}/auto-top-up")
def configure_auto_top_up(request, customer_id: str, payload: ConfigureAutoTopUpRequest):
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    AutoTopUpConfig.objects.update_or_create(
        customer=customer,
        defaults={
            "is_enabled": payload.is_enabled,
            "trigger_threshold_micros": payload.trigger_threshold_micros,
            "top_up_amount_micros": payload.top_up_amount_micros,
        },
    )
    return {"status": "ok"}


@api.post("/customers/{customer_id}/top-up")
def create_top_up(request, customer_id: str, payload: CreateTopUpRequest):
    from apps.platform.customers.models import TopUpAttempt

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    if not customer.stripe_customer_id:
        return api.create_response(request, {"error": "Customer has no stripe_customer_id"}, status=400)

    attempt = TopUpAttempt.objects.create(
        customer=customer,
        amount_micros=payload.amount_micros,
        trigger="manual",
        status="pending",
    )

    checkout_url = StripeService.create_checkout_session(
        customer, payload.amount_micros, attempt,
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
    )
    return {"checkout_url": checkout_url}


@api.post("/customers/{customer_id}/withdraw")
def withdraw(request, customer_id: str, payload: WithdrawRequest):
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import IntegrityError, transaction
    from core.locking import lock_for_billing
    from apps.platform.customers.models import WalletTransaction

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Check idempotency
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=payload.idempotency_key
        ).first()
        if existing:
            return {"transaction_id": str(existing.id), "balance_micros": wallet.balance_micros}

        if wallet.balance_micros < payload.amount_micros:
            return api.create_response(
                request, {"error": "Insufficient balance"}, status=400
            )

        wallet.balance_micros -= payload.amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="WITHDRAWAL",
            amount_micros=-payload.amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=payload.description or "Withdrawal",
            idempotency_key=payload.idempotency_key,
        )

    return {"transaction_id": str(txn.id), "balance_micros": wallet.balance_micros}


@api.post("/customers/{customer_id}/refund")
def refund_usage(request, customer_id: str, payload: RefundRequest):
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import IntegrityError, transaction
    from core.locking import lock_for_billing, lock_usage_event
    from apps.usage.models import UsageEvent, Refund
    from apps.platform.customers.models import WalletTransaction

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Lock event — raises DoesNotExist → catch and return 404
        try:
            event = lock_usage_event(payload.usage_event_id)
        except UsageEvent.DoesNotExist:
            return api.create_response(request, {"error": "Usage event not found"}, status=404)

        # Verify ownership
        if event.customer_id != customer.id or event.tenant_id != request.auth.tenant.id:
            return api.create_response(request, {"error": "Usage event not found"}, status=404)

        # Idempotency on WalletTransaction
        existing_txn = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=payload.idempotency_key
        ).first()
        if existing_txn:
            return {"refund_id": existing_txn.reference_id, "balance_micros": wallet.balance_micros}

        # Create refund (IntegrityError = already refunded via OneToOne constraint)
        try:
            refund = Refund.objects.create(
                tenant=request.auth.tenant,
                customer=customer,
                usage_event=event,
                amount_micros=event.cost_micros,
                reason=payload.reason,
                refunded_by_api_key=request.auth,
            )
        except IntegrityError:
            return api.create_response(
                request, {"error": "Usage event already refunded"}, status=409
            )

        wallet.balance_micros += event.cost_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="REFUND",
            amount_micros=event.cost_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Refund: {event.request_id}",
            reference_id=str(refund.id),
            idempotency_key=payload.idempotency_key,
        )

    return {"refund_id": str(refund.id), "balance_micros": wallet.balance_micros}


@api.get("/customers/{customer_id}/transactions")
def get_transactions(request, customer_id: str, cursor: str = None, limit: int = 50):
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)

    qs = customer.wallet.transactions.all().order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return api.create_response(request, {"error": "Invalid cursor"}, status=400)

    txns = list(qs[:limit + 1])
    has_more = len(txns) > limit
    txns = txns[:limit]

    next_cursor = None
    if has_more and txns:
        last = txns[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": t.id,
                "transaction_type": t.transaction_type,
                "amount_micros": t.amount_micros,
                "balance_after_micros": t.balance_after_micros,
                "description": t.description,
                "reference_id": t.reference_id,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
