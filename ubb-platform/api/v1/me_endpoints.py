from datetime import date, datetime, timedelta
from ninja import Router, Schema, Field
from pydantic import field_validator
from typing import Optional

from django.utils import timezone

from api.v1.pagination import paginate
from api.v1.topups import start_top_up
from apps.platform.audit.marker import records_audit
from core.auth import ProductAccess
from core.problems import Problem
from core.widget_auth import WidgetJWTAuth
from apps.billing.connectors.stripe.stripe_api import create_checkout_session
from apps.billing.invoicing.models import Invoice

me_router = Router(auth=WidgetJWTAuth())

_billing_check = ProductAccess("billing")
_metering_check = ProductAccess("metering")


def _check_billing_product(request):
    """Bridge widget auth (widget_tenant) to ProductAccess (tenant)."""
    request.tenant = request.widget_tenant
    _billing_check(request)


def _check_metering_product(request):
    """Same bridge for metering-scoped widget endpoints (usage summary)."""
    request.tenant = request.widget_tenant
    _metering_check(request)


class MeBalanceResponse(Schema):
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
    next_cursor: Optional[str] = None
    has_more: bool


class TopUpRequest(Schema):
    amount_micros: int = Field(gt=0)
    success_url: str = Field(min_length=1)
    cancel_url: str = Field(min_length=1)
    # #78: top-up creation moves money — replay must never mint a second
    # attempt (backed by uq_topup_attempt_idempotency).
    idempotency_key: str = Field(min_length=1, max_length=400)

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


class MeUsageInvoiceOut(Schema):
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
    data: list[MeUsageInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


class MeSubscriptionInvoiceOut(Schema):
    id: str
    amount_paid_micros: int
    status: str
    hosted_invoice_url: str = ""
    invoice_pdf: str = ""
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    created_at: datetime


class PaginatedSubscriptionInvoices(Schema):
    data: list[MeSubscriptionInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


class UsageMetricOut(Schema):
    event_type: str
    units: int
    billed_cost_micros: int
    event_count: int


class UsageSummaryResponse(Schema):
    period_start: str
    period_end: str
    total_units: int
    total_billed_micros: int
    currency: str
    metrics: list[UsageMetricOut]


@me_router.get("/balance", response=MeBalanceResponse)
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
        # CUR-1: no-wallet fallback reports the tenant currency, not a literal USD.
        return {"balance_micros": 0,
                "currency": (request.widget_tenant.default_currency or "usd").lower(),
                "promo_micros": 0, "expiring_micros": 0, "next_expiry_at": None}


@me_router.get("/grants", response=GrantListResponse)
def list_grants(request, cursor: str = None, limit: int = 50):
    """Active credit grant lots on the customer's own wallet (kind,
    remaining, expiry), newest first in the one cursor envelope (#78 — the
    envelope-less capped list died with the contract big-bang; ordering moved
    from soonest-expiring to the standard creation keyset so the cursor is
    real).

    Seat-scoping decision: own-wallet basis, matching the /me/balance
    precedent — a pooled seat (whose money lives on the business owner's
    wallet) sees an empty list here rather than the shared business lots,
    exactly as /me/balance shows the seat's own (empty) wallet.
    """
    _check_billing_product(request)
    customer = request.widget_customer
    from apps.billing.wallets.models import CreditGrant, Wallet
    wallet = Wallet.objects.filter(customer=customer).first()
    if wallet is None:
        return {"data": [], "next_cursor": None, "has_more": False}
    grants, next_cursor, has_more = paginate(
        CreditGrant.objects.filter(wallet=wallet, status="active"), cursor, limit)
    return {"data": [
        {"id": str(g.id), "kind": g.kind, "remaining_micros": g.remaining_micros,
         "expires_at": g.expires_at.isoformat() if g.expires_at else None}
        for g in grants],
        "next_cursor": next_cursor, "has_more": has_more}


@me_router.get("/transactions", response=PaginatedTransactions)
def get_transactions(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer

    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
    except Wallet.DoesNotExist:
        return {"data": [], "next_cursor": None, "has_more": False}

    txns, next_cursor, has_more = paginate(wallet.transactions.all(), cursor, limit)

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


@me_router.post("/top-up", response=TopUpResponse)
@records_audit("top_up.requested")
def create_top_up(request, payload: TopUpRequest):
    """Widget twin of the tenant top-up. Replay-safe: idempotency_key is
    required and unique per customer — a retried call re-uses the original
    attempt and never starts a second charge."""
    _check_billing_product(request)
    customer = request.widget_customer
    return start_top_up(request, customer, customer.tenant, payload,
                        trigger="widget", checkout=create_checkout_session)


@me_router.get("/invoices", response=PaginatedInvoices)
def get_invoices(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer

    invoices, next_cursor, has_more = paginate(
        Invoice.objects.filter(customer=customer), cursor, limit)

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


@me_router.get("/usage-invoices", response=PaginatedUsageInvoices)
def list_usage_invoices(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer

    # Billing-owner gate: a pooled seat's bill is the consolidated BUSINESS
    # invoice (which aggregates every sibling seat). Surfacing it to the seat
    # would leak sibling spend, so a non-owner sees nothing of its own here.
    if customer.resolve_billing_owner().id != customer.id:
        return {"data": [], "next_cursor": None, "has_more": False}

    from apps.billing.invoicing.models import CustomerUsageInvoice
    invoices, next_cursor, has_more = paginate(
        CustomerUsageInvoice.objects.filter(customer=customer), cursor, limit)

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


@me_router.get("/usage-summary", response=UsageSummaryResponse)
def get_usage_summary(request):
    """Month-to-date usage rollup for the calling end customer.

    Window: current UTC calendar month-to-date (house convention — first of
    month through today inclusive; period_end is the exclusive day bound).

    Deliberately NO billing-owner gate (unlike /me/usage-invoices): usage
    attribution is per-seat by design, so a pooled seat sees only its OWN
    consumption here and leaks nothing about its siblings — there is no
    consolidated money amount to protect. A BUSINESS token aggregates across
    its seats (the same seat basis its consolidated invoice bills on).
    Metering-scoped, not billing-scoped: a meter-only tenant's customers can
    still see what they consumed.
    """
    _check_metering_product(request)
    customer = request.widget_customer
    from apps.metering.queries import get_customer_usage_summary

    today = timezone.now().date()
    period_start = today.replace(day=1)
    period_end = today + timedelta(days=1)  # month-to-date, inclusive of today
    summary = get_customer_usage_summary(
        request.widget_tenant.id, customer.id, period_start, period_end)
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_units": summary["total_units"],
        "total_billed_micros": summary["total_billed_micros"],
        "currency": request.widget_tenant.default_currency or "usd",
        "metrics": summary["metrics"],
    }


@me_router.get("/subscription-invoices", response=PaginatedSubscriptionInvoices)
def list_subscription_invoices(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer

    # Same billing-owner gate as usage invoices: a pooled seat does not own the
    # consolidated subscription bill and must not see it.
    if customer.resolve_billing_owner().id != customer.id:
        return {"data": [], "next_cursor": None, "has_more": False}

    from apps.subscriptions.models import SubscriptionInvoice
    invoices, next_cursor, has_more = paginate(
        SubscriptionInvoice.objects.filter(customer=customer), cursor, limit)

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
