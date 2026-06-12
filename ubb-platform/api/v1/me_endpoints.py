from datetime import date, datetime
from ninja import NinjaAPI, Schema, Field
from pydantic import field_validator
from typing import Optional

from core.auth import ProductAccess
from core.widget_auth import WidgetJWTAuth
from apps.billing.topups.models import TopUpAttempt
from apps.billing.connectors.stripe.stripe_api import create_checkout_session
from apps.billing.invoicing.models import Invoice

me_api = NinjaAPI(auth=WidgetJWTAuth(), urls_namespace="ubb_me_v1")

_billing_check = ProductAccess("billing")


def _check_billing_product(request):
    """Bridge widget auth (widget_tenant) to ProductAccess (tenant)."""
    request.tenant = request.widget_tenant
    _billing_check(request)


class BalanceResponse(Schema):
    balance_micros: int
    currency: str
    # F4.3 (additive): grant visibility.
    promo_micros: Optional[int] = None
    expiring_micros: Optional[int] = None
    next_expiry_at: Optional[str] = None


class GrantSummaryOut(Schema):
    id: str
    kind: str
    remaining_micros: int
    expires_at: Optional[str] = None


class GrantListResponse(Schema):
    data: list[GrantSummaryOut]


class TopUpRequest(Schema):
    amount_micros: int = Field(gt=0)
    success_url: str = Field(min_length=1)
    cancel_url: str = Field(min_length=1)

    @field_validator("amount_micros")
    @classmethod
    def validate_amount_micros(cls, value):
        if value % 10_000 != 0:
            raise ValueError("amount_micros must be divisible by 10,000 (cent-aligned)")
        return value


class TopUpResponse(Schema):
    checkout_url: str


class TransactionOut(Schema):
    id: str
    transaction_type: str
    amount_micros: int
    balance_after_micros: int
    description: str
    created_at: str


class PaginatedTransactions(Schema):
    data: list[TransactionOut]
    next_cursor: Optional[str] = None
    has_more: bool


class InvoiceOut(Schema):
    id: str
    total_amount_micros: int
    status: str
    stripe_invoice_id: str  # Exposed so UIs can link to Stripe-hosted invoice
    created_at: str


class PaginatedInvoices(Schema):
    data: list[InvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


class UsageInvoiceOut(Schema):
    id: str
    total_billed_micros: int
    payment_status: Optional[str] = None
    hosted_invoice_url: str = ""
    invoice_pdf: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    stripe_invoice_id: str = ""
    created_at: datetime


class PaginatedUsageInvoices(Schema):
    data: list[UsageInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


class SubscriptionInvoiceOut(Schema):
    id: str
    amount_paid_micros: int
    status: str
    hosted_invoice_url: str = ""
    invoice_pdf: str = ""
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    created_at: datetime


class PaginatedSubscriptionInvoices(Schema):
    data: list[SubscriptionInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


@me_api.get("/balance", response=BalanceResponse)
def get_balance(request):
    _check_billing_product(request)
    customer = request.widget_customer
    from apps.billing.wallets.models import Wallet
    from apps.billing.wallets.grants import GrantLedger
    try:
        wallet = Wallet.objects.get(customer=customer)
        return {"balance_micros": wallet.balance_micros, "currency": wallet.currency,
                **GrantLedger.balance_summary(wallet)}
    except Wallet.DoesNotExist:
        return {"balance_micros": 0, "currency": "USD",
                "promo_micros": 0, "expiring_micros": 0, "next_expiry_at": None}


@me_api.get("/grants", response=GrantListResponse)
def list_grants(request):
    """Active credit grant lots on the customer's own wallet (kind,
    remaining, expiry), soonest-expiring first. Hard-capped at the first 100
    by expiry — active lots beyond that are pathological; full pagination
    lives on the tenant API (GET /billing/customers/{id}/grants).

    Seat-scoping decision: own-wallet basis, matching the /me/balance
    precedent — a pooled seat (whose money lives on the business owner's
    wallet) sees an empty list here rather than the shared business lots,
    exactly as /me/balance shows the seat's own (empty) wallet.
    """
    _check_billing_product(request)
    customer = request.widget_customer
    from django.db.models import F
    from apps.billing.wallets.models import CreditGrant, Wallet
    wallet = Wallet.objects.filter(customer=customer).first()
    if wallet is None:
        return {"data": []}
    grants = CreditGrant.objects.filter(wallet=wallet, status="active").order_by(
        F("expires_at").asc(nulls_last=True), "created_at")[:100]
    return {"data": [
        {"id": str(g.id), "kind": g.kind, "remaining_micros": g.remaining_micros,
         "expires_at": g.expires_at.isoformat() if g.expires_at else None}
        for g in grants
    ]}


@me_api.get("/transactions", response=PaginatedTransactions)
def get_transactions(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
    except Wallet.DoesNotExist:
        return {"data": [], "next_cursor": None, "has_more": False}

    qs = wallet.transactions.all().order_by("-created_at", "-id")

    if cursor:
        try:
            from api.v1.pagination import apply_cursor_filter
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return me_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    txns = list(qs[:limit + 1])
    has_more = len(txns) > limit
    txns = txns[:limit]

    next_cursor = None
    if has_more and txns:
        from api.v1.pagination import encode_cursor
        last = txns[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(t.id),
                "transaction_type": t.transaction_type,
                "amount_micros": t.amount_micros,
                "balance_after_micros": t.balance_after_micros,
                "description": t.description,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@me_api.post("/top-up", response=TopUpResponse)
def create_top_up(request, payload: TopUpRequest):
    _check_billing_product(request)
    customer = request.widget_customer
    tenant = customer.tenant

    from apps.platform.queries import get_tenant_stripe_account, get_customer_stripe_id
    if get_tenant_stripe_account(tenant.id):
        if not get_customer_stripe_id(customer.id):
            return me_api.create_response(
                request, {"error": "Customer has no stripe_customer_id"}, status=400
            )

        attempt = TopUpAttempt.objects.create(
            customer=customer,
            amount_micros=payload.amount_micros,
            trigger="widget",
            status="pending",
        )

        checkout_url = create_checkout_session(
            customer, payload.amount_micros, attempt,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
        return {"checkout_url": checkout_url}
    else:
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import TopUpRequested

        write_event(TopUpRequested(
            tenant_id=str(tenant.id),
            customer_id=str(customer.id),
            amount_micros=payload.amount_micros,
            trigger="widget",
            success_url=getattr(payload, "success_url", "") or "",
            cancel_url=getattr(payload, "cancel_url", "") or "",
        ))
        return me_api.create_response(
            request,
            {"status": "topup_requested", "message": "Top-up request sent to tenant"},
            status=202,
        )


@me_api.get("/invoices", response=PaginatedInvoices)
def get_invoices(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    qs = Invoice.objects.filter(customer=customer).order_by("-created_at", "-id")

    if cursor:
        try:
            from api.v1.pagination import apply_cursor_filter
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return me_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    invoices = list(qs[:limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        from api.v1.pagination import encode_cursor
        last = invoices[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "total_amount_micros": inv.total_amount_micros,
                "status": inv.status,
                "stripe_invoice_id": inv.stripe_invoice_id,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@me_api.get("/usage-invoices", response=PaginatedUsageInvoices)
def list_usage_invoices(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    # Billing-owner gate: a pooled seat's bill is the consolidated BUSINESS
    # invoice (which aggregates every sibling seat). Surfacing it to the seat
    # would leak sibling spend, so a non-owner sees nothing of its own here.
    if customer.resolve_billing_owner().id != customer.id:
        return {"data": [], "next_cursor": None, "has_more": False}

    from apps.billing.invoicing.models import CustomerUsageInvoice
    qs = CustomerUsageInvoice.objects.filter(
        customer=customer
    ).order_by("-created_at", "-id")

    if cursor:
        try:
            from api.v1.pagination import apply_cursor_filter
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return me_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    invoices = list(qs[:limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        from api.v1.pagination import encode_cursor
        last = invoices[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "total_billed_micros": inv.total_billed_micros,
                "payment_status": inv.payment_status,
                "hosted_invoice_url": inv.hosted_invoice_url,
                "invoice_pdf": inv.invoice_pdf,
                "period_start": inv.period_start,
                "period_end": inv.period_end,
                "stripe_invoice_id": inv.stripe_invoice_id,
                "created_at": inv.created_at,
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@me_api.get("/subscription-invoices", response=PaginatedSubscriptionInvoices)
def list_subscription_invoices(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    # Same billing-owner gate as usage invoices: a pooled seat does not own the
    # consolidated subscription bill and must not see it.
    if customer.resolve_billing_owner().id != customer.id:
        return {"data": [], "next_cursor": None, "has_more": False}

    from apps.subscriptions.models import SubscriptionInvoice
    qs = SubscriptionInvoice.objects.filter(
        customer=customer
    ).order_by("-created_at", "-id")

    if cursor:
        try:
            from api.v1.pagination import apply_cursor_filter
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return me_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    invoices = list(qs[:limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        from api.v1.pagination import encode_cursor
        last = invoices[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "amount_paid_micros": inv.amount_paid_micros,
                "status": inv.status,
                "hosted_invoice_url": inv.hosted_invoice_url,
                "invoice_pdf": inv.invoice_pdf,
                "period_start": inv.period_start,
                "period_end": inv.period_end,
                "created_at": inv.created_at,
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
