from ninja import NinjaAPI, Schema, Field
from typing import Optional

from core.widget_auth import WidgetJWTAuth
from apps.customers.models import TopUpAttempt
from apps.stripe_integration.services.stripe_service import StripeService
from apps.usage.models import Invoice

widget_api = NinjaAPI(auth=WidgetJWTAuth(), urls_namespace="ubb_widget_v1")


class WidgetBalanceResponse(Schema):
    balance_micros: int
    currency: str


class WidgetTopUpRequest(Schema):
    amount_micros: int = Field(gt=0)


class WidgetTopUpResponse(Schema):
    checkout_url: str


class WidgetTransactionOut(Schema):
    id: str
    transaction_type: str
    amount_micros: int
    balance_after_micros: int
    description: str
    created_at: str


class WidgetPaginatedTransactions(Schema):
    data: list[WidgetTransactionOut]
    next_cursor: Optional[str] = None
    has_more: bool


class WidgetInvoiceOut(Schema):
    id: str
    total_amount_micros: int
    status: str
    stripe_invoice_id: str
    created_at: str


class WidgetPaginatedInvoices(Schema):
    data: list[WidgetInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


@widget_api.get("/balance", response=WidgetBalanceResponse)
def widget_balance(request):
    customer = request.widget_customer
    wallet = customer.wallet
    return {"balance_micros": wallet.balance_micros, "currency": wallet.currency}


@widget_api.get("/transactions", response=WidgetPaginatedTransactions)
def widget_transactions(request, cursor: str = None, limit: int = 50):
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    qs = customer.wallet.transactions.all().order_by("-created_at", "-id")

    if cursor:
        try:
            from api.v1.pagination import apply_cursor_filter
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return widget_api.create_response(request, {"error": "Invalid cursor"}, status=400)

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


@widget_api.post("/top-up", response=WidgetTopUpResponse)
def widget_top_up(request, payload: WidgetTopUpRequest):
    customer = request.widget_customer

    if not customer.stripe_customer_id:
        StripeService.create_customer(customer)

    attempt = TopUpAttempt.objects.create(
        customer=customer,
        amount_micros=payload.amount_micros,
        trigger="widget",
        status="pending",
    )

    checkout_url = StripeService.create_checkout_session(
        customer, payload.amount_micros, attempt
    )
    return {"checkout_url": checkout_url}


@widget_api.get("/invoices", response=WidgetPaginatedInvoices)
def widget_invoices(request, cursor: str = None, limit: int = 50):
    customer = request.widget_customer
    limit = min(max(limit, 1), 100)

    qs = Invoice.objects.filter(customer=customer).order_by("-created_at", "-id")

    if cursor:
        try:
            from api.v1.pagination import apply_cursor_filter
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return widget_api.create_response(request, {"error": "Invalid cursor"}, status=400)

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
