"""Metering Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(billing, subscriptions, referrals) to read metering data.
Functions return plain dicts, never ORM instances.

If metering becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/tenant_billing/services.py → get_period_totals()
- api/v1/billing_endpoints.py → get_revenue_analytics()
- apps/referrals/rewards/reconciliation.py → get_customer_usage_for_period()
- apps/billing/gating/tasks.py → get_customer_ids_with_usage()
- apps/billing/invoicing/tasks.py → get_customer_ids_with_usage()
- apps/billing/invoicing/services/postpaid_service.py → get_customer_cost_totals(),
  get_billed_totals_by_customer(), get_customer_billed_breakdown()
- apps/billing/wallets/tasks.py → iter_billable_usage_events()
- apps/subscriptions/handlers.py → get_usage_event_effective_at()
- apps/subscriptions/tasks.py → list_backfill_dirty_periods(),
  clear_backfill_dirty_period() (the ack half of the marker contract)
- api/v1/me_endpoints.py → get_customer_usage_summary()
- api/v1/metering_endpoints.py → get_unresolved_queue(),
  get_projected_adjustment(), get_waived_loss() (the three recovery reads, #364)
- api/v1/spend_control_endpoints.py → stop_context_postings() (the itemised
  events of Stops and breaches, #465), charge_that_reached() (the Charge a
  pool episode cites where the crossing was detected off the recording route)
"""
import uuid
from datetime import date, datetime
from typing import Iterator, TypedDict

from django.db.models import Sum, Count
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import TruncDate

from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY, carry_cost_total,
    cost_total_annotations,
)
from core.time_windows import month_bounds, utc_day_start, utc_next_day_start
from core.vocabulary import (
    ANALYTICS_GROUPING_KIND_FIELD,
    ANALYTICS_GROUPING_KIND_ROLLUP,
    ANALYTICS_GROUPING_KIND_VALUES,
    ANALYTICS_MEASURE_SUPPLIER_COGS,
    ANALYTICS_ROLLUP_EVENT_CATEGORY,
    ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT,
    ANALYTICS_ROLLUP_VALUES,
    PRICING_STATUS_WAIVED,
)
from apps.platform.grouping_fields.models import (
    RESERVED_KEYS, SCOPE_CHOICES, SLOT_CHOICES)

#: The slot columns a caller may group by, read off the registry that owns the
#: vocabulary. Restating it as a literal range here is how the two come to
#: disagree.
SLOTS = tuple(slot for slot, _ in SLOT_CHOICES)

# EVERY MONEY TOTAL IN THIS MODULE IS A PAIR, ON BOTH SIDES OF THE MARGIN
# (#327, #351).
#
# `Posting.provider_cost_micros` is nullable and `NULL` means *not resolved*
# (#317). `Posting.billed_cost_micros` is nullable too and `NULL` there means
# *UBB could not resolve this price* (#351). A bare `Sum` over either answers a
# number that looks complete and is not, so every function below that returns
# one returns the resolved sum AND its completeness count beside it, built
# together by `core.cost_totals` from the pair declared in
# `core.amount_status_pairs`.
#
# ⚠ TWO COUNTS, NOT ONE, AND THEY ARE NOT INTERCHANGEABLE. `unresolved_event_count`
# is about postings whose SUPPLIER COST UBB has not learned;
# `unpriced_event_count` is about postings whose CUSTOMER PRICE it could not
# resolve. They are different sets of rows — an event can carry a settled cost
# and an unknown price, and the reverse — and most queries here total both pairs
# in one statement, where a single key would have the second annotation
# overwrite the first.
#
# ⚠ AND THE `or 0` IS GONE FROM THE BILLED HALF FOR THE SAME REASON IT WENT
# FROM THE COST HALF. It was live where the aggregate was ungrouped, on the
# argument that a grouped `Sum` cannot answer `None` over a NOT NULL column —
# a group exists only because a row produced it. **That argument died with the
# NOT NULL.** Over a nullable column a group CAN answer `None`: every row in it
# may be unpriced. The coalescing rule is now the helper's, at every site,
# grouped or not, and `or 0` reproduces exactly the ambiguity the nullable
# column just stopped having.
#
# ⚠ THREE `pricing_status` VALUES NULL THE AMOUNT AND ONLY ONE IS COUNTED.
# `unknown` is missing information; `waived` is a charge somebody decided not to
# pursue and `not_applicable` is a subject with no customer revenue at this
# level, and both of those are genuine zeroes. `core.amount_status_pairs` is
# where that is argued; nothing here restates it, and no reader picks the set
# for itself.

#: What a grouped analytics row calls the value it groups.
#:
#: THE SAME PROPERTY `GroupingFieldMarginRow` DECLARES on
#: `/margin/by-grouping-field`, and its comment carries the reading: the VALUE
#: the row groups, not the axis it was grouped on — the axis is already named by
#: the request's `group_by`. Three rollups answer that question over the same
#: axes and only that one declares its rows; the other two return `list[dict]`,
#: so no schema, drift gate or breaking gate can hold them to it.
#:
#: It is a shared constant rather than a literal in each writer BECAUSE the two
#: open rollups are written in different modules and one of them is in the
#: composition layer. Spelled twice they can drift, and the only thing that
#: would notice is a test — after the fact, and only if somebody wrote one.
#: Spelled once they cannot. `api/v1/tests/test_analytics_dimensions.py` still
#: asserts both whole rows against the running routes, because a shared constant
#: proves the two AGREE and not that either is what the console and the SDK read.
#:
#: ⚠ THE THREE ROLLUPS SHARE A SECOND PROPERTY NOW, AND THE DECLARED ONE HAD TO
#: BE TOLD (#327). All three carry `unresolved_event_count` — but a key the
#: declared row does not name is a key django-ninja DROPS, so `#327` added it to
#: `GroupingFieldMarginRow` in the same commit that started attaching it here.
#: Two open rollups gaining a key silently while the declared one loses it is
#: precisely the divergence this constant exists to make impossible.
GROUPED_VALUE_KEY = "grouping_field_value"


class PeriodTotals(TypedDict):
    #: What the tenant's customers were CHARGED, and how much of it UBB could
    #: price. It was documented here as "never partial: the column is NOT NULL"
    #: — that sentence died with the NOT NULL in #351, and it is replaced rather
    #: than deleted so a reader meets the change where the old claim stood. Both
    #: halves of the margin can now be floors, and each says so with its own
    #: count.
    total_cost_micros: int
    unpriced_event_count: int
    event_count: int
    #: What the SUPPLIER charged, and how much of it UBB has learned. The pair
    #: travels together for the reason `core.cost_totals` states: a bare sum
    #: over a nullable column answers a number that looks complete and is not.
    #: It is here because the period close is the moment a month stops being
    #: revisable, and a month that closes without saying what it could not
    #: account for is exactly the silence #329 removes.
    total_provider_cost_micros: int
    unresolved_event_count: int


#: STILL SPELLS THE RETIRED NOUN, DELIBERATELY, AND NOBODY OWNS IT YET (#269).
#:
#: #269 renamed the model and its table; it did not rename the *names built on*
#: the model, and the ticket says so — "the model, the table, the two neighbours
#: that reference it, and the tests that name it". Three groups survive the
#: rename and they are not in the same position:
#:
#:   * `UsageEventOut` / `UsageEventDetailOut` (`api/v1/schemas.py`) are on the
#:     PUBLISHED contract. Renaming a schema is a contract break, and ADR-0007 §3
#:     forbids doing it twice on one field — so it happens once, deliberately,
#:     in whichever slice rebuilds that surface.
#:   * `iter_billable_usage_events` and `get_usage_event_cost` are `queries.py`
#:     read-contract entry points, consumed across a product boundary
#:     (`apps/billing/wallets/`). Renaming them is a same-commit change on both
#:     sides, cheap but out of #269's stated extent.
#:   * This TypedDict is neither: it is internal to metering and it names a
#:     thing that is now called something else. It is the one of the three with
#:     no reason to wait, and it is recorded here rather than renamed only
#:     because #269 declined to widen — a later reader should treat it as
#:     payable, not as a decision.
class UsageEventCost(TypedDict):
    #: `None` where UBB could not resolve a customer price (#351), exactly as
    #: the supplier half below has been since #317. A PER-EVENT row, so it
    #: carries no count either — `pricing_status` is what a caller adding these
    #: up reads instead.
    billed_cost_micros: int | None
    #: WHICH READING THAT NULL TAKES. Only `unknown` is missing information;
    #: `waived` and `not_applicable` are genuine zeroes, and a caller that
    #: counted all three would report every metering-only tenant's every period
    #: as partial forever.
    pricing_status: str
    #: `None` where UBB has not resolved the supplier's cost (#317) AND where
    #: the Event Type declares there is none. This is a PER-EVENT row rather
    #: than a total, so it carries no count — but the null alone does not say
    #: which of the two it is, and a caller adding these up has to know
    #: (#328). That is what the status beside it is for.
    provider_cost_micros: int | None
    #: WHICH READING THE NULL ABOVE TAKES: `unresolved` is a cost UBB has yet to
    #: learn, `not_applicable` is one that does not exist, and only the first is
    #: missing information. A caller totalling these rows counts the first and
    #: ignores the second — counting both would report every metering-only
    #: tenant's every period as partial forever (#327).
    costing_status: str


def get_period_totals(tenant_id: str, period_start: date, period_end: date,
                      basis: str = "effective") -> PeriodTotals:
    """Get aggregate usage totals for a tenant's billing period.

    Returns BOTH pairs — the resolved customer-price total with
    `unpriced_event_count`, and the resolved supplier-cost total with
    `unresolved_event_count` — plus the event count.
    basis="effective" windows on effective_at (when the usage happened);
    basis="arrival" windows on created_at (when it was recorded) — used by
    tenant platform-fee reconciliation, which accrues fees in the ARRIVAL
    period to match the wall-clock live accumulator.

    THE TWO TOTALS ARE THE SAME KIND OF NUMBER SINCE #351, AND EACH CARRIES ITS
    OWN CAVEAT. This docstring used to say the opposite — that the billed sum
    "passes over nothing and is complete by construction" while only the
    supplier sum was a floor — and it was true of a NOT NULL column. Both are
    floors now, and the two counts are about different rows, so neither may be
    read as a caveat on the other. Both pairs are built by `core.cost_totals` in
    the SAME query as the total each qualifies, which is what stops one group's
    exclusions being counted against another's.

    ⚠ This is the period close's input, and the close is where a month stops
    being revisable. #329 already refuses to close a period holding supplier
    cost nobody accounted for; the same question about an unresolved customer
    price is a policy this ticket does not decide, and the number it would need
    is now here rather than absent.
    """
    from apps.metering.usage.models import Posting

    if basis not in ("effective", "arrival"):
        raise ValueError("basis must be 'effective' or 'arrival'")
    field = "created_at" if basis == "arrival" else "effective_at"
    aggregated = Posting.objects.filter(
        tenant_id=tenant_id,
        **{f"{field}__gte": utc_day_start(period_start),
           f"{field}__lt": utc_day_start(period_end)},
    ).aggregate(
        event_count=Count("id"),
        **cost_total_annotations(CUSTOMER_PRICE, key="total_cost"),
        **cost_total_annotations(SUPPLIER_COST, key="total_provider_cost_micros"),
    )
    # One call per pair. Each touches only its own two keys, so the order is
    # immaterial and neither can consume the other's count.
    totals = carry_cost_total(CUSTOMER_PRICE, aggregated, key="total_cost")
    totals = carry_cost_total(SUPPLIER_COST, totals,
                              key="total_provider_cost_micros")

    return {
        "total_cost_micros": totals["total_cost"],
        UNPRICED_EVENT_COUNT_KEY: totals[UNPRICED_EVENT_COUNT_KEY],
        "event_count": totals["event_count"] or 0,
        "total_provider_cost_micros": totals["total_provider_cost_micros"],
        UNRESOLVED_EVENT_COUNT_KEY: totals[UNRESOLVED_EVENT_COUNT_KEY],
    }


class UsageEventPrice(TypedDict):
    #: `None` where UBB could not resolve a customer price (#351). Zero still
    #: means priced at exactly nothing.
    billed_cost_micros: int | None
    #: WHICH READING THE NULL ABOVE TAKES — `unknown` is a price UBB does not
    #: have, `waived` is one somebody decided not to pursue, `not_applicable` is
    #: a subject with no customer revenue at this level. A caller with only the
    #: amount cannot tell the three apart.
    pricing_status: str


def get_usage_event_cost(usage_event_id: str,
                         tenant_id: str | None = None) -> UsageEventPrice | None:
    """One posting's customer price and the status that qualifies it.

    Returns `None` — and ONLY `None` — when there is no such posting. If
    tenant_id is provided, a posting belonging to another tenant is no such
    posting.

    ⚠ IT RETURNED A BARE `int | None` UNTIL #351, AND THE TWO MEANINGS OF THAT
    `None` HAD JUST BECOME THREE. `None` meant "no such event", and the one
    caller — the wallet's refund path — refused with `usage_event_not_found` on
    it. Once the column went nullable, a posting that exists and whose price UBB
    could not resolve answered the same `None`, so a real event would have been
    reported to a tenant as missing. Returning the row rather than the number
    keeps "there is no such posting" a statement this function alone can make,
    and hands the caller the status it needs to say anything else.
    """
    from apps.metering.usage.models import Posting

    qs = Posting.objects.filter(id=usage_event_id)
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    return qs.values("billed_cost_micros", "pricing_status").first()


class RevenueAnalytics(TypedDict):
    total_provider_cost_micros: int
    #: How many postings the provider total could not include.
    unresolved_event_count: int
    total_billed_cost_micros: int
    #: How many postings the BILLED total could not include (#351). A second
    #: count and not a duplicate of the one above: the two are about different
    #: rows, and a window can be complete on one side of the margin and a floor
    #: on the other.
    unpriced_event_count: int
    #: Bounded by BOTH counts, and carrying neither of its own. The markup is
    #: arithmetic over the two totals, and arithmetic does not mint a third
    #: fact — there are two, and they are already stated.
    total_markup_micros: int
    daily: list[dict]


def get_revenue_analytics(
    tenant_id: str, start_date: date = None, end_date: date = None,
) -> RevenueAnalytics:
    """Get revenue analytics with totals and daily breakdown.

    Returns dict with total provider/billed/markup costs, BOTH completeness
    counts, and a daily list of dicts with day, provider_cost_micros,
    unresolved_event_count, billed_cost_micros, unpriced_event_count,
    event_count.

    The markup is the RESOLVED billed total minus the RESOLVED provider cost, so
    it is bounded in both directions where either count is non-zero — a floor
    where prices are missing, a ceiling where costs are. It carries no count of
    its own because there is no third fact here: the two counts beside it are
    the whole of what was excluded, and arithmetic over two totals does not make
    a third.
    """
    from apps.metering.usage.models import Posting

    qs = Posting.objects.filter(tenant_id=tenant_id)

    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))

    aggregated = qs.aggregate(
        **cost_total_annotations(SUPPLIER_COST, key="total_provider_cost_micros"),
        **cost_total_annotations(CUSTOMER_PRICE, key="total_billed_cost_micros"),
    )
    totals = carry_cost_total(SUPPLIER_COST, aggregated,
                              key="total_provider_cost_micros")
    totals = carry_cost_total(CUSTOMER_PRICE, totals,
                              key="total_billed_cost_micros")

    provider_cost = totals["total_provider_cost_micros"]
    billed_cost = totals["total_billed_cost_micros"]

    daily = []
    for entry in qs.annotate(day=TruncDate("effective_at")).values("day").annotate(
        **cost_total_annotations(SUPPLIER_COST, key="provider_cost_micros"),
        **cost_total_annotations(CUSTOMER_PRICE, key="billed_cost_micros"),
        event_count=Count("id"),
    ).order_by("day"):
        row = carry_cost_total(SUPPLIER_COST, entry, key="provider_cost_micros")
        daily.append(carry_cost_total(CUSTOMER_PRICE, row,
                                      key="billed_cost_micros"))

    for entry in daily:
        if entry.get("day"):
            entry["day"] = entry["day"].isoformat()

    # THE MARKUP IS WHAT UBB KNOWS IT CHARGED MINUS WHAT IT KNOWS IT PAID.
    #
    # This used to answer 0 whenever the provider aggregate came back `None`,
    # which was harmless while that column was NOT NULL — `None` then meant "no
    # rows", and billed was 0 too. #317 gave it a second meaning ("every cost
    # here is unresolved") and the subtraction became unconditional. #351 does
    # the same to the other operand: `billed_cost` carried an `or 0` on the
    # argument that its column could not be null, and that argument is gone.
    # Both sides are now resolved sums, and BOTH counts say how far the answer
    # can be off — in opposite directions.
    markup = billed_cost - provider_cost

    return {
        "total_provider_cost_micros": provider_cost,
        UNRESOLVED_EVENT_COUNT_KEY: totals[UNRESOLVED_EVENT_COUNT_KEY],
        "total_billed_cost_micros": billed_cost,
        UNPRICED_EVENT_COUNT_KEY: totals[UNPRICED_EVENT_COUNT_KEY],
        "total_markup_micros": markup,
        "daily": daily,
    }


def get_customer_usage_for_period(
    tenant_id: str, customer_id: str, period_start: date, period_end: date,
) -> list[UsageEventCost]:
    """Get per-event usage data for a customer in a period.

    Returns list of dicts with billed_cost_micros, pricing_status,
    provider_cost_micros and costing_status. Used by referrals reconciliation.

    ⚠ THESE ARE ROWS, NOT A TOTAL, so no count travels with them — a row states
    its own completeness in the only place it can, in the value itself. What a
    caller may NOT do is add them up as though `None` were zero: that is the
    defect this slice deletes, one step further out.

    ⚠ AND THE NULL NEEDS THE STATUS TO BE READ (#328). #327 described the null
    as saying the cost is unresolved; that was half of it. A cost the Event Type
    declares does not exist is null too, and the two must be totalled
    differently — the first is excluded and counted, the second contributes a
    genuine zero and is not. A caller with only the amount cannot tell them
    apart, so the status travels with every row.
    """
    from apps.metering.usage.models import Posting

    events = Posting.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
        effective_at__gte=period_start,
        effective_at__lt=period_end,
    ).values("billed_cost_micros", "pricing_status", "provider_cost_micros",
             "costing_status")

    return list(events)


class CustomerUsageSummary(TypedDict):
    total_billed_micros: int
    #: How many of this customer's postings the total above could not include
    #: (#351). The grand count is the sum of the rows' counts, exactly as the
    #: grand total is the sum of the rows' totals — the same "by construction"
    #: relation, extended to the caveat so a reader cannot get one without the
    #: other.
    unpriced_event_count: int
    event_count: int
    metrics: list[dict]


def get_customer_usage_summary(tenant_id, customer_id, period_start: date,
                               period_end: date) -> CustomerUsageSummary:
    """Per-event_type usage rollup for ONE customer over [period_start, period_end).

    Each row: {event_type, billed_cost_micros, event_count}; the grand
    totals equal the sum of the rows by construction. A BUSINESS customer
    aggregates across its seats — the same seat basis as the postpaid business
    branch (aggregate_lines): ALL seats incl. soft-deleted via all_objects, ONE
    grouped query via customer_id__in; a business emits no usage of its own.
    Rows sort largest-billed first (ties by event_type). Sargable half-open day
    window via core.time_windows.

    The rollup ITSELF is what replaced the posting's inline unit total (#272):
    one comparable magnitude per Event Type, rather than one nameless integer
    summed across Event Types whose granularities differ.
    """
    from apps.metering.usage.models import Posting
    from apps.platform.customers.models import Customer

    customer_ids = [customer_id]
    account_type = Customer.all_objects.filter(id=customer_id).values_list(
        "account_type", flat=True).first()
    if account_type == "business":
        customer_ids = list(Customer.all_objects.filter(
            parent_id=customer_id).values_list("id", flat=True))
        if not customer_ids:
            return {"total_billed_micros": 0, UNPRICED_EVENT_COUNT_KEY: 0,
                    "event_count": 0, "metrics": []}

    rows = (Posting.objects.filter(
        tenant_id=tenant_id, customer_id__in=customer_ids,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    ).values("event_type").annotate(
        **cost_total_annotations(CUSTOMER_PRICE, key="billed_sum"),
        cnt=Count("id"),
    ).order_by())

    metrics = sorted(
        ({"event_type": r["event_type"],
          "billed_cost_micros":
              carry_cost_total(CUSTOMER_PRICE, dict(r),
                               key="billed_sum")["billed_sum"],
          UNPRICED_EVENT_COUNT_KEY: r[UNPRICED_EVENT_COUNT_KEY],
          "event_count": r["cnt"]}
         for r in rows),
        key=lambda m: (-m["billed_cost_micros"], m["event_type"]))
    return {
        "total_billed_micros": sum(m["billed_cost_micros"] for m in metrics),
        # The grand caveat is the sum of the rows' caveats, the same way the
        # grand total is the sum of the rows' totals. Re-aggregating it would be
        # a second query answering a question these rows already answer.
        UNPRICED_EVENT_COUNT_KEY: sum(m[UNPRICED_EVENT_COUNT_KEY]
                                      for m in metrics),
        "event_count": sum(m["event_count"] for m in metrics),
        "metrics": metrics,
    }


def get_customer_cost_totals(tenant_id, customer_id, start_date, end_date) -> dict:
    """Provider + billed cost totals for one customer over [start, end).

    Each total travels with its own count: `unresolved_event_count` says how
    many of those events carry a supplier cost UBB has not resolved,
    `unpriced_event_count` how many carry a customer price it could not resolve.
    Different events, so different numbers.
    """
    from apps.metering.usage.models import Posting
    agg = Posting.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        effective_at__gte=utc_day_start(start_date),
        effective_at__lt=utc_day_start(end_date),
    ).aggregate(
        **cost_total_annotations(SUPPLIER_COST, key="provider_cost_micros"),
        **cost_total_annotations(CUSTOMER_PRICE, key="billed"),
        count=Count("id"),
    )
    agg = carry_cost_total(SUPPLIER_COST, agg, key="provider_cost_micros")
    agg = carry_cost_total(CUSTOMER_PRICE, agg, key="billed")
    return {
        "provider_cost_micros": agg["provider_cost_micros"],
        UNRESOLVED_EVENT_COUNT_KEY: agg[UNRESOLVED_EVENT_COUNT_KEY],
        "billed_cost_micros": agg["billed"],
        UNPRICED_EVENT_COUNT_KEY: agg[UNPRICED_EVENT_COUNT_KEY],
        "event_count": agg["count"] or 0,
    }


def get_billing_owner_billed_total(tenant_id, billing_owner_id, start_date,
                                   end_date) -> dict:
    """The resolved billed total for one billing owner over [start, end), as a pair.

    OWNER-aggregates a pooled business across all its seats (each seat's events
    pin the business as billing owner) and reduces to a single seat for an
    allocated/individual owner (whose events pin themselves). It is the durable
    source of truth the Tier-2 postpaid live-spend counter MAX-merges toward
    (apps.billing.gating.services.live_counter).

    ⚠ IT RETURNED A BARE `int` WITH AN `or 0` UNTIL #351, AND THAT IS WHY IT IS
    A PAIR NOW. The counter this feeds compares a durable total against a live
    one and takes the larger, so a floor reported as a figure understates spend
    — it does not overcharge anybody, it lets a line be crossed later than it
    should be. That is a spend-control input rather than a report: the pool's
    stop line races it (#459, known-over fires on this pair and an unknown is
    never summed as zero), and what #351 owed that line was a number that
    says when it is incomplete instead of one that quietly is.
    """
    from apps.metering.usage.models import Posting
    return carry_cost_total(CUSTOMER_PRICE, Posting.objects.filter(
        tenant_id=tenant_id, billing_owner_id=billing_owner_id,
        effective_at__gte=utc_day_start(start_date),
        effective_at__lt=utc_day_start(end_date),
    ).aggregate(**cost_total_annotations(CUSTOMER_PRICE, key="billed")),
        key="billed")


def get_usage_timeseries(tenant_id, *, granularity="day", customer_id=None,
                         group_by=None, start_date=None, end_date=None) -> list[dict]:
    """Time-series spend rollup: daily or hourly COGS per tenant, optionally
    per customer or per grouping field.

    Returns list of dicts with bucket (ISO string), provider_cost_micros,
    unresolved_event_count, billed_cost_micros, unpriced_event_count,
    markup_micros, event_count, and optionally grouping_field_value (when
    group_by is set).

    Each bucket carries its OWN completeness, on both sides: an unresolved cost
    or an unresolved price belongs to the bucket it fell in, and a tenant
    reading one day of a month must be told about that day rather than about the
    month.
    """
    from django.db.models.functions import TruncHour
    from apps.metering.usage.models import Posting

    trunc = TruncHour if granularity == "hour" else TruncDate
    qs = Posting.objects.filter(tenant_id=tenant_id)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # end_date is INCLUSIVE, matching the /analytics/usage rollup — this is
        # the sole caller (the /analytics/usage/timeseries endpoint), so the two
        # sibling endpoints resolve the same date inputs identically.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))

    valid_group_by = ("provider", "event_type", "task_type", "subtask_type",
                      *SLOTS)
    cols = ["bucket"]
    if group_by in valid_group_by:
        cols.append(group_by)

    rows = (qs.annotate(bucket=trunc("effective_at")).values(*cols).annotate(
        **cost_total_annotations(SUPPLIER_COST, key="provider_cost_micros"),
        **cost_total_annotations(CUSTOMER_PRICE, key="billed_cost_micros"),
        event_count=Count("id")).order_by("bucket"))

    out = []
    for r in rows:
        d = carry_cost_total(SUPPLIER_COST, dict(r), key="provider_cost_micros")
        d = carry_cost_total(CUSTOMER_PRICE, d, key="billed_cost_micros")
        d["bucket"] = d["bucket"].isoformat() if d.get("bucket") else None
        if group_by and group_by in d:
            raw_value = d.pop(group_by)
            # Map empty string or None to the unattributed sentinel so no events
            # are silently dropped and every timeseries bucket reconciles to the total.
            # The key is `GROUPED_VALUE_KEY` above, shared with the sibling
            # `/analytics/usage` breakdown so the two cannot drift apart.
            d[GROUPED_VALUE_KEY] = raw_value if raw_value else "(unattributed)"
        # What UBB knows it charged minus what it knows it paid, bounded by
        # this bucket's OWN two counts rather than by the window's.
        #
        # ⚠ THE COMMENT HERE USED TO READ "no coalesce on the billed half: this
        # aggregate is grouped over a NOT NULL column, so a bucket exists only
        # because a row produced one." That was sound and it is now false. A
        # bucket still exists only because a row produced it — but over a
        # nullable column its `Sum` can still answer `None`, because every row
        # in the bucket may be unpriced. Both halves are coalesced by the
        # helper, at the same point, by the same rule.
        d["markup_micros"] = d["billed_cost_micros"] - d["provider_cost_micros"]
        out.append(d)
    return out


def get_per_customer_cost_totals(tenant_id, start_date, end_date) -> list[dict]:
    """Per-customer provider + billed totals over [start, end).

    Each customer's totals carry their own counts — one customer's unresolved
    cost or unresolved price does not make another's total partial.
    """
    from apps.metering.usage.models import Posting
    rows = (Posting.objects.filter(
        tenant_id=tenant_id,
        effective_at__gte=utc_day_start(start_date),
        effective_at__lt=utc_day_start(end_date),
    ).values("customer_id").annotate(
        **cost_total_annotations(SUPPLIER_COST, key="provider_cost_micros"),
        **cost_total_annotations(CUSTOMER_PRICE, key="billed_cost_micros"),
        event_count=Count("id"),
    ).order_by("-billed_cost_micros"))
    return [carry_cost_total(
        CUSTOMER_PRICE,
        carry_cost_total(SUPPLIER_COST, dict(r), key="provider_cost_micros"),
        key="billed_cost_micros") for r in rows]


def get_dimensional_margin(tenant_id, *, group_by=None, tag_key=None,
                           start_date=None, end_date=None) -> list[dict]:
    """Usage-only margin (billed - provider) grouped by a column or a tag key.

    group_by in {"provider", "event_type", "task_type", "subtask_type",
    "grouping_field_1".."grouping_field_10"} (a resolved column, not a
    tenant-facing key — the caller resolves the tenant's declared name via the
    Grouping Field registry first);
    OR tag_key for a key read out of the open bag.
    Each row: {grouping_field_value, provider_cost_micros,
    unresolved_event_count, billed_cost_micros, unpriced_event_count,
    margin_micros, event_count}.

    A margin over a cost total that excluded an event is a CEILING on a margin;
    over a price total that excluded one it is a FLOOR. Both counts say so, and
    a row can be bounded in both directions at once. Rows still sort on the
    margin they can state.

    The row key names the VALUE grouped rather than the axis it was grouped on,
    because the caller already chose the axis and the row would otherwise repeat
    it once per row.

    THIS ROW IS THE DECLARED ONE, and it is why the other two say the same
    thing. `GroupingFieldMarginRow` publishes this property through the schema,
    so the drift and breaking gates hold it; `get_usage_timeseries` above and the
    `/analytics/usage` breakdown return `list[dict]`, and #312 settled that they
    belong to the same vocabulary and moved them onto `GROUPED_VALUE_KEY`. This
    function keeps its literal spelling in the ANNOTATION below on purpose —
    there it is a Django alias that has to match a `values()` lookup, which is a
    different obligation from naming a wire key.
    """
    from apps.metering.usage.models import Posting
    qs = Posting.objects.filter(tenant_id=tenant_id)
    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        qs = qs.filter(effective_at__lt=utc_day_start(end_date))

    #: What one grouped row is made of. The aggregate writes the row's final
    #: names directly, so the only thing left to do per row is name the value it
    #: groups and subtract — no second vocabulary of aliases in between.
    _AGGREGATE = {
        **cost_total_annotations(SUPPLIER_COST, key="provider_cost_micros"),
        **cost_total_annotations(CUSTOMER_PRICE, key="billed_cost_micros"),
        "event_count": Count("id"),
    }

    def _row(value, group):
        """One row, from one group of the aggregate.

        BOTH pairs are resolved first, so the margin is taken against the two
        sums the row will actually state.

        ⚠ The billed half needed no coalesce here until #351, on the argument
        that a grouped aggregate over a NOT NULL column cannot answer `None`.
        The grouping half of that is still true and the NOT NULL half is not:
        a group can now consist entirely of unpriced postings.
        """
        cost = carry_cost_total(SUPPLIER_COST, dict(group),
                                key="provider_cost_micros")
        cost = carry_cost_total(CUSTOMER_PRICE, cost, key="billed_cost_micros")
        return {GROUPED_VALUE_KEY: value,
                "provider_cost_micros": cost["provider_cost_micros"],
                UNRESOLVED_EVENT_COUNT_KEY: cost[UNRESOLVED_EVENT_COUNT_KEY],
                "billed_cost_micros": cost["billed_cost_micros"],
                UNPRICED_EVENT_COUNT_KEY: cost[UNPRICED_EVENT_COUNT_KEY],
                "margin_micros": (cost["billed_cost_micros"]
                                  - cost["provider_cost_micros"]),
                "event_count": cost["event_count"]}

    if tag_key:
        # The keyed margin breakdown is slice 7's surface, left where #273
        # found it — only the column underneath moved, with the fold.
        grouped = (
            qs.filter(metadata__has_key=tag_key)
            .annotate(grouping_field_value=KeyTextTransform(tag_key, "metadata"))
            .values("grouping_field_value")
            .annotate(**_AGGREGATE)
            .order_by()
        )
        rows = [_row(g["grouping_field_value"], g) for g in grouped]
        return sorted(rows, key=lambda r: -r["margin_micros"])

    valid = ("provider", "event_type", "task_type", "subtask_type", *SLOTS)
    if group_by not in valid:
        raise ValueError(f"group_by must be one of {valid}")
    grouped = (qs.exclude(**{group_by: ""}).values(group_by)
               .annotate(**_AGGREGATE).order_by())
    rows = [_row(g[group_by], g) for g in grouped]
    return sorted(rows, key=lambda r: -r["margin_micros"])


def get_usage_event_effective_at(usage_event_id) -> datetime | None:
    """Get a usage event's effective_at timestamp. Returns datetime or None.

    Tolerates malformed (non-UUID) ids by returning None — the UUID is
    validated BEFORE the DB query so a legacy id (e.g. "evt-1" in old
    fixtures) can never raise DataError inside a caller's atomic block.
    """
    from apps.metering.usage.models import Posting

    try:
        uuid.UUID(str(usage_event_id))
    except (ValueError, TypeError):
        return None
    return Posting.objects.filter(id=usage_event_id).values_list(
        "effective_at", flat=True
    ).first()


def get_customer_ids_with_usage(tenant_id, period_start: date, period_end: date) -> list:
    """Distinct customer ids with ANY usage in [period_start, period_end).

    Existence-based: deliberately does NOT filter on billed_cost_micros
    (zero-billed usage still counts — spend-pool reconcile and postpaid close
    both want every customer that emitted events). tenant_id may be a single
    tenant id or a list/tuple/set of tenant ids (one query either way).
    """
    from apps.metering.usage.models import Posting

    tenant_ids = tenant_id if isinstance(tenant_id, (list, tuple, set)) else [tenant_id]
    return list(Posting.objects.filter(
        tenant_id__in=list(tenant_ids),
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    ).values_list("customer_id", flat=True).distinct())


def get_billed_totals_by_customer(tenant_id, customer_ids, period_start: date,
                                  period_end: date) -> dict:
    """Sum(billed_cost_micros) per customer over [period_start, period_end).

    Returns {customer_id: {billed_cost_micros, unpriced_event_count}}; a
    customer with no events in the window is absent (a customer whose events all
    bill 0 IS present, with 0 and a count of 0). SQL GROUP BY pushdown — the
    trailing .order_by() clears the model's default ordering so it cannot poison
    the GROUP BY.

    ⚠ THE VALUE WAS A BARE `int` WITH AN `or 0` UNTIL #351. This builds postpaid
    INVOICE LINES, so a floor reported as a figure is money not charged, and
    silently: a seat whose every posting is unpriced billed exactly like a seat
    that emitted nothing. The count travels so the caller can see the
    difference. **Whether a period holding unresolved prices may be invoiced at
    all is a policy question this ticket does not decide** — #329 answered the
    equivalent one for supplier cost by refusing the close, and the number that
    question needs is now present rather than absent.
    """
    from apps.metering.usage.models import Posting

    rows = (Posting.objects.filter(
        tenant_id=tenant_id, customer_id__in=list(customer_ids),
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    ).values("customer_id").annotate(
        **cost_total_annotations(CUSTOMER_PRICE, key="total")).order_by())
    return {r["customer_id"]:
            {"billed_cost_micros": carry_cost_total(
                CUSTOMER_PRICE, dict(r), key="total")["total"],
             UNPRICED_EVENT_COUNT_KEY: r[UNPRICED_EVENT_COUNT_KEY]}
            for r in rows}


def get_customer_billed_breakdown(tenant_id, customer_id, period_start: date,
                                  period_end: date, group_by: str) -> list[tuple]:
    """Billed totals for ONE customer grouped by "tag:<key>" or the first slot.

    Returns UNSORTED, aggregated [(label, billed_micros, unpriced_event_count),
    ...] triples (the caller owns presentation order). The third element is
    #351's, and it is on the tuple for the reason `get_billed_totals_by_customer`
    above gives at length: these are invoice lines, so a line that is a floor and
    says nothing is money not charged. Postpaid invoice-line label semantics:
    a missing key, an absent bag, a JSON-null or EMPTY-STRING value, and
    an empty slot value ALL collapse into "(other)" — unlike the analytics
    contract (get_usage_timeseries/get_dimensional_margin) where "" stays a
    grouped value of its own. SQL GROUP BY pushdown; NULL and "" groups are
    merged into "(other)" post-query.

    ``group_by`` IS ONLY READ FOR ITS "tag:" PREFIX. Anything else means the
    first slot, whatever the stored configuration spells — which is why #276
    renaming that column changed no stored value and needed no rewrite of
    ``PostpaidUsageConfig``. A tenant configured against the old spelling still
    gets the first slot, exactly as before.
    """
    from apps.metering.usage.models import Posting

    qs = Posting.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    )
    if group_by.startswith("tag:"):
        # The key-driven invoice line labels are slice 7's surface, left where
        # #273 found them — only the column underneath moved, with the fold.
        rows = (qs.annotate(label=KeyTextTransform(group_by[4:], "metadata"))
                .values("label")
                .annotate(**cost_total_annotations(CUSTOMER_PRICE, key="total"))
                .order_by())
        raw_key = "label"
    else:  # the first slot
        rows = (qs.values("grouping_field_1")
                .annotate(**cost_total_annotations(CUSTOMER_PRICE, key="total"))
                .order_by())
        raw_key = "grouping_field_1"
    merged: dict = {}
    counts: dict = {}
    for r in rows:
        label = r[raw_key] or "(other)"  # NULL and "" both collapse, then merge
        row = carry_cost_total(CUSTOMER_PRICE, dict(r), key="total")
        merged[label] = merged.get(label, 0) + row["total"]
        counts[label] = counts.get(label, 0) + row[UNPRICED_EVENT_COUNT_KEY]
    return [(label, billed, counts[label]) for label, billed in merged.items()]


def list_backfill_dirty_periods(created_before: datetime | None = None) -> list[dict]:
    """Pending backfill markers (plain dicts, oldest first).

    Each: {"id", "tenant_id", "customer_id", "period_start" (date)}. Written by
    record_usage when an event backfills into a PRIOR calendar month; consumed
    by subscriptions' resnapshot_dirty_periods, which acks each marker via
    clear_backfill_dirty_period() AFTER its snapshot work succeeds.

    created_before: only markers created strictly before this aware datetime.
    The consumer passes now − its settle horizon so a marker is never acked
    while the backfill's accumulator write (outbox-dispatched, hours of retry
    backoff) may still be in flight — acking against a stale accumulator would
    freeze the prior-month snapshot wrong forever.
    """
    from apps.metering.usage.models import BackfillDirtyPeriod

    qs = BackfillDirtyPeriod.objects.order_by("created_at")
    if created_before is not None:
        qs = qs.filter(created_at__lt=created_before)
    return [
        {"id": r["id"], "tenant_id": r["tenant_id"],
         "customer_id": r["customer_id"], "period_start": r["period_start"]}
        for r in qs.values("id", "tenant_id", "customer_id", "period_start")
    ]


def clear_backfill_dirty_period(marker_id) -> None:
    """Ack (delete) one backfill marker by id. Idempotent.

    The deliberate WRITE half of the marker contract: the consumer deletes the
    marker only after its re-snapshot succeeded, so a crash retries it.
    """
    from apps.metering.usage.models import BackfillDirtyPeriod

    BackfillDirtyPeriod.objects.filter(id=marker_id).delete()


def iter_billable_usage_events(tenant_id, since: datetime, before: datetime,
                               basis: str = "effective") -> Iterator[dict]:
    """Iterate billable events (billed_cost_micros > 0) in [since, before).

    since/before are aware datetimes (NOT dates — no day-snapping here).
    basis="effective" windows on effective_at; basis="created" windows on
    created_at, so a consumer (e.g. drawdown repair) can flip its scan basis
    with a one-word change. Yields plain dicts:
    {"id", "billed_cost_micros", "customer_id", "billing_owner_id"}.
    Server-side cursor via .iterator() — safe for large windows.

    ⚠ `billed_cost_micros__gt=0` NOW EXCLUDES AN UNPRICED POSTING TOO, and that
    is correct rather than incidental (#351). SQL's `> 0` is unknown for `NULL`,
    so a posting whose price UBB could not resolve is not yielded — and there is
    nothing to draw down for it, because there is no amount. What a caller must
    NOT conclude is that the window held no such postings: this iterator answers
    "what can be drawn down", not "what happened", and the completeness question
    is answered by the totals above rather than by an absence here.
    """
    from apps.metering.usage.models import Posting

    if basis not in ("effective", "created"):
        raise ValueError("basis must be 'effective' or 'created'")
    field = "created_at" if basis == "created" else "effective_at"
    return Posting.objects.filter(
        tenant_id=tenant_id, billed_cost_micros__gt=0,
        **{f"{field}__gte": since, f"{field}__lt": before},
    ).values("id", "billed_cost_micros", "customer_id", "billing_owner_id").iterator()


# --- What went unresolved, what recovering it is worth, and what waiving cost -
#
# The three read surfaces a Resolution Run projects onto (#364, spec §10
# rulings 11 and 12c; user stories 34, 40 and 42). None of them writes anything
# and none of them moves money: the customer adjustment is the only one of the
# four recovery mechanisms that does, two documents forbid it being automatic,
# and Stripe owns the billing engine UBB never reimplements. What these produce
# is a figure and the receipts behind it; the tenant acts through the money path
# UBB already has.
#
# ⚠ ALL THREE FILTER THROUGH THE RUN'S OWN AXES (`resolution_run.narrowed`)
# rather than through a copy of them here. A queue that could be narrowed
# differently from the run aimed at it would be a working list of a different
# set of postings, and the divergence would be invisible — both would answer
# 200 with plausible rows.
#
# ⚠ AND EACH ONE STATES ITS BASIS IN THE RESPONSE, not only in this file. A
# money figure whose basis a reader has to infer is one they will infer wrongly,
# and the waived figure is the sharpest case: a number a tenant reads as revenue
# lost, which it cannot be.

#: WHAT THE QUEUE'S MONEY TOTAL IS, IN THE RESPONSE'S OWN WORDS.
UNRESOLVED_QUEUE_BASIS = (
    "Everything UBB could not resolve: a supplier cost it never learned, a "
    "customer price no rule and no markup rung gave, or both. Each row carries "
    "the status that put it here and, for a supplier cost, the recorded reason "
    "the cost is missing. The total beside the list is what UBB has already "
    "paid the supplier for these calls — money out with no settled price "
    "against it — over the whole filter rather than over one page. Rows whose "
    "supplier cost is itself unresolved are not in that total and are counted "
    "beside it; rows whose Event Type declares no supplier cost are not in it "
    "and are not counted, because nothing about those is missing."
)

#: WHERE THE RECEIPTS BEHIND A PROJECTED FIGURE ARE, NAMED ONCE.
#:
#: ⚠ A PATH QUOTED IN PROSE IS A CROSS-REFERENCE NOTHING TYPE-CHECKS, and this
#: one is published verbatim into the contract and the generated SDK — so a
#: reader following it would be sent nowhere by a route that moved.
#:
#: ⚠ **THE CONSTANT ALONE DOES NOT MAKE THE COPIES AGREE, AND A COMMENT SAYING
#: IT DOES WOULD BE THE DEFECT IT WARNS ABOUT.** A docstring cannot interpolate
#: one, so the route's and the schema's each hand-type this path; only the
#: response's `basis` is built from it. What holds all three together is a
#: test — `api/v1/tests/test_the_three_surfaces_a_recovery_projects_onto.py`
#: checks this value against the LIVE API and then requires every published
#: docstring that names a receipt path to name exactly this one.
RECEIPTS_ARE_AT = "/metering/usage/{event_id}"

#: WHAT THE PROJECTION IS, AND — LOUDLY — WHAT IT IS NOT.
PROJECTED_ADJUSTMENT_BASIS = (
    "What completing this filter would be worth, per customer: the customer "
    "prices a Resolution Run would settle, summed over the postings this pass "
    "examined. It is a projection and not an instruction — no invoice, credit "
    "note, charge or refund follows from reading it, and UBB will not bill "
    "your customer for it. Each price is re-resolved at its own posting's "
    "effective instant, so nothing here is repriced against today's rules. "
    "The supplier-cost half of a recovery is deliberately not in the figure: "
    "learning what a call cost is not money you can go back to a customer "
    "for. Two things make these figures a floor and both are counted: "
    "`unpriced_event_count`, per customer, is how many examined postings "
    "still resolve to no price; `postings_not_examined` is how many the "
    "filter matched beyond what one pass takes up — narrow the date range to "
    "reach those. `usage_event_ids` names the postings that produced each "
    f"total; each one's Pricing Receipt is at GET {RECEIPTS_ARE_AT}."
)

#: WHAT THE WAIVED FIGURE IS TAKEN OVER, AND WHY IT CANNOT BE THE PRICE.
#:
#: ⚠ **THE BASIS HAD TO BE DECIDED HERE AND IT IS NOT THE OBVIOUS ONE.** A
#: waived posting carries a `NULL` price by construction — a charge is waived
#: exactly where the margin rule could not compute — so there is no set of
#: prices to add up, and a figure presented as forgone revenue would be a
#: number nobody ever stated. What IS a real loss, and is denominated, is the
#: supplier cost UBB paid on those calls: money that left the tenant's account
#: with nothing charged against it.
WAIVED_LOSS_BASIS = (
    "What UBB paid suppliers for calls whose charge was waived — money out "
    "with nothing charged for it. It is NOT revenue forgone and cannot be: a "
    "waived charge never carried a price, because the margin rule had no "
    "supplier cost to take a margin over, which is why it was waived. Waived "
    "postings whose own supplier cost UBB has not resolved are not in the "
    "figure and are counted beside it, so the total is a floor. Waived "
    "postings are never candidates for a "
    "Resolution Run — a decision somebody made is not information UBB is "
    "missing — so this is reported, never repaired."
)


def _the_same_axes_a_run_accepts(selected_from, selected_to,
                                 selected_customer_id, selected_event_type):
    """The three axes, as a run's own selector.

    Built rather than re-implemented so that "filterable on the same axes a run
    accepts" is a fact about the code and not a claim in a docstring.
    """
    from apps.metering.pricing.services.resolution_run import RunSelector

    return RunSelector(selected_from=selected_from, selected_to=selected_to,
                       selected_customer=selected_customer_id,
                       selected_event_type=selected_event_type)


def _per_currency_supplier_cost(postings, count_key: str) -> list[dict]:
    """The supplier cost over `postings`, one row per currency, with its count.

    Two of the three surfaces total the same column over different sets — the
    queue over what UBB could not resolve, the waived report over what nobody
    was charged for — and the only thing that differs is what the row calls its
    population. Written once because two copies of one rollup is how two
    surfaces come to answer the same question differently.

    ⚠ **THE TRAILING `.order_by("currency")` IS LOAD-BEARING AND IT IS NOT
    DECORATION.** `candidates` orders on two columns this rollup does not group
    by, and Django folds a surviving ordering into the GROUP BY — so without it
    this answers ONE ROW PER POSTING, each "total" being a single row's own
    amount, with nothing raising. `order_by` REPLACES rather than appends,
    which is what makes one call both the ordering and the repair. Measured
    rather than reasoned about: dropping it turns
    `test_the_queues_total_counts_the_unresolved_and_not_the_absent` red at
    `3 != 1`, while an `.order_by()` reset in front of `.values()` — which
    looks like the guard — turns nothing red.

    Rows are per currency because adding two denominations produces a number in
    neither. The rollups above this section are silent on that; the silence is
    inherited and is not widened here.
    """
    rows = (postings.values("currency").annotate(
        **cost_total_annotations(SUPPLIER_COST, key="provider_cost_micros"),
        **{count_key: Count("id")}).order_by("currency"))
    return [carry_cost_total(SUPPLIER_COST, dict(row),
                             key="provider_cost_micros") for row in rows]


def _queue_row(posting) -> dict:
    """One posting in the queue, as plain data.

    The statuses are the *why*: a supplier cost UBB has not learned says so
    with its recorded reason beside it, and a price it could not resolve says
    so with its own status. Neither amount is coerced — a price UBB does not
    have is `None` here, never a zero and never the word `unknown` in a money
    field, which is the whole defect the nullable columns exist to remove.
    """
    return {
        "usage_event_id": str(posting.id),
        "effective_at": posting.effective_at.isoformat(),
        "customer_id": str(posting.customer_id),
        "event_type": posting.event_type,
        "provider": posting.provider,
        "currency": posting.currency,
        "provider_cost_micros": posting.provider_cost_micros,
        "costing_status": posting.costing_status,
        "unresolved_reason": posting.unresolved_reason or None,
        "billed_cost_micros": posting.billed_cost_micros,
        "pricing_status": posting.pricing_status,
    }


def get_unresolved_queue(tenant_id, *, selected_from=None, selected_to=None,
                         selected_customer_id=None, selected_event_type="",
                         cursor=None, limit=50) -> dict:
    """The working list a Resolution Run is aimed at (user story 34).

    Exactly the run's candidate set — `resolution_run.candidates`, not a
    re-derived filter — so a tenant working through this list is looking at the
    postings a run over the same filter would take up, and the two cannot come
    to disagree about membership.

    Paged newest-first, which is the house list idiom; a run works its own set
    oldest-first so that a bounded run advances through a backlog. The two
    orders answer different questions and neither is the other's bug.

    The totals are over the WHOLE filter rather than over the page, per
    currency, each with the count of rows it could not include.
    """
    from apps.metering.pricing.services.resolution_run import candidates
    from core.pagination import page

    queued = candidates(tenant_id, _the_same_axes_a_run_accepts(
        selected_from, selected_to, selected_customer_id, selected_event_type))
    return {
        "basis": UNRESOLVED_QUEUE_BASIS,
        # THE ONE ENVELOPE (#115), not a hand-assembled copy of it: `page`
        # owns `data`/`next_cursor`/`has_more` and is in the kernel, so a
        # product may call it. Keyed on `effective_at`, which is the axis the
        # filter narrows on and the one a working list is read in.
        **page(queued, cursor, limit, serialize=_queue_row,
               time_field="effective_at"),
        "totals": _per_currency_supplier_cost(queued, "queued_event_count"),
    }


def get_projected_adjustment(tenant_id, *, selected_from=None, selected_to=None,
                             selected_customer_id=None,
                             selected_event_type="") -> dict:
    """What recovering this filter would be worth, per customer (user story 40).

    The arithmetic is the run's own, with the writing taken out — see
    `resolution_run.project`, which re-resolves each posting through the same
    function a run completes from. This adds the response's statement of what
    the figure is, which the surface owes a reader who would otherwise read a
    projection as a receivable.
    """
    from apps.metering.pricing.services.resolution_run import project

    return {"basis": PROJECTED_ADJUSTMENT_BASIS,
            **project(tenant_id, _the_same_axes_a_run_accepts(
                selected_from, selected_to, selected_customer_id,
                selected_event_type))}


def get_waived_loss(tenant_id, *, selected_from=None, selected_to=None,
                    selected_customer_id=None, selected_event_type="") -> dict:
    """What waiving has cost this tenant over the filter (user story 42).

    A misconfiguration that is losing a tenant money should be visible as
    money, and this is the money it is visible as: the supplier cost paid on
    calls nobody was ever charged for. `WAIVED_LOSS_BASIS` argues why it cannot
    be the price, and the response carries that sentence.

    Rows are per currency. There is no grand total across them, deliberately —
    adding two denominations produces a number in neither.
    """
    from apps.metering.pricing.services.resolution_run import narrowed
    from apps.metering.usage.models import Posting

    # ⚠ THE PAIR'S THIRD BRANCH IS UNREACHABLE HERE, AND SAYING SO IN CODE IS
    # WHY THE PUBLISHED BASIS DOES NOT MENTION IT. `core.cost_totals` skips a
    # `not_applicable` cost without counting it, because nothing about that one
    # is missing — but a charge is waived exactly where a margin had no basis,
    # i.e. where the cost is `unresolved`, and `not_applicable` is only ever
    # written when a posting is recorded. So no waived posting can carry one,
    # and a tenant-facing sentence describing that carve would be explaining a
    # case they can never meet. The rule still applies; it just has nothing to
    # apply to.
    waived = narrowed(
        Posting.objects.filter(tenant_id=tenant_id,
                               pricing_status=PRICING_STATUS_WAIVED),
        _the_same_axes_a_run_accepts(selected_from, selected_to,
                                     selected_customer_id, selected_event_type))
    return {
        "basis": WAIVED_LOSS_BASIS,
        "rows": _per_currency_supplier_cost(waived, "waived_event_count"),
    }


def stop_context_postings(tenant_id, *, customer_id=None, billing_owner_id=None,
                          since=None, until=None) -> list[dict]:
    """Every posting the stop-context tagging marked, as plain rows — the
    itemised events of Stops and breaches (#465, slice 6 §14).

    One query over the partial index's population (`stop_context` not null),
    ordered as the report itemises. Each row carries both amount/status pairs
    so a total built on it can add what is resolved and count what is not
    (#328, #351), the seat and the billing owner (a customer-wide episode is
    the owner's, and the posting is the seat's), and the stored context
    array exactly as written — the composition layer reads scope and ids off
    it, never a current spelling (the metering glossary's rule for a column
    that is immutable with its row).

    `charge_id` names the Charge a projected posting came from — the one
    posting under a fixed-price unit of work, keyed by the Charge's own
    idempotency key (ADR-0013, `charge_projection.py`) — so a pool episode
    can cite the Charge that crossed it and that Charge's posting rather than
    an arbitrary event (#153 §10.2). Null on a metered posting, which is a
    charge in its own right and names nothing further.

    ``customer_id`` narrows to one seat's postings and ``billing_owner_id``
    to every seat's that pins that owner — either alone, or both together as
    a union, so a customer filter reaches the events tagged into its
    owner's customer-wide episodes from every seat (review of #465). The
    window, where given, selects on ``effective_at``; the report passes
    none, because an episode's events are the episode's whatever window
    selected the episode.
    """
    from django.db.models import Q
    from apps.metering.pricing.models import Charge
    from apps.metering.usage.models import Posting
    from core.vocabulary import USAGE_EVENT_KIND_TASK_CHARGE

    qs = Posting.objects.filter(tenant_id=tenant_id, stop_context__isnull=False)
    scope = Q()
    if customer_id is not None:
        scope |= Q(customer_id=customer_id)
    if billing_owner_id is not None:
        scope |= Q(billing_owner_id=billing_owner_id)
    if scope:
        qs = qs.filter(scope)
    if since is not None:
        qs = qs.filter(effective_at__gte=since)
    if until is not None:
        qs = qs.filter(effective_at__lt=until)
    postings = list(qs.order_by("effective_at", "created_at").values(
        "id", "customer_id", "billing_owner_id", "effective_at",
        "billed_cost_micros", "pricing_status", "provider_cost_micros",
        "costing_status", "kind", "idempotency_key", "stop_context"))
    projected_keys = [p["idempotency_key"] for p in postings
                      if p["kind"] == USAGE_EVENT_KIND_TASK_CHARGE]
    charges = {}
    if projected_keys:
        charges = {key: str(pk) for pk, key in Charge.objects
                   .filter(tenant_id=tenant_id, idempotency_key__in=projected_keys)
                   .values_list("id", "idempotency_key")}
    return [{**_stopped_work_posting_row(
                 p, charges.get(p["idempotency_key"])
                 if p["kind"] == USAGE_EVENT_KIND_TASK_CHARGE else None),
             "stop_context": list(p["stop_context"] or [])}
            for p in postings]


def _stopped_work_posting_row(p, charge_id):
    """The plain row both spend-control reads answer a posting as — one
    shape, so a repair applied to one cannot be missing from the other."""
    return {
        "event_id": str(p["id"]),
        "customer_id": str(p["customer_id"]),
        "billing_owner_id": str(p["billing_owner_id"]) if p["billing_owner_id"] else None,
        "effective_at": p["effective_at"],
        "billed_cost_micros": p["billed_cost_micros"],
        "pricing_status": p["pricing_status"],
        "provider_cost_micros": p["provider_cost_micros"],
        "costing_status": p["costing_status"],
        "charge_id": str(charge_id) if charge_id else None,
    }


def charge_that_reached(tenant_id, customer_id, *, stop_threshold_micros,
                        at) -> dict | None:
    """The posting whose resolved customer price took this customer's known
    period charges at or over ``stop_threshold_micros`` — the Charge that
    reached a pool's boundary (#150 §7.2, #465 slice 6 §14), for an episode
    the recording route did not mark.

    A crossing the live lane detects marks its tipping posting in the
    stop-context (`arrived_after` false), and the composition layer reads
    that first. A crossing detected on the durable drawdown or by the hourly
    reconcile marks nothing — a delivered fixed-price unit's Charge reaches
    the pool through its projection and the drawdown, never the recording
    route — so this read replays what the drawdown counted: the customer's
    postings with a resolved price in the month ``at`` falls in, at either
    declared level (the customer's own postings and those pinning it as
    billing owner — one row for a seat, the whole business for an owner),
    in the order they were recorded, up to ``at``, and answers the first at
    which the running total reaches the line. ``None`` where the line is
    never reached by then — a pool row raised since, or a crossing the
    lanes signalled off a counter the durable basis does not reproduce.

    THE SCOPE IS EACH LEVEL'S OWN BASIS. A seat's pool is measured over the
    seat's postings (`get_customer_cost_totals`); a business's over every
    posting pinning it as billing owner (`get_billing_owner_billed_total`),
    its own included because its own postings pin itself. The union of the
    two filters is the seat's basis for a seat (no posting pins a seat as
    another's owner) and the owner's basis for a business, so one read
    serves both levels without being told which it is asked about.

    THE LINE IS THE ROW'S AS IT STANDS, AND THE CALLER SAYS SO. The crossing
    recorded no figure; a pool lowered since names an earlier posting than
    the one that crossed, and one raised since names none. The report
    publishes whether the crossing was marked or replayed, so a reader can
    weigh a replayed answer for exactly that.

    The same shape as one of `stop_context_postings`' rows, less the context.
    """
    from django.db.models import Q
    from apps.metering.pricing.models import Charge
    from apps.metering.usage.models import Posting
    from core.vocabulary import USAGE_EVENT_KIND_TASK_CHARGE

    start, end = month_bounds(at)
    running = 0
    for p in (Posting.objects
              .filter(tenant_id=tenant_id, created_at__lte=at,
                      effective_at__gte=utc_day_start(start),
                      effective_at__lt=utc_day_start(end),
                      billed_cost_micros__isnull=False)
              .filter(Q(customer_id=customer_id) | Q(billing_owner_id=customer_id))
              .order_by("created_at")
              .values("id", "customer_id", "billing_owner_id", "effective_at",
                      "billed_cost_micros", "pricing_status", "provider_cost_micros",
                      "costing_status", "kind", "idempotency_key")):
        running += p["billed_cost_micros"]
        if running >= stop_threshold_micros:
            charge_id = None
            if p["kind"] == USAGE_EVENT_KIND_TASK_CHARGE:
                charge_id = (Charge.objects
                             .filter(tenant_id=tenant_id, idempotency_key=p["idempotency_key"])
                             .values_list("id", flat=True).first())
            return _stopped_work_posting_row(p, charge_id)
    return None


# --- What a tenant may group by, and what each axis can honestly answer -----
#
# THE GROUPING CONTRACT (#498, slice 7 §6 and §7). Four bespoke per-surface
# grouping parameters each answered the same question their own way and three of
# them read free text; the registry retires all four to ONE request word whose
# values carry their own kind.
#
# EXACTLY TWO KINDS, AND THEIR DIFFERENCE STAYS VISIBLE TO THE CALLER. A direct
# grouping field is a COLUMN — a value materially attached to the posting or
# inherited from the work it belongs to. A declared semantic rollup is a JOIN —
# a controlled mapping from an identity the tenant already declared to a broader
# analytical heading. The two have materially different cardinality and query
# cost, so a flat list of axis names would hide that behind strings that look
# alike. The kind is therefore part of the request word (`field:` / `rollup:`)
# rather than metadata beside it, which is why `analytics_grouping_kind` is a
# closed set rather than a boolean.
#
# COMPUTED PER TENANT, NEVER A SHIPPED LIST. UBB ships no catalogue of
# suppliers, event types or prices and its registries start empty (map #137
# constraint 5), so an answer that did not vary by tenant would be UBB shipping
# one. The two rollup axes are UBB's and closed; the fields are the tenant's and
# open.
#
# ⚠ IT IS THE PROTECTION, NOT A CONVENIENCE FOR CLIENTS. Renaming a measure
# makes the honest reading *available*; it does not make the dishonest
# comparison impossible (#154 §14). What makes it impossible is refusing the
# combination — and a refusal can only be stated against a declared vocabulary,
# which is this one. :func:`grouping_refusal` is that statement.
#
# ⚠ NEITHER KIND EVER SELECTS A RATE OR A CUSTOMER-PRICING RULE. #145 §5 took
# that role away and #147 §2 took the event heading out of pricing by name, and
# this vocabulary must not readmit either through a reporting door. What makes
# it structural rather than a promise: a rule's selectors are `Rate.SELECTORS`,
# nothing here writes one, and neither rollup identity is a column on that
# table. `apps/metering/tests/test_the_grouping_contract.py` asserts it, and
# `apps/platform/tests/test_event_type_declaration_invariants.py` has held the
# quantity heading to it since the record was built.

#: The character between an axis's kind and its name in the one request word.
#:
#: ⚠ **A DECLARED KEY MAY CONTAIN IT, AND THE WORD IS STILL UNAMBIGUOUS.** UBB
#: never invented a charset for a tenant's own key — the registry says so at the
#: column, because a charset UBB invented would be UBB second-guessing a
#: tenant's catalogue — so the split has to be at the FIRST separator and the
#: rest is the name, however many more it holds. Requiring the key to avoid this
#: character would have been a rule nothing enforces, stated where a reader
#: would believe it.
GROUPING_KIND_SEPARATOR = ":"

#: The grain an axis's value is constant at. Three of the four are the Grouping
#: Field registry's own scopes, read off it rather than restated; the fourth is
#: the one no declared field can ever be scoped to, because it is a rollup's.
#:
#: UBB owns this set and the registry declares no concept for it — legal, and
#: legal for the reason `event_types.VALUE_TYPE_CHOICES` gives for its own pair:
#: the contract does not RESTATE the set. The field publishes as a plain string
#: whose meaning the schema states in prose (`api/v1/schemas.py::
#: SOURCE_GRAIN_MEANING`), so this is still the one place the values live, and
#: §7's raw-HTTP reader is told what they mean without a generated enum. A
#: concept would buy the published `enum` and the console wording, and neither
#: is owed by a ticket that names two concepts and no more. A later slice
#: wanting either should register it; the cost of doing so has not risen.
GRAIN_MEASUREMENT = "measurement"
GROUPING_GRAINS = tuple(scope for scope, _ in SCOPE_CHOICES) + (GRAIN_MEASUREMENT,)
GRAIN_EVENT, GRAIN_TASK, GRAIN_SUBTASK = "event", "task", "subtask"

#: The three above are the registry's own scope values, and a declared field's
#: grain is passed straight through from its scope — so they are spelled here
#: only for the axes that have no declaration to read one from. The agreement is
#: checked rather than assumed: a scope renamed in the kernel would otherwise
#: leave this module answering a grain no declared field can ever match.
assert {GRAIN_EVENT, GRAIN_TASK, GRAIN_SUBTASK} < set(GROUPING_GRAINS), (
    "the always-present axes must be scoped in the registry's own words")

#: The surfaces that take a grouping axis. Two, and the second is why this read
#: is not "the analytics capabilities endpoint": a tenant chooses how its
#: invoice lines are grouped from this same vocabulary rather than through a
#: fourth bespoke door (§11). Held to the same reasoning as the grains above,
#: and described on the wire by `api/v1/schemas.py::SUPPORTED_SURFACES_MEANING`.
#:
#: It declares CAPABILITY rather than availability, which is §5.4's own rule and
#: is why the invoice surface is named before the ticket that consumes it: an
#: axis is listed where it may honestly be used, and a surface reads this to
#: find out, rather than each surface keeping a list of its own.
SURFACE_ANALYTICS = "analytics"
SURFACE_INVOICE_LINES = "invoice_lines"
GROUPING_SURFACES = (SURFACE_ANALYTICS, SURFACE_INVOICE_LINES)

#: The axes every posting carries whatever the tenant has declared, each with
#: the grain its value is constant at, in the order a reader meets them.
#:
#: THEY ARE NOT A CATALOGUE AND THAT IS WHY THEY ARE HERE. A catalogue is a list
#: of VALUES UBB would be shipping on a tenant's behalf — which suppliers exist,
#: which event types exist. These are COLUMNS every posting has, exactly the
#: four ADR-0005 calls the reserved keys, plus the customer the posting is
#: attributed to. Leaving them out would make a whole family of the collapse
#: unexpressible: the per-customer margin list becomes grouping by the customer
#: field, and a vocabulary that cannot name it cannot validate it.
#:
#: ⚠ THE CUSTOMER IS A GROUPING AXIS AND NOT A RATE SELECTOR, and that is why
#: the registry's reserved words and `Rate.SELECTORS` are two lists rather than
#: one. A rule pins a customer through `Rate.customer`, its own relation, never
#: through a selector. §6 names the customer first among the direct grouping
#: fields, so it is an axis here — and the registry reserves the word, which is
#: what stops a tenant declaring a field called `customer` and leaving one
#: request word naming two axes at two grains.
ALWAYS_PRESENT_AXES = (
    ("customer", GRAIN_EVENT),
    ("provider", GRAIN_EVENT),
    ("event_type", GRAIN_EVENT),
    ("task_type", GRAIN_TASK),
    ("subtask_type", GRAIN_SUBTASK),
)

#: The registry owns WHICH words are always present; this module owns the grain
#: each one resolves at, which the registry does not record. So the pair is
#: checked rather than copied, in both directions: a sixth reserved word with no
#: grain here would be silently ungroupable on a contract whose whole claim is
#: that it says what may be grouped by, and an axis here that the registry does
#: NOT reserve is a word a tenant could declare underneath.
assert {name for name, _ in ALWAYS_PRESENT_AXES} == set(RESERVED_KEYS), (
    "every reserved word needs a grain here, and every axis here must be a "
    "word the registry reserves")

#: THE MEASUREMENT-CONCEPT ROLLUP SHIPS NARROWED, AND THAT IS THE HONEST ANSWER
#: (§7). #153 §5.4's own sketch wanted it to support component-level cost and
#: §19's first residue said that had to be resolved before the axis could ship.
#: Slice 2's split did not resolve it: the measurement child record carries
#: quantities, a parent, a recorded moment and a retention column — and no cost
#: lines. The per-measurement components live inside the receipt's JSON, which
#: is exactly what does not scale.
#:
#: So the axis ships supporting measurement quantities with the supplier cost
#: declared UNSUPPORTED on it, and the reason stated. §5.4's whole purpose is
#: that this contract declares CAPABILITY rather than availability, so declaring
#: an unsupported measure is the honest answer the mechanism was built to
#: express — strictly better than an axis that ships and is quietly unusable at
#: volume. The component-grain row is #194's, by name.
#:
#: ⚠ AND THE RESTRICTION TRAVELS WITH THE AXIS. It groups measurement RECORDS,
#: not events, so a cost at this grain could only be produced by spreading one
#: event's whole cost across every measurement that event contains. That is not
#: a narrower answer, it is a wrong one — a tenant reading it would see the same
#: money once per quantity — and refusing is what stops it.
MEASUREMENT_ROLLUP_UNSUPPORTED = (
    (ANALYTICS_MEASURE_SUPPLIER_COGS,
     "UBB records supplier cost per posting and not per measurement, so a cost "
     "at this grain could only be produced by repeating one event's whole cost "
     "against every quantity that event was measured by."),
)

#: The rollup axes, each with the grain it resolves at and the measures it
#: cannot answer. UBB owns both and the set is closed, which is the half of this
#: contract that is NOT computed per tenant: the tenant assigns members to them;
#: the axes themselves are UBB's.
#:
#: THIS TUPLE FIXES THE ORDER THE READ ANSWERS IN, and it is the only thing that
#: does — the guard below holds the SET against the registry, which a reordering
#: of either would not move. Saying the order "is the registry's" would be a
#: claim nothing checks.
ROLLUP_AXES = (
    (ANALYTICS_ROLLUP_EVENT_CATEGORY, GRAIN_EVENT, ()),
    (ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT, GRAIN_MEASUREMENT,
     MEASUREMENT_ROLLUP_UNSUPPORTED),
)

#: A rollup that ships without a line here would be an axis this module answers
#: for and never offers — invisible, because every function below iterates the
#: tuple rather than the registry. The guard is the one place the two are
#: compared.
assert {axis for axis, _, _ in ROLLUP_AXES} == ANALYTICS_ROLLUP_VALUES, (
    "every declared rollup needs a line in ROLLUP_AXES")

#: Same guard, for the kinds: a third kind would need a prefix, a grain rule and
#: a place in the answer, and the failure to give it one should be loud rather
#: than a word the read silently never offers.
assert {ANALYTICS_GROUPING_KIND_FIELD,
        ANALYTICS_GROUPING_KIND_ROLLUP} == ANALYTICS_GROUPING_KIND_VALUES, (
    "every declared grouping kind needs a prefix and a place in the answer")


def grouping_axis(kind, name) -> str:
    """The one request word for an axis: its kind, then the axis's own name.

    Spelled once, here, so the request word and the discovery read cannot
    disagree about what a caller sends.
    """
    return f"{kind}{GROUPING_KIND_SEPARATOR}{name}"


def parse_grouping_axis(word) -> tuple[str, str] | None:
    """``(kind, name)`` for one request word, or ``None`` where it names none.

    ``None`` covers both halves of the same mistake — a word with no kind at all
    (the bare axis name every parameter this vocabulary replaces took) and a
    word whose kind is not one the registry declares. Both are refused by the
    same sentence, because both are a caller guessing at a vocabulary instead of
    reading it.
    """
    kind, separator, name = str(word).partition(GROUPING_KIND_SEPARATOR)
    if not separator or not name or kind not in ANALYTICS_GROUPING_KIND_VALUES:
        return None
    return kind, name


def grouping_options(tenant_id) -> list[dict]:
    """This tenant's grouping vocabulary — one row per axis it may group by.

    Each row carries what a caller needs to build a request and to know what the
    answer will mean:

    ``key``
        the one request word, with its kind attached.
    ``kind``
        ``field`` or ``rollup`` — a column or a join, stated rather than
        inferred from the prefix, so nothing has to split a string to learn it.
    ``rollup``
        which rollup axis, where the kind is one; ``None`` otherwise.
    ``label``
        the TENANT's own word for the axis, and ``""`` where the wording is
        UBB's. That asymmetry is ADR-0008 §4 rather than an omission: the
        registry owns identity and the localisation layer owns expression, so a
        backend deriving "Event Category" from `event_category` would be
        manufacturing user-facing terminology out of an implementation token —
        the defect that section names by example. A tenant's own key is not
        UBB's English and has nowhere else to come from, which is why it is
        here and UBB's wording is not.
    ``source_grain``
        the grain the axis's value is constant at.
    ``supported_surfaces``
        which surfaces take the axis.
    ``max_cardinality``
        the cap the tenant declared on the axis, and ``None`` where UBB owns the
        axis and no cap was declared. §7 makes cardinality one of the three
        things a request is validated against, and the invoice-line surface
        warns at configuration time from this same read.
    ``unsupported_measures``
        the measures this axis REFUSES, each with its reason. An axis that
        refuses none carries an empty list, and every measure not named here is
        accepted and answers with its own state.

    ⚠ **THE COMPLEMENT — an enumerated `supported_measures` — IS NOT HERE, AND
    THE HALF THAT IS MISSING IS NAMED RATHER THAN QUIETLY DROPPED.** Listing the
    supported measures means this module naming all four by reference, which
    would make it the measure concept's serving consumer and pay a debt that
    belongs to the query that COMPUTES the measures rather than to the read that
    lists them — the vacuous form of the payment, and the one thing both tickets
    forbid. Worse, the contract cannot advertise a measure value while its
    backend consumer holds none, so publishing the set here would publish it
    ahead of anything that can serve it. Declaring capability BY EXCEPTION is
    complete for the server, which is where refusal happens; the set the
    exceptions are exceptions to arrives with the one economic query.

    ⚠ **RETIRED FIELDS STAY IN THE ANSWER.** Retirement blocks new VALUES, never
    reads (ADR-0005 D8): a posting recorded before its field was retired must
    still be groupable, so an axis that can still answer is still offered.

    Ordered: the always-present axes, then the tenant's declared fields in slot
    order, then the rollups in registry order. Slot order is not alphabetical
    order and the registry's own read is what knows the difference.
    """
    from apps.platform.grouping_fields.queries import declared_dimensions

    options = [
        _option(grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, name),
                kind=ANALYTICS_GROUPING_KIND_FIELD, grain=grain)
        for name, grain in ALWAYS_PRESENT_AXES
    ]
    options += [
        _option(grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, field["key"]),
                kind=ANALYTICS_GROUPING_KIND_FIELD, grain=field["scope"],
                label=field["key"], max_cardinality=field["max_cardinality"])
        for field in declared_dimensions(tenant_id)
    ]
    options += [
        _option(grouping_axis(ANALYTICS_GROUPING_KIND_ROLLUP, axis),
                kind=ANALYTICS_GROUPING_KIND_ROLLUP, grain=grain, rollup=axis,
                unsupported=unsupported)
        for axis, grain, unsupported in ROLLUP_AXES
    ]
    return options


def _option(key, *, kind, grain, rollup=None, label="", max_cardinality=None,
            unsupported=()):
    """One row of :func:`grouping_options`, built in one place.

    The surface list is derived rather than passed: an axis resolving at the
    measurement grain may appear only where component-level quantities exist,
    and an invoice line is money — so the rule is the grain's and not each
    caller's to remember.
    """
    surfaces = [surface for surface in GROUPING_SURFACES
                if surface != SURFACE_INVOICE_LINES
                or grain != GRAIN_MEASUREMENT]
    return {"key": key, "kind": kind, "rollup": rollup, "label": label,
            "source_grain": grain, "supported_surfaces": surfaces,
            "max_cardinality": max_cardinality,
            "unsupported_measures": [{"measure": measure, "reason": reason}
                                     for measure, reason in unsupported]}


def grouping_refusal(tenant_id, *, axes, measures=(),
                     surface=SURFACE_ANALYTICS) -> str | None:
    """Why this combination may not be answered, or ``None`` where it may.

    A sentence rather than a raised error, because a read contract returns plain
    data and the caller decides what an unanswerable request looks like on its
    own surface.

    ⚠ **IT NAMES THE AXIS AND THE MEASURE, NOT JUST THAT SOMETHING WAS WRONG.**
    A caveat a client may ignore is a caveat that will be ignored, and that is
    how three free-text hatches survived ADR-0005 in the first place; a refusal
    a client cannot act on is the same failure one step later.

    ⚠ **IT REFUSES ON TWO OF §7's THREE GROUNDS, AND THE THIRD IS NAMED RATHER
    THAN SILENTLY ABSENT.** §7 validates a request against supported measures,
    supported surfaces AND cardinality. The first two are decided here, from
    facts this contract holds. The third is not: a cardinality refusal has to
    compare the tenant's declared cap against how many rows a request would
    ACTUALLY produce, which is a count over their postings — something only the
    query that runs them can know, and something the invoice-line surface asks
    at configuration time rather than at request time. So the cap travels on the
    row (`max_cardinality`) and the two surfaces that can count decide with it.
    Refusing here on the cap alone would mean refusing a request that would have
    returned three rows because the tenant once said a hundred was their limit.
    """
    available = {option["key"]: option for option in grouping_options(tenant_id)}
    for word in axes:
        if parse_grouping_axis(word) is None:
            return (f"{word!r} names no grouping kind — every axis is sent as "
                    f"{ANALYTICS_GROUPING_KIND_FIELD}"
                    f"{GROUPING_KIND_SEPARATOR}<name> or "
                    f"{ANALYTICS_GROUPING_KIND_ROLLUP}"
                    f"{GROUPING_KIND_SEPARATOR}<name>")
        option = available.get(word)
        if option is None:
            return f"{word!r} is not a grouping axis this tenant has declared"
        if surface not in option["supported_surfaces"]:
            return f"{word!r} is not available on {surface!r}"
        for refused in option["unsupported_measures"]:
            if refused["measure"] in measures:
                return (f"{refused['measure']!r} is not available grouped by "
                        f"{word!r}: {refused['reason']}")
    return None


def rollup_membership(tenant_id, rollup) -> dict:
    """``{identity: heading}`` for one declared semantic rollup.

    The JOIN half of the contract, as plain data: which of the tenant's own
    declared identities currently sit under which of their own headings. An
    identity with no heading is absent rather than present under a sentinel —
    "nobody has filed this" and "this is filed under nothing" are the same fact
    here, and the axis is opt-in on both sides.

    ⚠ **IT IS READ LIVE, AND THAT IS WHAT RECLASSIFYING HISTORY MEANS.** Moving
    an identity to another heading changes what every past row rolls up to, and
    that is safe precisely because a rollup touches no money: it alters no
    original event, no cost, no Charge, no receipt and no historical monetary
    amount. Making that true is this module's job and the console states the
    behaviour at the point of change.

    Keyed by the tenant's own spelling on both sides, because those are the
    words the tenant reads on the surfaces that carry the answer. The event
    heading keys on an Event Type's key; the measurement heading keys on the
    PAIR of Event Type key and quantity code, because a declaration is
    Event-Type-local and two Event Types declaring one name may be filed under
    two different headings — the kernel read argues that in full.

    ⚠ **THE QUERY IS THE KERNEL'S AND NOT THIS MODULE'S, AND THAT IS ENFORCED
    RATHER THAN PREFERRED.** `apps/platform/tests/test_event_type_satellite
    _invariants.py` refuses a module where a cost, a price or a spend ceiling is
    decided to NAME a catalogue class — money code does not hold catalogue rows
    — and this file is metering's read contract, which is squarely one. So the
    records are reached through `event_types.rollups`, which answers in plain
    data beside the declaration, exactly as `costing.py` answers what a
    declaration says about cost. The reporter asks; the kernel answers.
    """
    from apps.platform.event_types import rollups

    readers = {
        ANALYTICS_ROLLUP_EVENT_CATEGORY: rollups.event_types_by_category,
        ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT: rollups.measurements_by_concept,
    }
    # A declared axis with no reader must not fall out of the door below, which
    # would tell a caller its own registry does not declare the axis it just
    # read off the discovery contract — a true-sounding message about the wrong
    # thing. The registry's set is the authority in both directions.
    assert set(readers) == ANALYTICS_ROLLUP_VALUES, (
        "every declared rollup needs a reader in the kernel")
    if rollup not in readers:
        raise ValueError(f"{rollup!r} is not a declared rollup axis")
    return readers[rollup](tenant_id)
