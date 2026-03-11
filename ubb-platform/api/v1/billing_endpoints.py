from datetime import date
from typing import Optional

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
    RevenueAnalyticsResponse,
)
from core.auth import ApiKeyAuth, ProductAccess
from apps.platform.customers.models import Customer
from apps.billing.topups.models import AutoTopUpConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.connectors.stripe.stripe_api import create_checkout_session
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
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction

    customer = get_object_or_404(
        Customer, external_id=payload.customer_id, tenant=request.auth.tenant
    )

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        if payload.idempotency_key:
            existing = WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=payload.idempotency_key,
            ).first()
            if existing:
                return {"new_balance_micros": wallet.balance_micros, "transaction_id": str(existing.id)}

        wallet.balance_micros -= payload.amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="DEBIT",
            amount_micros=-payload.amount_micros,
            balance_after_micros=wallet.balance_micros,
            description="External debit",
            reference_id=payload.reference,
            idempotency_key=payload.idempotency_key or None,
        )

    return {"new_balance_micros": wallet.balance_micros, "transaction_id": str(txn.id)}


@billing_api.post("/credit", response=DebitCreditResponse)
def credit(request, payload: CreditRequest):
    _product_check(request)
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction

    customer = get_object_or_404(
        Customer, external_id=payload.customer_id, tenant=request.auth.tenant
    )

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        if payload.idempotency_key:
            existing = WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=payload.idempotency_key,
            ).first()
            if existing:
                return {"new_balance_micros": wallet.balance_micros, "transaction_id": str(existing.id)}

        wallet.balance_micros += payload.amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="ADJUSTMENT",
            amount_micros=payload.amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Credit: {payload.source}",
            reference_id=payload.reference,
            idempotency_key=payload.idempotency_key or None,
        )

    return {"new_balance_micros": wallet.balance_micros, "transaction_id": str(txn.id)}


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
    tenant = request.auth.tenant

    from apps.platform.queries import get_tenant_stripe_account, get_customer_stripe_id
    if get_tenant_stripe_account(tenant.id):
        # Stripe connector is active — create checkout session
        if not get_customer_stripe_id(customer.id):
            return billing_api.create_response(
                request, {"error": "Customer has no stripe_customer_id"}, status=400
            )

        attempt = TopUpAttempt.objects.create(
            customer=customer,
            amount_micros=payload.amount_micros,
            trigger="manual",
            status="pending",
        )

        checkout_url = create_checkout_session(
            customer, payload.amount_micros, attempt,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
        return {"checkout_url": checkout_url}
    else:
        # No connector — emit event for tenant to handle
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import TopUpRequested

        write_event(TopUpRequested(
            tenant_id=str(tenant.id),
            customer_id=str(customer.id),
            amount_micros=payload.amount_micros,
            trigger="manual",
            success_url=getattr(payload, "success_url", "") or "",
            cancel_url=getattr(payload, "cancel_url", "") or "",
        ))
        return billing_api.create_response(
            request,
            {"status": "topup_requested", "message": "Top-up request sent to tenant"},
            status=202,
        )


@billing_api.post("/customers/{customer_id}/withdraw")
def withdraw(request, customer_id: str, payload: WithdrawRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import IntegrityError, transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import WithdrawalRequested

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

        write_event(WithdrawalRequested(
            tenant_id=str(request.auth.tenant.id),
            customer_id=str(customer.id),
            amount_micros=payload.amount_micros,
            transaction_id=str(txn.id),
            idempotency_key=payload.idempotency_key,
        ))

    return {"transaction_id": str(txn.id), "balance_micros": wallet.balance_micros}


@billing_api.post("/pre-check", response=PreCheckResponse)
def pre_check(request, payload: PreCheckRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    result = RiskService.check(
        customer,
        create_run=payload.start_run,
        run_metadata=payload.run_metadata,
        external_run_id=payload.external_run_id,
    )
    return result


@billing_api.post("/customers/{customer_id}/refund")
def refund_usage(request, customer_id: str, payload: RefundRequest):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.models import WalletTransaction
    from apps.metering.queries import get_usage_event_cost
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import RefundRequested

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Idempotency on WalletTransaction
        existing_txn = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=payload.idempotency_key
        ).first()
        if existing_txn:
            return {"refund_id": existing_txn.reference_id, "balance_micros": wallet.balance_micros}

        # Look up cost via metering query interface (tenant-scoped)
        cost = get_usage_event_cost(payload.usage_event_id, tenant_id=request.auth.tenant.id)
        if cost is None:
            return billing_api.create_response(request, {"error": "Usage event not found"}, status=404)

        wallet.balance_micros += cost
        wallet.save(update_fields=["balance_micros", "updated_at"])

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="REFUND",
            amount_micros=cost,
            balance_after_micros=wallet.balance_micros,
            description=f"Refund: {payload.usage_event_id}",
            reference_id=str(payload.usage_event_id),
            idempotency_key=payload.idempotency_key,
        )

        # Emit outbox event for metering to create Refund record
        write_event(RefundRequested(
            tenant_id=str(request.auth.tenant.id),
            customer_id=str(customer.id),
            usage_event_id=str(payload.usage_event_id),
            refund_amount_micros=cost,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        ))

    return {"refund_id": str(txn.id), "balance_micros": wallet.balance_micros}


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


# ---------- Analytics ----------


@billing_api.get("/analytics/revenue", response=RevenueAnalyticsResponse)
def revenue_analytics(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    from apps.metering.queries import get_revenue_analytics
    return get_revenue_analytics(request.auth.tenant.id, start_date, end_date)
