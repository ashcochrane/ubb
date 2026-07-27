from typing import Optional

from ninja import Field, Schema


class SyncResponse(Schema):
    synced: int
    skipped: int
    errors: int


class StripeSubscriptionOut(Schema):
    id: str
    stripe_subscription_id: str
    stripe_product_name: str
    status: str
    amount_micros: int
    currency: str
    interval: str
    current_period_start: str
    current_period_end: str
    last_synced_at: str


class SubscriptionInvoiceOut(Schema):
    id: str
    stripe_invoice_id: str
    amount_paid_micros: int
    currency: str
    period_start: str
    period_end: str
    paid_at: str


class CustomerEconomicsOut(Schema):
    customer_id: str
    external_id: str
    plan: str
    subscription_revenue_micros: int
    usage_billed_micros: int
    provider_cost_micros: int
    gross_margin_micros: int
    margin_percentage: float


class EconomicsListResponse(Schema):
    period: dict
    customers: list[CustomerEconomicsOut]
    summary: dict


class EconomicsSummaryResponse(Schema):
    period: dict
    total_revenue_micros: int
    total_cost_micros: int
    total_margin_micros: int
    avg_margin_percentage: float
    unprofitable_customers: int
    total_customers: int


class PaginatedInvoicesResponse(Schema):
    data: list[SubscriptionInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


# Lifecycle verb payloads (moved from api/v1/schemas.py with the routes —
# apps/subscriptions/api is itself composition layer for this product, but
# ADR-001 forbids a product importing api.v1, so these are defined locally
# rather than imported from api.v1.schemas).


class SubscriptionCancelIn(Schema):
    at_period_end: bool = True


class SubscribeIn(Schema):
    plan_key: str = Field(min_length=1, max_length=64)
    seats: int = Field(default=0, ge=0)


class SeatsIn(Schema):
    seats: int = Field(ge=0)
