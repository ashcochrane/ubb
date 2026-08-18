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
from core.time_windows import utc_day_start, utc_next_day_start
from apps.platform.grouping_fields.models import SLOT_CHOICES

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
    — it does not overcharge anybody, it lets a limit be crossed later than it
    should be. That is a spend-control input rather than a report, and the
    ceilings that race it are slice 6's; what this slice owes them is a number
    that says when it is incomplete instead of one that quietly is.
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
    (zero-billed usage still counts — budget reconcile and postpaid close
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
