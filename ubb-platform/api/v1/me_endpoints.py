from datetime import date, datetime, timedelta
from ninja import Router, Schema, Field
from pydantic import field_validator
from typing import Optional

from django.utils import timezone

from api.v1.pagination import Paginated, empty_page, page
from api.v1.topups import start_top_up
from apps.platform.audit.marker import records_audit
from api.v1.schemas import whole_minor_units
from core.auth import ProductAccess
from core.money import DEFAULT_CURRENCY, minor_units
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
    # Pooled-seat disclosure (Task 9 finding B): this balance is the
    # RESOLVED BILLING OWNER's — reuses the same two fields the tenant
    # surface's GET /billing/customers/{id}/balance already discloses, so a
    # pooled seat's widget can label the number "your business's balance"
    # instead of implying it is the seat's own.
    is_pooled_seat: bool = False
    billing_owner_external_id: str = ""


class GrantSummaryOut(Schema):
    id: str
    kind: str
    remaining_micros: int
    expires_at: Optional[str] = None


def _grant_summary_out(g):
    return {
        "id": str(g.id),
        "kind": g.kind,
        "remaining_micros": g.remaining_micros,
        "expires_at": g.expires_at.isoformat() if g.expires_at else None,
    }


class GrantListResponse(Paginated[GrantSummaryOut]):
    pass


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
        # The same inward boundary as the tenant-facing top-up, kept with its
        # own wording because the message is part of the widget surface's answer.
        return whole_minor_units(value, message=(
            "amount_micros must be divisible by "
            f"{minor_units(DEFAULT_CURRENCY):,} (cent-aligned)"))


class TopUpResponse(Schema):
    checkout_url: str


class TransactionOut(Schema):
    id: str
    transaction_type: str
    amount_micros: int
    balance_after_micros: int
    description: str
    created_at: str


def _transaction_out(t):
    return {
        "id": str(t.id),
        "transaction_type": t.transaction_type,
        "amount_micros": t.amount_micros,
        "balance_after_micros": t.balance_after_micros,
        "description": t.description,
        "created_at": t.created_at.isoformat(),
    }


class PaginatedTransactions(Paginated[TransactionOut]):
    pass


class InvoiceOut(Schema):
    id: str
    total_amount_micros: int
    status: str
    stripe_invoice_id: str  # Exposed so UIs can link to Stripe-hosted invoice
    created_at: str


def _invoice_out(inv):
    return {
        "id": str(inv.id),
        "total_amount_micros": inv.total_amount_micros,
        "status": inv.status,
        "stripe_invoice_id": inv.stripe_invoice_id,
        "created_at": inv.created_at.isoformat(),
    }


class PaginatedInvoices(Paginated[InvoiceOut]):
    pass


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


def _usage_invoice_out(inv):
    return {
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


class PaginatedUsageInvoices(Paginated[MeUsageInvoiceOut]):
    pass


class MeSubscriptionInvoiceOut(Schema):
    id: str
    amount_paid_micros: int
    status: str
    hosted_invoice_url: str = ""
    invoice_pdf: str = ""
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    created_at: datetime


def _subscription_invoice_out(inv):
    return {
        "id": str(inv.id),
        "amount_paid_micros": inv.amount_paid_micros,
        "status": inv.status,
        "hosted_invoice_url": inv.hosted_invoice_url,
        "invoice_pdf": inv.invoice_pdf,
        "period_start": inv.period_start,
        "period_end": inv.period_end,
        "created_at": inv.created_at,
    }


class PaginatedSubscriptionInvoices(Paginated[MeSubscriptionInvoiceOut]):
    pass


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
    """A pooled seat's balance IS the billing owner's (Task 9 finding B):
    Task 8c's ``lock_for_billing`` ratchet refuses to let a wallet exist on
    a seat id at all, and ``start_top_up`` pins every top-up's credit to
    ``customer.resolve_billing_owner()`` — so a seat's OWN wallet row can
    never exist, even right after that seat pays. Reading ``customer``
    directly here used to 404 into a fabricated ``balance_micros: 0`` that
    never changed no matter how much the seat topped up. Resolve to the
    owner instead, exactly like the tenant surface's GET
    /billing/customers/{id}/balance, and disclose ownership
    (``is_pooled_seat`` / ``billing_owner_external_id``, the same two
    fields that surface already returns) so the widget can label the number
    "your business's balance" rather than implying it is the seat's own.

    This does NOT extend to /me/grants or /me/transactions below: those are
    ITEMIZED lists (individual lots/lines with amounts and timing), and
    resolving them to the owner would show one seat every sibling seat's
    financial activity — the exact leak their docstrings are written to
    avoid. A balance is one aggregate number, not sibling-attributed detail,
    so disclosing it does not cross the same privacy line.
    """
    _check_billing_product(request)
    customer = request.widget_customer
    owner = customer.resolve_billing_owner()
    owner_disclosure = {"is_pooled_seat": owner.id != customer.id,
                        "billing_owner_external_id": owner.external_id}
    from apps.billing.wallets import operations as wallet_ops
    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=owner)
        return {"balance_micros": wallet.balance_micros, "currency": wallet.currency,
                **wallet_ops.balance_summary(wallet), **owner_disclosure}
    except Wallet.DoesNotExist:
        # CUR-1: no-wallet fallback reports the tenant currency, not a literal USD.
        # A genuinely untouched owner (never topped up) legitimately has no
        # wallet yet — this 0 is honest, not the seat-vs-owner defect above.
        return {"balance_micros": 0,
                "currency": (request.widget_tenant.default_currency or "usd").lower(),
                "promo_micros": 0, "expiring_micros": 0, "next_expiry_at": None,
                **owner_disclosure}


@me_router.get("/grants", response=GrantListResponse)
def list_grants(request, cursor: str = None, limit: int = 50):
    """Active credit grant lots on the customer's own wallet (kind,
    remaining, expiry), newest first in the one cursor envelope (#78 — the
    envelope-less capped list died with the contract big-bang; ordering moved
    from soonest-expiring to the standard creation keyset so the cursor is
    real).

    Seat-scoping decision: own-wallet basis — deliberately NOT resolved to
    the billing owner the way /me/balance now is (Task 9 finding B). A grant
    list is ITEMIZED (individual lots, each with its own amount/expiry); a
    pooled seat reading the owner's grants would see every sibling seat's
    lots, not just an aggregate figure. So this stays seat-scoped and,
    since Task 8c's ``lock_for_billing`` ratchet guarantees a pooled seat's
    own wallet can never exist, always answers an honest empty page for a
    seat — never the shared business lots.
    """
    _check_billing_product(request)
    customer = request.widget_customer
    from apps.billing.wallets.models import CreditGrant, Wallet
    wallet = Wallet.objects.filter(customer=customer).first()
    if wallet is None:
        return empty_page()
    return page(CreditGrant.objects.filter(wallet=wallet, status="active"),
                cursor, limit, serialize=_grant_summary_out)


@me_router.get("/transactions", response=PaginatedTransactions)
def get_transactions(request, cursor: str = None, limit: int = 50):
    """Ledger lines on the customer's OWN wallet — same seat-scoping call as
    /me/grants, for the same reason: a transaction list is line-by-line
    itemized detail, so resolving it to the billing owner would show a
    pooled seat every sibling seat's individual top-ups/debits. Stays
    seat-scoped; per Task 8c's ``lock_for_billing`` ratchet a pooled seat's
    own wallet can never exist, so this always answers an honest empty page
    for a seat rather than the shared business ledger.
    """
    _check_billing_product(request)
    customer = request.widget_customer

    from apps.billing.wallets.models import Wallet
    try:
        wallet = Wallet.objects.get(customer=customer)
    except Wallet.DoesNotExist:
        return empty_page()

    return page(wallet.transactions.all(), cursor, limit, serialize=_transaction_out)


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

    return page(Invoice.objects.filter(customer=customer), cursor, limit,
                serialize=_invoice_out)


@me_router.get("/usage-invoices", response=PaginatedUsageInvoices)
def list_usage_invoices(request, cursor: str = None, limit: int = 50):
    _check_billing_product(request)
    customer = request.widget_customer

    # Billing-owner gate: a pooled seat's bill is the consolidated BUSINESS
    # invoice (which aggregates every sibling seat). Surfacing it to the seat
    # would leak sibling spend, so a non-owner sees nothing of its own here.
    if customer.resolve_billing_owner().id != customer.id:
        return empty_page()

    from apps.billing.invoicing.models import CustomerUsageInvoice
    return page(CustomerUsageInvoice.objects.filter(customer=customer),
                cursor, limit, serialize=_usage_invoice_out)


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
        return empty_page()

    from apps.subscriptions.models import SubscriptionInvoice
    return page(SubscriptionInvoice.objects.filter(customer=customer),
                cursor, limit, serialize=_subscription_invoice_out)
