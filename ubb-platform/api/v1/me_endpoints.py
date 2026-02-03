from ninja import NinjaAPI, Schema, Field
from pydantic import field_validator
from typing import Optional

from core.widget_auth import WidgetJWTAuth
from apps.customers.models import TopUpAttempt
from apps.stripe_integration.services.stripe_service import StripeService
from apps.usage.models import Invoice

me_api = NinjaAPI(auth=WidgetJWTAuth(), urls_namespace="ubb_me_v1")


class BalanceResponse(Schema):
    balance_micros: int
    currency: str


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


@me_api.get("/balance", response=BalanceResponse)
def get_balance(request):
    customer = request.widget_customer
    wallet = customer.wallet
    return {"balance_micros": wallet.balance_micros, "currency": wallet.currency}


@me_api.get("/transactions", response=PaginatedTransactions)
def get_transactions(request, cursor: str = None, limit: int = 50):
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    qs = customer.wallet.transactions.all().order_by("-created_at", "-id")

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
    customer = request.widget_customer

    if not customer.stripe_customer_id:
        return me_api.create_response(request, {"error": "Customer has no stripe_customer_id"}, status=400)

    attempt = TopUpAttempt.objects.create(
        customer=customer,
        amount_micros=payload.amount_micros,
        trigger="widget",
        status="pending",
    )

    checkout_url = StripeService.create_checkout_session(
        customer, payload.amount_micros, attempt,
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
    )
    return {"checkout_url": checkout_url}


@me_api.get("/invoices", response=PaginatedInvoices)
def get_invoices(request, cursor: str = None, limit: int = 50):
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
