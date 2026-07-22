from typing import Optional
from ninja import Schema, Field


class RevenueProfileIn(Schema):
    recurring_amount_micros: int = Field(ge=0)
    interval: str = "month"
    currency: str = "usd"
    effective_from: Optional[str] = None  # ISO date; defaults to today
    effective_to: Optional[str] = None


class RevenueProfileOut(Schema):
    recurring_amount_micros: int
    interval: str
    currency: str
    effective_from: str
    effective_to: Optional[str] = None


class MarginThresholdIn(Schema):
    min_margin_pct: float = 0.0
    consecutive_periods: int = Field(default=1, ge=1)
    provider_cost_spike_pct: float = 25.0


class MarginThresholdOut(Schema):
    min_margin_pct: float
    consecutive_periods: int
    provider_cost_spike_pct: float


class RevenueModeIn(Schema):
    revenue_mode: str = ""


class RevenueModeOut(Schema):
    revenue_mode: str
    resolved: str


# ---- Margin read surface out-types (#98) ----
# These document the bodies the margin endpoints already serve — typing
# documents what is served, it never reshapes it.


class PeriodWindow(Schema):
    # ISO dates; end is exclusive (month-to-date windows end at tomorrow).
    start: str
    end: str


class SeatMarginOut(Schema):
    """One customer's live margin (``MarginService.compute_live``) — the shape
    a business rollup's ``seats`` entries carry."""
    customer_id: str
    revenue_mode: str
    subscription_revenue_micros: int
    usage_billed_micros: int
    usage_revenue_micros: int
    provider_cost_micros: int
    total_revenue_micros: int
    gross_margin_micros: int
    margin_percentage: float
    event_count: int


class CustomerMarginOut(SeatMarginOut):
    # The standalone customer read adds identity + the resolved window.
    external_id: str
    period: PeriodWindow


class CustomerMarginListRow(Schema):
    customer_id: str
    subscription_revenue_micros: int
    usage_billed_micros: int
    usage_revenue_micros: int
    provider_cost_micros: int
    gross_margin_micros: int
    margin_percentage: float


class MarginListOut(Schema):
    period: PeriodWindow
    customers: list[CustomerMarginListRow]


class MarginSummaryOut(Schema):
    period: PeriodWindow
    subscription_revenue_micros: int
    usage_billed_micros: int
    usage_revenue_micros: int
    provider_cost_micros: int
    total_revenue_micros: int
    gross_margin_micros: int
    margin_percentage: float
    customer_count: int


class DimensionMarginRow(Schema):
    # Null when grouping by a tag key and the tag's JSON value is null —
    # `has_key` matches the key, KeyTextTransform surfaces SQL NULL.
    dimension: Optional[str] = None
    provider_cost_micros: int
    billed_cost_micros: int
    margin_micros: int
    event_count: int


class MarginByDimensionOut(Schema):
    period: PeriodWindow
    rows: list[DimensionMarginRow]


class UnprofitableCustomerRow(Schema):
    customer_id: str
    external_id: str
    gross_margin_micros: int
    margin_percentage: float


class UnprofitableOut(Schema):
    period_start: str
    customers: list[UnprofitableCustomerRow]


class MarginTrendPointOut(Schema):
    period_start: str
    provider_cost_micros: int
    usage_billed_micros: int
    subscription_revenue_micros: int
    gross_margin_micros: int
    margin_percentage: float


class MarginTrendOut(Schema):
    customer_id: str
    points: list[MarginTrendPointOut]


class BusinessMarginTotals(Schema):
    # The per-seat sums plus the business's own subscription revenue —
    # no margin_percentage at the rollup level (the endpoint serves none).
    subscription_revenue_micros: int
    usage_revenue_micros: int
    provider_cost_micros: int
    total_revenue_micros: int
    gross_margin_micros: int
    event_count: int


class BusinessMarginOut(Schema):
    business_id: str
    external_id: str
    totals: BusinessMarginTotals
    seats: list[SeatMarginOut]
