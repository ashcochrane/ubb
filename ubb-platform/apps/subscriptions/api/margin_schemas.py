from typing import Annotated, List, Optional
from ninja import Schema, Field

from core.amount_status_pairs import (
    PRICING_STATUS_REASON_MEANING, supplier_cost_total_meaning)
from apps.subscriptions.economics.services import MARGIN_REVENUE_BASIS
from core.currency_policy import FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_MEANING
from core.field_values import a_field_of
from core.report_windows import END_DATE_DESCRIPTION, START_DATE_DESCRIPTION


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

#: THE ONE BASIS EVERY MARGIN THIS PRODUCT COMPUTES PLACES SUPPLIED REVENUE
#: UNDER (`economics/services.py:MARGIN_REVENUE_BASIS`). The answers that
#: state it can return that value of `revenue_basis` and no other, so they
#: advertise that one alone (the owner's review of #621): the concept marker
#: stays, the export writes the `enum` from the registry, and the `Literal`
#: refuses any other value at the response.
MarginRevenueBasis = a_field_of("revenue_basis", MARGIN_REVENUE_BASIS)

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

#: WHY THAT STATUS APPLIES, where a published reason does (#603) — required
#: and nullable wherever `pricing_status` is published (the owner's ruling,
#: `6279966961`). Always null at this scope: a supplied window is `known` or
#: `unknown` for want of a supplied figure, and no published reason names
#: either. Declared rather than omitted, because a surface publishing the
#: status without the reason would be the third "field absent" state the
#: ruling refuses.
PricingStatusReason = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "pricing_status_reason"})]


class TenantSuppliedRevenueIn(Schema):
    """What a tenant states it earned from one customer over one period.

    ⚠ **NOT A CHARGE.** UBB neither created nor invoiced this money; the tenant
    bills its customers somewhere UBB cannot see and is supplying the figure so
    that margin can be computed at the scope it was supplied at.

    **THE WHOLE REVENUE FOR THAT CUSTOMER AND PERIOD, NOT AN ADDITION TO WHAT
    UBB PRICED** (#537). Where UBB also priced the customer's usage inside the
    period, the figure replaces that usage's revenue rather than adding to it.
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
    # The window the answer applied, as the caller's inclusive dates (#543):
    # it said `end` was exclusive until W5, and it no longer is anywhere.
    start: str = Field(description=START_DATE_DESCRIPTION)
    end: str = Field(description=END_DATE_DESCRIPTION)


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
    pricing_status_reason: Optional[PricingStatusReason] = Field(
        description=PRICING_STATUS_REASON_MEANING)
    totals: List[SuppliedRevenueTotalOut]
    records: List[AttributedSuppliedRevenueOut]


# WHAT `unresolved_event_count` MEANS EVERYWHERE BELOW, SAID ONCE (#328).
#
# It is the number of events the supplier cost beside it could not include —
# `Posting.provider_cost_micros` is nullable and a null means UBB has not
# resolved that cost (#317), so a total built over the column is the sum of
# the resolved costs wherever this is non-zero, and every margin derived from
# it is not the margin either — in either direction, since an omitted cost may
# be negative (#603). Zero means the figure is whole.
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
    #: under the `recognised` basis every margin figure is stated under
    #: (`economics/services.py:MARGIN_REVENUE_BASIS`, #496; this comment said
    #: `recorded` until #512 found it). Beside the Stripe figure above and
    #: never inside it: both are in `total_revenue_micros`, and this pair is
    #: what lets a reader of that total say which part UBB drove through
    #: Stripe and which part the tenant stated about a system UBB cannot see.
    supplied_revenue_micros: int
    usage_billed_micros: int
    usage_revenue_micros: int
    provider_cost_micros: int = Field(description=supplier_cost_total_meaning(
        "this customer's events in the window the margin covers"))
    unresolved_event_count: int
    #: The revenue half's own count (#351), kept apart from the count above it:
    #: an excluded cost or an excluded price leaves the margin incomplete, in a
    #: direction nobody can state (#603), and a seat can be missing both at
    #: once — which is why they are two properties and not one.
    unpriced_event_count: int
    foreign_currency_subscription_count: int = Field(
        description=FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_MEANING)
    total_revenue_micros: int
    gross_margin_micros: int
    margin_percentage: float
    posting_count: int = Field(description=(
        "How many postings this customer has in the window the margin "
        "covers — every posting, whatever its kind, so it can include a Task "
        "Charge's projected posting. It is not the `recorded_events` measure."))


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
    #: A margin named as unprofitable is INCOMPLETE wherever this is non-zero:
    #: it is the sum of what resolved, and the count says how many supplier
    #: costs it leaves out — in a direction nobody can state (#603).
    unresolved_event_count: int
    #: ⚠ AND SO IS IT WHEREVER THIS ONE IS (#351). An excluded PRICE means
    #: revenue was left out of the figure that named this customer
    #: unprofitable. Publishing only the count above — the one that cannot say
    #: it — would have made this list the more misleading of the two surfaces.
    unpriced_event_count: int
    foreign_currency_subscription_count: int = Field(
        description=FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_MEANING)
    margin_percentage: float


class UnprofitableOut(Schema):
    period_start: str
    #: WHICH VIEW THE SUPPLIED REVENUE INSIDE EVERY FLAGGED MARGIN WAS PLACED
    #: UNDER (#548, W5 ruling 15). The flags are raised on margins computed
    #: under the recognised basis (`economics/services.py:MARGIN_REVENUE_BASIS`),
    #: one basis for the whole list; required and never null, so a console
    #: states the basis this answer names rather than a constant of its own.
    basis: MarginRevenueBasis
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
    #: under the `recognised` basis every margin figure is stated under
    #: (`economics/services.py:MARGIN_REVENUE_BASIS`, #496; this comment said
    #: `recorded` until #512 found it). Beside the Stripe figure above and
    #: never inside it: both are in `total_revenue_micros`, and this pair is
    #: what lets a reader of that total say which part UBB drove through
    #: Stripe and which part the tenant stated about a system UBB cannot see.
    supplied_revenue_micros: int
    usage_revenue_micros: int
    provider_cost_micros: int = Field(description=supplier_cost_total_meaning(
        "every seat's events in the window, the seats' own totals added up"))
    #: The seats' counts added up, exactly as the cost above is: one seat's
    #: unresolved cost leaves the business figure incomplete too.
    unresolved_event_count: int
    #: And the revenue half's, added up the same way (#351).
    unpriced_event_count: int
    #: The seats' foreign subscriptions plus the business's own (#564).
    foreign_currency_subscription_count: int = Field(
        description=FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_MEANING)
    total_revenue_micros: int
    gross_margin_micros: int
    posting_count: int = Field(description=(
        "The seats' posting counts added up. Each counts every posting in the "
        "window, so it can include a Task Charge's projected posting."))


class BusinessMarginOut(Schema):
    business_id: str
    external_id: str
    #: WHICH VIEW EVERY SUPPLIED REVENUE FIGURE IN THIS ANSWER IS STATED UNDER
    #: (#548, W5 ruling 15) — the totals and every seat alike, one basis for
    #: the whole tree. Required and never null: the rollup always places
    #: supplied revenue under the recognised basis
    #: (`economics/services.py:MARGIN_REVENUE_BASIS`), and a console reading a
    #: figure off it shows the basis the answer states rather than a constant
    #: of its own.
    basis: MarginRevenueBasis
    totals: BusinessMarginTotals
    seats: list[SeatMarginOut]
