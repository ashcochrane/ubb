from typing import Annotated, List, Optional
from ninja import Schema, Field


# --- Tenant-supplied revenue (#495, slice 7 §9) -----------------------------
#
# THE THREE CONCEPT MARKERS THIS MODULE DECLARES, and why declaring them here
# is not a second copy of anything. A marker names a concept and spells not one
# of its values — the values arrive at export time from the registry's own
# generated decision document — so an alias is a pointer, and a module that
# publishes a field carrying a concept declares the pointer beside the field.
# `apps/platform/events/schemas.py` already declares its own `PricingStatus`
# for exactly this reason, beside the payloads that carry it.

#: HOW A SUPPLIED REVENUE RECORD IS SPREAD OVER THE SPAN IT DECLARES. `closed`
#: — UBB owns both values — so the export writes a real `enum` here and this
#: file spells neither of them. No hand-written `description`: the registry owns
#: this concept's summary, and a sentence restating it here would be a second
#: copy no gate reads.
RecognitionMethod = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "recognition_method"})]

#: WHICH OF THE TWO VIEWS A REVENUE FIGURE IS STATED UNDER. Present on every
#: response that serves one, never optional: a figure whose basis is unstated
#: is the unlabelled proration slice 7 §5 exists to end, and an absent field
#: would be exactly that.
RevenueBasis = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "revenue_basis"})]

#: WHETHER CUSTOMER REVENUE FOR THE WINDOW IS SETTLED, AND IF NOT, WHY NOT.
#: The same four states the posting carries (#153 §3.4 rules this slice adds no
#: fifth) — here answering the question at the supplied scope: `known` where a
#: figure the tenant supplied is attributable to this window, `unknown` where
#: none is. `unknown` is why the totals beside it are an EMPTY LIST rather than
#: a zero: revenue UBB does not know is not revenue of nothing.
#:
#: ⚠ `known` DOES NOT CLAIM THE WINDOW IS FULLY COVERED, and it cannot: UBB
#: has no way to tell a period the tenant has not supplied yet from one in
#: which the customer generated nothing, so "fully covered" is not a fact
#: available to this surface. The contributing `records` carry their own
#: periods, which is where coverage is read from.
PricingStatus = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "pricing_status"})]


class TenantSuppliedRevenueIn(Schema):
    """What a tenant states it earned from one customer over one period.

    ⚠ **NOT A CHARGE.** UBB neither created nor invoiced this money; the tenant
    bills its customers somewhere UBB cannot see and is supplying the figure so
    that margin can be computed at the scope it was supplied at.
    """

    amount_micros: int
    currency: str
    #: ISO dates. The end is EXCLUSIVE and may be omitted for revenue that is
    #: an instant rather than a span; a partial period is therefore expressible
    #: by writing the part the record covers, which is what the recurring
    #: profile this replaces could not do without a second record.
    period_start: str
    period_end: Optional[str] = None
    recognition_method: RecognitionMethod
    #: The tenant's own handle for where the number came from — required, and
    #: refused blank. It is part of the record's identity: two figures covering
    #: one month from two sources are two facts, and re-supplying the same
    #: source for the same period re-states one.
    source_reference: str


class TenantSuppliedRevenueOut(Schema):
    """One supplied record, as the tenant stated it."""

    id: str
    amount_micros: int
    currency: str
    period_start: str
    period_end: Optional[str] = None
    recognition_method: RecognitionMethod
    source_reference: str
    #: When UBB accepted the statement — not when the money was earned, which
    #: is what the period above says.
    recorded_at: str


class AttributedSuppliedRevenueOut(TenantSuppliedRevenueOut):
    """One supplied record and what a window gets of it under one basis."""

    #: What the requested window gets of `amount_micros` above under the
    #: response's stated basis. Equal to the whole amount wherever nothing was
    #: distributed, which is every record under the `recorded` basis and every
    #: `on_receipt` record under either.
    attributed_amount_micros: int


class SuppliedRevenueTotalOut(Schema):
    """One currency's worth of the window's attributed supplied revenue."""

    currency: str
    amount_micros: int


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


class SuppliedRevenueWindowOut(Schema):
    """The window's supplied revenue, under a basis the response NAMES (#495).

    **The totals are a list per currency and never a single figure**, because a
    single figure summed across currencies is a wrong number, and this slice's
    whole subject is revenue figures that say what they are. The normal answer
    is a one-element list; a customer whose supplied records are denominated
    two ways gets two entries rather than a total that is true of neither.

    **An empty list is how `unknown` is served, and it is never a zero.** A
    tenant that has supplied nothing for this window has revenue UBB does not
    know — margin is unavailable there, not nil — and a `0` here would be the
    silent-zero #153 §3.4 refuses by name.
    """

    basis: RevenueBasis
    window: PeriodWindow
    pricing_status: PricingStatus
    totals: List[SuppliedRevenueTotalOut]
    records: List[AttributedSuppliedRevenueOut]


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
