from datetime import date
from typing import Optional

from django.db.models import Sum, Count
from django.db.models.functions import TruncDate, Coalesce
from ninja import NinjaAPI, Schema

from api.v1.pagination import apply_cursor_filter, encode_cursor
from api.v1.schemas import (
    PreCheckRequest, PreCheckResponse,
    BalanceResponse,
    ConfigureAutoTopUpRequest,
    CreateTopUpRequest,
    WithdrawRequest,
    RefundRequest,
    DebitRequest, CreditRequest, DebitCreditResponse,
)
from core.auth import ApiKeyAuth, ProductAccess
from apps.platform.customers.models import Customer
from apps.billing.topups.models import AutoTopUpConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.stripe.services.stripe_service import StripeService
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from django.shortcuts import get_object_or_404

billing_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_billing_v1")

_product_check = ProductAccess("billing")


# ---------- Customer billing endpoints ----------


@billing_api.get("/customers/{customer_id}/balance", response=BalanceResponse)
def get_balance(request, customer_id: str):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
        return {"balance_micros": wallet.balance_micros, "currency": wallet.currency}
    except Wallet.DoesNotExist:
        return {"balance_micros": 0, "currency": "USD"}


@billing_api.post("/debit", response=DebitCreditResponse)
def debit(request, payload: DebitRequest):
    _product_check(request)
    customer = get_object_or_404(
        Customer, external_id=payload.customer_id, tenant=request.auth.tenant
    )
    txn = customer.wallet.deduct(
        payload.amount_micros,
        description="External debit",
        reference_id=payload.reference,
    )
    return {
        "new_balance_micros": customer.wallet.balance_micros,
        "transaction_id": str(txn.id),
    }


@billing_api.post("/credit", response=DebitCreditResponse)
def credit(request, payload: CreditRequest):
    _product_check(request)
    customer = get_object_or_404(
        Customer, external_id=payload.customer_id, tenant=request.auth.tenant
    )
    txn = customer.wallet.credit(
        payload.amount_micros,
        description=f"Credit: {payload.source}",
        reference_id=payload.reference,
        transaction_type="ADJUSTMENT",
    )
    return {
        "new_balance_micros": customer.wallet.balance_micros,
        "transaction_id": str(txn.id),
    }


@billing_api.put("/customers/{customer_id}/auto-top-up")
def configure_auto_top_up(request, customer_id: str, payload: ConfigureAutoTopUpRequest):
    _product_check(request)
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


@billing_api.post("/customers/{customer_id}/top-up")
def create_top_up(request, customer_id: str, payload: CreateTopUpRequest):
    _product_check(request)
    from apps.billing.topups.models import TopUpAttempt

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    if not customer.stripe_customer_id:
        return billing_api.create_response(request, {"error": "Customer has no stripe_customer_id"}, status=400)

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


@billing_api.post("/customers/{customer_id}/withdraw")
def withdraw(request, customer_id: str, payload: WithdrawRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import IntegrityError, transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Check idempotency
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=payload.idempotency_key
        ).first()
        if existing:
            return {"transaction_id": str(existing.id), "balance_micros": wallet.balance_micros}

        if wallet.balance_micros < payload.amount_micros:
            return billing_api.create_response(
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


@billing_api.post("/pre-check", response=PreCheckResponse)
def pre_check(request, payload: PreCheckRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    result = RiskService.check(customer)
    return result


@billing_api.post("/customers/{customer_id}/refund")
def refund_usage(request, customer_id: str, payload: RefundRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import IntegrityError, transaction
    from apps.billing.locking import lock_for_billing
    from apps.metering.locking import lock_usage_event
    from apps.metering.usage.models import UsageEvent, Refund
    from apps.billing.wallets.models import WalletTransaction

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Lock event — raises DoesNotExist → catch and return 404
        try:
            event = lock_usage_event(payload.usage_event_id)
        except UsageEvent.DoesNotExist:
            return billing_api.create_response(request, {"error": "Usage event not found"}, status=404)

        # Verify ownership
        if event.customer_id != customer.id or event.tenant_id != request.auth.tenant.id:
            return billing_api.create_response(request, {"error": "Usage event not found"}, status=404)

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
            return billing_api.create_response(
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


@billing_api.get("/customers/{customer_id}/transactions")
def get_transactions(request, customer_id: str, cursor: str = None, limit: int = 50):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)

    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
    except Wallet.DoesNotExist:
        return {"data": [], "next_cursor": None, "has_more": False}

    qs = wallet.transactions.all().order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return billing_api.create_response(request, {"error": "Invalid cursor"}, status=400)

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


# ---------- Tenant billing endpoints ----------


class TenantBillingPeriodOut(Schema):
    id: str
    period_start: str
    period_end: str
    status: str
    total_usage_cost_micros: int
    event_count: int
    platform_fee_micros: int


class TenantBillingPeriodListResponse(Schema):
    data: list[TenantBillingPeriodOut]
    next_cursor: Optional[str] = None
    has_more: bool


class TenantInvoiceOut(Schema):
    id: str
    billing_period_id: str
    stripe_invoice_id: str
    total_amount_micros: int
    status: str
    created_at: str


class TenantInvoiceListResponse(Schema):
    data: list[TenantInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


@billing_api.get("/tenant/billing-periods", response=TenantBillingPeriodListResponse)
def list_billing_periods(request, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = TenantBillingPeriod.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return billing_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    periods = list(qs[:limit + 1])
    has_more = len(periods) > limit
    periods = periods[:limit]

    next_cursor = None
    if has_more and periods:
        last = periods[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(p.id),
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "status": p.status,
                "total_usage_cost_micros": p.total_usage_cost_micros,
                "event_count": p.event_count,
                "platform_fee_micros": p.platform_fee_micros,
            }
            for p in periods
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@billing_api.get("/tenant/invoices", response=TenantInvoiceListResponse)
def list_invoices(request, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = TenantInvoice.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return billing_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    invoices = list(qs[:limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        last = invoices[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "billing_period_id": str(inv.billing_period_id),
                "stripe_invoice_id": inv.stripe_invoice_id,
                "total_amount_micros": inv.total_amount_micros,
                "status": inv.status,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
