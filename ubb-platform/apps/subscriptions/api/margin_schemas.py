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


# WHAT `unresolved_event_count` MEANS EVERYWHERE BELOW, SAID ONCE (#328).
#
# It is the number of events the supplier cost beside it could not include —
# `Posting.provider_cost_micros` is nullable and a null means UBB has not
# resolved that cost (#317), so a total built over the column is a FLOOR
# wherever this is non-zero, and every margin derived from that total is a
# CEILING: the true margin can only be smaller than the figure shown. Zero means
# the figure is whole.
#
# An event whose Event Type declares no supplier cost is NOT counted. Nothing
# about it is missing (#327), and a caveat that is always on is a caveat nobody
# reads.
#
# Every schema here that publishes a supplier cost declares it, because a key a
# schema does not name is a key django-ninja DROPS rather than passes through —
# which is how #327's declared row lost the count while its two untyped
# siblings carried it for free.


class SeatMarginOut(Schema):
    """One customer's live margin (``MarginService.compute_live``) — the shape
    a business rollup's ``seats`` entries carry."""
    customer_id: str
    revenue_mode: str
    subscription_revenue_micros: int
    usage_billed_micros: int
    usage_revenue_micros: int
    provider_cost_micros: int
    unresolved_event_count: int
    #: The revenue half's own count (#351) — see `GroupingFieldMarginRow`.
    unpriced_event_count: int
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
    unresolved_event_count: int
    unpriced_event_count: int
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
    #: The tenant-wide count: every customer's, added up, because the cost above
    #: is every customer's added up.
    unresolved_event_count: int
    #: The same, for the revenue half (#351): every customer's, added up.
    unpriced_event_count: int
    total_revenue_micros: int
    gross_margin_micros: int
    margin_percentage: float
    customer_count: int


class GroupingFieldMarginRow(Schema):
    # The VALUE the row groups, not the axis it was grouped on: the axis is
    # already named by the request's `group_by`, and repeating it in every row
    # would say the same thing once per row. Null when grouping by an open-bag
    # key and that key's JSON value is null — `has_key` matches the key,
    # KeyTextTransform surfaces SQL NULL.
    grouping_field_value: Optional[str] = None
    provider_cost_micros: int
    #: HOW MANY EVENTS THE COST ABOVE COULD NOT INCLUDE, for THIS row's group
    #: (#327). Non-zero makes the cost a floor and `margin_micros` a ceiling —
    #: the margin can only be smaller than stated, never larger.
    #:
    #: It is declared here rather than left to arrive because this row is the
    #: DECLARED one of the three rollups over these axes: the read contract
    #: attaches the count, and a schema that does not name it does not merely
    #: omit it — django-ninja DROPS it, which turns a floor back into a figure
    #: on the one surface of the three that a drift gate can see.
    unresolved_event_count: int
    billed_cost_micros: int
    #: HOW MANY EVENTS THE BILLED TOTAL COULD NOT INCLUDE, for THIS row's group
    #: (#351) — and it is declared here for the reason the count above it is,
    #: which #351 was sent to apply a second time rather than to rediscover.
    #: **A `Schema` that does not name a key DROPS it.** The read contract
    #: attaches this to every row of all three rollups; the two untyped ones
    #: carry it free, and this one — the only surface a drift gate can see —
    #: would be the only one to lose it.
    #:
    #: It bounds the margin the OTHER way from its sibling: an excluded cost
    #: makes `margin_micros` a ceiling, an excluded price makes it a floor.
    unpriced_event_count: int
    margin_micros: int
    event_count: int


class MarginByGroupingFieldOut(Schema):
    period: PeriodWindow
    rows: list[GroupingFieldMarginRow]


class UnprofitableCustomerRow(Schema):
    customer_id: str
    external_id: str
    gross_margin_micros: int
    #: A margin named as unprofitable is a CEILING wherever this is non-zero, so
    #: the count can never mean "perhaps they are fine" — only that they may be
    #: worse than the figure says.
    unresolved_event_count: int
    #: ⚠ AND THIS ONE CAN MEAN EXACTLY THAT (#351). An excluded PRICE means
    #: revenue was left out, so the true margin is HIGHER than the figure that
    #: named this customer unprofitable. Publishing only the count above — the
    #: one that cannot say it — would have made this list the more misleading of
    #: the two surfaces.
    unpriced_event_count: int
    margin_percentage: float


class UnprofitableOut(Schema):
    period_start: str
    customers: list[UnprofitableCustomerRow]


class MarginTrendPointOut(Schema):
    period_start: str
    provider_cost_micros: int
    #: Per POINT, because completeness varies month to month and a trend that
    #: stated it once would be stating it about the wrong months.
    unresolved_event_count: int
    #: The revenue half, per point, on the same argument (#351).
    unpriced_event_count: int
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
    #: The seats' counts added up, exactly as the cost above is: one seat's
    #: unresolved cost makes the business figure a floor too.
    unresolved_event_count: int
    #: And the revenue half's, added up the same way (#351).
    unpriced_event_count: int
    total_revenue_micros: int
    gross_margin_micros: int
    event_count: int


class BusinessMarginOut(Schema):
    business_id: str
    external_id: str
    totals: BusinessMarginTotals
    seats: list[SeatMarginOut]
