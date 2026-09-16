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
    #: profile this replaced could not do without a second record.
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


class MarginThresholdIn(Schema):
    min_margin_pct: float = 0.0
    consecutive_periods: int = Field(default=1, ge=1)
    provider_cost_spike_pct: float = 25.0


class MarginThresholdOut(Schema):
    min_margin_pct: float
    consecutive_periods: int
    provider_cost_spike_pct: float


# THE SWITCH'S REQUEST AND RESPONSE BODIES WERE HERE AND ARE GONE with the
# path that carried them (#497, slice 7 §9). The response published two fields
# — what had been set, and what it resolved to — which is a shape worth
# remembering: it existed because the setting alone could not say what it
# meant, the resolution being a second rule somewhere else. Nothing here
# replaces them.


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
    subscription_revenue_micros: int
    #: WHAT THE TENANT SAID IT EARNED ELSEWHERE, attributed to this window
    #: under the `recorded` basis (#496). Beside the Stripe figure above and
    #: never inside it: both are in `total_revenue_micros`, and this pair is
    #: what lets a reader of that total say which part UBB drove through
    #: Stripe and which part the tenant stated about a system UBB cannot see.
    supplied_revenue_micros: int
    usage_billed_micros: int
    usage_revenue_micros: int
    provider_cost_micros: int
    unresolved_event_count: int
    #: The revenue half's own count (#351). It bounds the margin the OTHER way
    #: from the count above it: an excluded cost makes the margin a ceiling, an
    #: excluded price makes it a floor, and a seat can be bounded both ways at
    #: once — which is why they are two properties and not one.
    unpriced_event_count: int
    total_revenue_micros: int
    gross_margin_micros: int
    margin_percentage: float
    event_count: int


# FIVE MARGIN BODIES WERE HERE AND ARE GONE (#501, slice 7 §1): one customer's
# margin, the per-customer list and its row, the tenant-wide summary, and the
# grouped breakdown with its row.
#
# ⚠ `SeatMarginOut` ABOVE SURVIVES AND ITS DOCSTRING IS NOW THE WHOLE STORY OF
# THAT SHAPE. One customer's read used to extend it with an identity and a
# window; what is left of it is a seat inside the business rollup, which is a
# TREE and keeps its own contract (§14).
#
# ⚠ AND THE GROUPED ROW IS WHERE THE DECLARED-VERSUS-OPEN ARGUMENT LIVED. It was
# the only one of three rollups over the same axes whose rows a schema named, so
# it was the only one a drift gate could see — which is why both completeness
# counts had to be declared on it explicitly (#327, #351) while the two untyped
# siblings carried them for free. `EconomicsOut` declares its row, so that
# asymmetry is gone rather than inherited.


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


# THE TREND AND ITS POINT WERE HERE AND ARE GONE (#501, slice 7 §1) — the last
# of the five this module gave up. Every field on the point was read straight
# off a stored margin snapshot, one row per month, which is what made the trend
# the clearest case for the read-time rule: a supplier cost that resolves in
# June moves March's margin, and a series read out of storage goes on drawing
# the old shape for as long as the rows survive. `bucket=month` on the one query
# derives each point from the facts as they stand when the question is asked.


class BusinessMarginTotals(Schema):
    # The per-seat sums plus the business's own subscription and supplied
    # revenue — no margin_percentage at the rollup level (the endpoint serves
    # none).
    subscription_revenue_micros: int
    #: WHAT THE TENANT SAID IT EARNED ELSEWHERE, attributed to this window
    #: under the `recorded` basis (#496). Beside the Stripe figure above and
    #: never inside it: both are in `total_revenue_micros`, and this pair is
    #: what lets a reader of that total say which part UBB drove through
    #: Stripe and which part the tenant stated about a system UBB cannot see.
    supplied_revenue_micros: int
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
