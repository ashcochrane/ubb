from datetime import date, datetime
from ninja import Query, Router, Schema, Field
from pydantic import field_validator
from typing import Optional

from api.v1.pagination import Paginated, empty_page, page
from api.v1.topups import start_top_up
from apps.platform.audit.marker import records_audit
from api.v1.schemas import (
    GrantKind, WalletTransactionType, whole_minor_units)
from apps.subscriptions.economics.revenue import DEFAULT_REVENUE_BASIS
from core.auth import ProductAccess
from core.currency_policy import (
    ECONOMIC_CURRENCY,
    FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_KEY,
)
from core.field_values import a_field_of
from core.report_windows import (
    END_DATE_DESCRIPTION, START_DATE_DESCRIPTION, resolve_report_window,
    states_its_report_window)
from core.money import DEFAULT_CURRENCY, minor_units
from core.problems import ProblemOut
from core.widget_auth import WidgetJWTAuth
from apps.billing.connectors.stripe.stripe_api import create_checkout_session
from apps.billing.invoicing.models import Invoice
from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE,
    ANALYTICS_MEASURE_RECORDED_EVENTS,
    AUDIT_ACTION_TOP_UP_REQUESTED,
    MEASURE_STATUS_INCOMPLETE,
    MEASURE_STATUS_KNOWN,
    MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON,
)

me_router = Router(auth=WidgetJWTAuth())

_billing_check = ProductAccess("billing")


def _check_billing_product(request):
    """Bridge widget auth (widget_tenant) to ProductAccess (tenant)."""
    request.tenant = request.widget_tenant
    _billing_check(request)


_metering_check = ProductAccess("metering")


def _check_metering_product(request):
    """The same bridge for the one metering-scoped surface on this mount,
    `/me/economics` (#561): a tenant that meters and bills elsewhere still
    shows its customers what they used."""
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
    kind: GrantKind
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
    # attempt (backed by uq_top_up_attempt_idempotency).
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
    transaction_type: WalletTransactionType
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
    amount_paid_micros: Optional[int] = Field(description=(
        "What was paid, in micros of US dollars — or null where the invoice "
        "was issued in another currency, which UBB does not convert; the "
        "hosted invoice states it as issued."))
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


@me_router.post("/top-up", response={200: TopUpResponse, 409: ProblemOut})
@records_audit(AUDIT_ACTION_TOP_UP_REQUESTED)
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


# THE END CUSTOMER'S OWN USAGE SUMMARY (#561; W5 ruling 17). The route #501
# deleted from this mount (`/me/usage-summary`) answered from a rollup of its
# own; its replacement went to the tenant's mount, which left a widget holder
# unable to see what it used. This restores the capability — not that route's
# shape — over the ONE economic query, through a response type this mount owns.
#
# ⚠⚠ THE CONTRACT IS DELIBERATELY NARROWER THAN THE TENANT'S, AND IT IS ITS OWN
# TYPE (amendment D). `EconomicsOut` is the tenant's: it publishes the supplier
# cost, the margin, provider economics and the tenant's own grouping axes. A
# widget token is an END CUSTOMER, so this mount publishes exactly two
# measures — what the customer's usage earned (`customer_revenue`) and how many
# metered events it recorded (`recorded_events`) — each as a field of a schema
# declared here. Nothing reaches the wire that this module did not name, so a
# field later added to the tenant answer stays off it (ninja publishes only the
# declared keys).
#
# ⚠ SCOPE COMES FROM THE TOKEN AND NOTHING ELSE. The route takes no customer
# parameter at all — "another customer" is not an id it accepts and refuses,
# it is a question it has no way to receive. A business token reads what
# belongs to the business itself; its seats are not added up (ruling 17), and
# neither is any other customer's.


#: WHAT EACH FIELD OF THIS ANSWER CAN RETURN, and nothing more (the owner's
#: review of #621). The question asked here is always ungrouped and
#: unbucketed, so it never meets the grain a revenue figure cannot be placed
#: at, and a count is never partly known; the revenue is always stated on
#: the default basis. Each field keeps its concept's marker and names its
#: values with the registry's constants; the export writes the `enum`.
MeRevenueStatus = a_field_of(
    "measure_status", MEASURE_STATUS_KNOWN, MEASURE_STATUS_INCOMPLETE,
    MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON)
MeCountStatus = a_field_of(
    "measure_status", MEASURE_STATUS_KNOWN,
    MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON)
MeRevenueBasis = a_field_of("revenue_basis", DEFAULT_REVENUE_BASIS)


class MeCustomerRevenueOut(Schema):
    """What your usage in the window earned, under the basis the answer names.

    `amount_micros` is null wherever no figure can be stated — no revenue is
    ever shown as zero because it is unknown or unavailable — and `status` says
    which: `known` (every input resolved), `incomplete` (the sum of what
    resolved; some is still being priced), or
    `unavailable_outside_retention_horizon` (the window reaches back past what
    UBB still holds; `available_from` says from when it can start).
    """
    amount_micros: Optional[int] = Field(description=(
        "The revenue in micros of the answer's currency, or null where no "
        "figure can be stated — never a zero standing in."))
    status: MeRevenueStatus
    available_from: Optional[str] = Field(description=(
        "The first day this figure can be stated from, non-null exactly where "
        "`status` is `unavailable_outside_retention_horizon`."))


class MeRecordedEventsOut(Schema):
    """How many metered usage events you recorded in the window.

    `status` is `known`, or `unavailable_outside_retention_horizon` where the
    window reaches back past what UBB still holds (`available_from` says
    from when it can start) — `count` is then null, never a zero.
    """
    count: Optional[int] = Field(description=(
        "How many metered usage events the window holds, or null where no "
        "figure can be stated — never a zero standing in."))
    status: MeCountStatus
    available_from: Optional[str] = Field(description=(
        "The first day this count can be stated from, non-null exactly where "
        "`status` is `unavailable_outside_retention_horizon`."))


class MeEconomicsOut(Schema):
    """Your own usage over a window: what it earned, and how many events.

    The window is echoed so a caller who left it to the default can see it.
    """
    period_start: str = Field(description=START_DATE_DESCRIPTION)
    period_end: str = Field(description=END_DATE_DESCRIPTION)
    #: Which view the revenue is stated under, as the answer applied it.
    basis: MeRevenueBasis
    #: The currency every amount here is stated in.
    currency: str
    customer_revenue: MeCustomerRevenueOut
    recorded_events: MeRecordedEventsOut
    #: The one fact the tenant answer's count states that is about THIS
    #: customer's own money (#564's rule: every revenue read the exclusion can
    #: change says so), worded for the end customer — this answer states no
    #: margin, so the tenant wording about one would be a claim it never makes.
    foreign_currency_subscription_count: int = Field(description=(
        "How many of your subscriptions the revenue above leaves out because "
        "they are billed in a currency UBB does not admit. Where it is not 0, "
        "your revenue is higher by an amount UBB cannot state; 0 where nothing "
        "was left out."))


#: The two measures this mount publishes (ruling 17) — fixed, never a caller's
#: choice: there is no measure selector to ask for a third.
WIDGET_MEASURES = (ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                   ANALYTICS_MEASURE_RECORDED_EVENTS)


def _projected(entry, figure_key):
    """One measure of the tenant answer, cut down to the widget's shape: its
    figure under ``figure_key``, its state and where its series can start."""
    return {figure_key: entry[figure_key], "status": entry["status"],
            "available_from": entry.get("available_from")}


@me_router.get("/economics", response={200: MeEconomicsOut, 422: ProblemOut})
@states_its_report_window()
def get_my_economics(
        request,
        start_date: Optional[date] = Query(None, description=START_DATE_DESCRIPTION),
        end_date: Optional[date] = Query(None, description=END_DATE_DESCRIPTION)):
    """What your own usage earned and how many events it recorded.

    Scoped to the customer the widget token names, and to nothing else: there
    is no customer parameter, and a business's answer is the business's own
    usage, without its seats'. Revenue is stated under the basis the answer
    names, and where UBB cannot state a figure the amount is null, never zero.
    """
    _check_metering_product(request)
    from api.v1.economic_question import ask_the_economic_query
    from apps.metering.queries import EconomicFilters

    window = resolve_report_window(start_date, end_date)
    answer, foreign = ask_the_economic_query(
        request.widget_tenant.id, measures=list(WIDGET_MEASURES), group_by=[],
        bucket=None, basis=DEFAULT_REVENUE_BASIS, window=window,
        filters=EconomicFilters(window=window,
                                customer_id=request.widget_customer.id))
    (row,) = answer["rows"]
    by_measure = {entry["measure"]: entry for entry in row["measures"]}
    return 200, {
        "period_start": window.start_date.isoformat(),
        "period_end": window.end_date.isoformat(),
        "basis": answer["basis"],
        # The currency every economic amount UBB states is held in — the one
        # its economic columns are checked to (ADR-0023) — named explicitly
        # even though v1 admits only one.
        "currency": ECONOMIC_CURRENCY,
        "customer_revenue": _projected(
            by_measure[ANALYTICS_MEASURE_CUSTOMER_REVENUE], "amount_micros"),
        "recorded_events": _projected(
            by_measure[ANALYTICS_MEASURE_RECORDED_EVENTS], "count"),
        FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_KEY: foreign,
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
