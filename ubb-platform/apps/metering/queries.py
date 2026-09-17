"""Metering Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(billing, subscriptions, referrals) to read metering data.
Functions return plain dicts, never ORM instances.

⚠ ONE DECLARED EXCEPTION, AND IT IS NOT A READ: the `BackfillDirtyPeriod`
marker contract — `mark_backfill_dirty_period*` and
`clear_backfill_dirty_period` — writes rows. ADR-001 §3 carries the reason: the
marker table is metering's and the things that make a month stale are not all
metering's, so the alternative is another product reaching for a metering model.
The whole contract stays in one module, both halves together. Everything else
here returns plain data and writes nothing.

If metering becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/tenant_billing/services.py → get_period_totals()
- apps/referrals/rewards/reconciliation.py → get_customer_usage_for_period()
- apps/billing/gating/tasks.py → get_customer_ids_with_usage()
- apps/billing/invoicing/tasks.py → get_customer_ids_with_usage()
- apps/billing/invoicing/services/postpaid_service.py → get_customer_cost_totals(),
  get_billed_totals_by_customer(), get_customer_billed_breakdown()
- api/v1/billing_endpoints.py → grouping_refusal(), invoice_line_cardinality_warning()
  — the postpaid config's write surface, which validates the invoice-line
  grouping axis against this tenant's own discovery contract and warns on its
  cardinality at the moment it is chosen (#503). A BILLING surface reached
  through this read contract, which is the only channel ADR-001 allows
- apps/billing/wallets/tasks.py → iter_billable_usage_events()
- apps/subscriptions/handlers.py → get_usage_event_effective_at()
- apps/subscriptions/tasks.py → list_backfill_dirty_periods(),
  clear_backfill_dirty_period() (the ack half of the marker contract),
  get_customer_cost_totals() (the repair a marker's consumer runs first, #502)
- apps/subscriptions/api/margin_endpoints.py → mark_backfill_dirty_period()
  (the write half: a figure a tenant supplies about a month that has closed
  makes that month's cached economics stale, exactly as a late supplier cost
  does, #502)
- api/v1/metering_endpoints.py → get_unresolved_queue(),
  get_projected_adjustment(), get_waived_loss() (the three recovery reads, #364),
  and economics() with grouping_options() beside it — the one economic query
  (#499) and the discovery read that says what may be asked of it (#498), which
  between them replaced five separate definitions of revenue and margin (#501)
- api/v1/spend_control_endpoints.py → stop_context_postings() (the itemised
  events of Stops and breaches, #465), charge_that_reached() (the Charge a
  pool episode cites where the crossing was detected off the recording route)
"""
import uuid
from datetime import date, datetime
from typing import Iterator, NamedTuple, TypedDict

from django.db.models import Count
from django.db.models.functions import TruncDay, TruncHour, TruncMonth
from django.utils import timezone

from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY, carry_cost_total,
    cost_total_annotations,
)
from core.retention import (
    AVAILABLE_FROM_FIELD, ECONOMIC_HORIZON_FIELD, MEASUREMENT_HORIZON_FIELD,
    retention_horizons)
from core.time_windows import month_bounds, utc_day_start, utc_next_day_start
from core.vocabulary import (
    ANALYTICS_GROUPING_KIND_FIELD,
    ANALYTICS_GROUPING_KIND_ROLLUP,
    ANALYTICS_GROUPING_KIND_VALUES,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE,
    ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_RECORDED_EVENTS,
    ANALYTICS_MEASURE_SUPPLIER_COGS,
    ANALYTICS_MEASURE_VALUES,
    ANALYTICS_ROLLUP_EVENT_CATEGORY,
    ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT,
    ANALYTICS_ROLLUP_VALUES,
    MEASURE_STATUS_INCOMPLETE,
    MEASURE_STATUS_KNOWN,
    MEASURE_STATUS_NOT_APPLICABLE,
    MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN,
    MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON,
    MEASURE_STATUS_VALUES,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_WAIVED,
    USAGE_EVENT_KIND_TASK_CHARGE,
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
#: The VALUE the row groups, not the axis it was grouped on — the axis is
#: already named by the request's `group_by`, and repeating it once per row
#: would say the same thing over and over.
#:
#: ⚠ **IT WAS A SHARED CONSTANT BECAUSE THREE ROLLUPS ANSWERED THIS QUESTION
#: OVER THE SAME AXES AND ONLY ONE OF THEM DECLARED ITS ROWS.** The other two
#: returned `list[dict]`, so no schema, drift gate or breaking gate could hold
#: them to the spelling, and spelling it in three writers in two modules was
#: three chances to drift. #501 left ONE — `economics` below — so the constant
#: is now read by its writer and by the tests that pin the wire key, and what it
#: protects is a rename nobody meant rather than a divergence between siblings.
#:
#: ⚠ **AND THE ROW SAYS MORE THAN THE VALUE NOW.** `GROUPED_VALUE_STATUS_KEY`
#: travels beside it: the three rollups this replaced put every absent value
#: under one `(unattributed)` heading, and separating *not recorded* from *does
#: not apply* is one of the things the collapse bought.
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


# THE TENANT-WIDE DAILY REVENUE ROLLUP WAS HERE AND IS GONE (#501, slice 7 §1),
# with the billing route that was its only caller. It answered a window's
# supplier cost and billed total, a per-day series of the same pair, and a
# "markup" between them — which was the same difference the metering timeseries
# beside it already published under a different name, over the same postings.
#
# `economics` below answers it: the supplier cost and customer revenue measures,
# `bucket=day`, no grouping. The difference is the gross-margin measure, taken
# once at the bucket and carrying its own state rather than being arithmetic a
# reader has to bound for themselves.


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


# THE PER-EVENT-TYPE ROLLUP FOR ONE CUSTOMER WAS HERE AND IS GONE (#501, slice
# 7 §1), with the widget route that was its only caller. It is `economics`
# filtered to one customer and grouped by the Event Type axis.
#
# ⚠ ONE THING IT DID THAT THE REPLACEMENT DOES NOT, SAID HERE BECAUSE NOTHING
# ELSE RECORDS IT: a BUSINESS customer aggregated across its seats, on the same
# seat basis the postpaid business branch bills on. The one query filters on the
# customer the caller named and nothing else, so asking about a business answers
# about the business's own postings — of which there are none, because a
# business emits no usage of its own. A caller wanting the pooled figure groups
# by the customer axis over the seats, which is the shape the business rollup
# (`/margin/business/{external_id}`) already serves as a TREE and keeps.


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


# THE DAY-OR-HOUR SPEND SERIES WAS HERE AND IS GONE (#501, slice 7 §1), with
# the route that was its only caller. `bucket=day|hour` on `economics` answers
# it, optionally grouped and optionally filtered to one customer, with every
# bucket carrying its own completeness exactly as these rows did.
#
# ⚠ AND THE UNATTRIBUTED SENTINEL DIED HERE RATHER THAN MOVING. This function
# put every absent axis value under one `(unattributed)` heading, which folds
# *UBB does not know which provider* together with *the question does not apply
# to this kind of row* — two facts with two different remedies, one of which has
# none. `GROUPED_VALUE_STATUSES` is what separates them on the replacement, and
# that separation is one of the reasons the collapse was worth doing.


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


# THE GROUPED USAGE-ONLY MARGIN WAS HERE AND IS GONE (#501, slice 7 §1), with
# the route in another product that was its only caller. It grouped either by a
# resolved column or by a key read out of the open bag, and subtracted the
# supplier cost from the billed total PER ROW.
#
# ⚠ THE PER-ROW SUBTRACTION IS THE REASON THIS ONE HAD TO GO RATHER THAN BE
# WRAPPED. `economics` subtracts at the BUCKET and never at a row, because a
# row-level margin states a figure for a posting that was never going to carry
# revenue — and it counted only usage, so a customer's subscription and the
# revenue a tenant supplied itself were silently outside the number. That is the
# "silently different revenue basis" the collapse exists to remove: the same
# axes, the same arithmetic and a different answer from the surface beside it.
#
# The keyed half has no replacement, deliberately: the declared grouping
# contract publishes what a tenant may group by, and an unbounded keyspace is
# exactly the capability it does not have.


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


#: THE CUSTOMER-PRICE STATES THAT CARRY NO LIABILITY, AND THEREFORE NO INVOICE
#: LINE (#503, slice 7 §11).
#:
#: **A customer's invoice depends on revenue state only.** Both of these null
#: the amount and both are genuine zeroes rather than missing information — the
#: asymmetry `core.amount_status_pairs` argues for the completeness count — so a
#: total over them is already right. What is NOT already right is the LINE: a
#: group exists because a row produced it, so a posting nobody owes anything for
#: mints a heading on a customer's invoice with nothing under it.
#:
#: * `not_applicable` is every metered call beneath a fixed-price unit of work.
#:   The unit's own Charge is the liability and it projects one posting of its
#:   own, so rendering the calls as zero-revenue lines sends a customer hundreds
#:   of lines that say nothing. §11 is explicit that this is **worse on an
#:   invoice than on a dashboard**, where the same rows are a legitimate answer
#:   to *what work was done*.
#: * `waived` is a charge somebody decided not to pursue. There is no liability,
#:   so there is nothing to put on an invoice — and it must not vanish with the
#:   line: the loss it represents is reported by :func:`get_waived_loss`, which
#:   is the tenant's exposure surface and reads the same postings.
#:
#: ⚠ **`unknown` IS DELIBERATELY NOT HERE.** A price UBB could not resolve is a
#: liability it failed to put a number on, not an absent one, and dropping those
#: rows would silently shrink an invoice. They stay in, contribute nothing, and
#: are COUNTED — which is what makes a line a floor that says so (#351).
INVOICE_LINE_STATES_WITH_NO_LIABILITY = (PRICING_STATUS_WAIVED,
                                         PRICING_STATUS_NOT_APPLICABLE)


def _carrying_customer_liability(postings):
    """The postings an invoice line may be built from, filtered in one place.

    Both invoice reads below apply the same rule and a second copy is how the
    per-seat lines and the grouped lines come to disagree about what a customer
    owes.
    """
    return postings.exclude(
        pricing_status__in=INVOICE_LINE_STATES_WITH_NO_LIABILITY)


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

    ⚠ **A SEAT WHOSE EVERY POSTING CARRIES NO LIABILITY IS ABSENT, NOT PRESENT
    WITH A ZERO** (#503). This is the per-seat half of the invoice, so the rule
    at `INVOICE_LINE_STATES_WITH_NO_LIABILITY` applies here exactly as it does
    to the grouped half: a seat that only ever ran work under a fixed-price unit
    owes nothing of its own, and a zero line against its name on a customer's
    invoice is a line that should not have been drawn. The TOTAL is unmoved —
    those rows summed to nothing before they were excluded.
    """
    from apps.metering.usage.models import Posting

    rows = (_carrying_customer_liability(Posting.objects.filter(
        tenant_id=tenant_id, customer_id__in=list(customer_ids),
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    )).values("customer_id").annotate(
        **cost_total_annotations(CUSTOMER_PRICE, key="total")).order_by())
    return {r["customer_id"]:
            {"billed_cost_micros": carry_cost_total(
                CUSTOMER_PRICE, dict(r), key="total")["total"],
             UNPRICED_EVENT_COUNT_KEY: r[UNPRICED_EVENT_COUNT_KEY]}
            for r in rows}


#: THE HEADING AN INVOICE LINE TAKES WHERE THE AXIS HAS NO VALUE TO PUT ON IT.
#:
#: ⚠ **THIS IS WHERE THE INVOICE AND THE ANALYTICS CONTRACT DELIBERATELY PART**,
#: and both readings are right for their own surface. `economics` carries a null
#: value with `GROUPED_VALUE_STATUS_KEY` beside it, which says WHY there is no
#: value — the distinction #501 bought and the thing a chart must not hide. An
#: invoice cannot use it: a customer is charged under a HEADING, and a line with
#: no heading is a line nobody can dispute. So an absent value keeps a word here
#: rather than a status, and the two never become one rule.
INVOICE_LINE_OTHER = "(other)"


def get_customer_billed_breakdown(tenant_id, customer_id, period_start: date,
                                  period_end: date, group_by: str) -> list[tuple]:
    """Billed totals for ONE customer, grouped by one axis of §6's vocabulary.

    Returns UNSORTED, aggregated [(label, billed_micros, unpriced_event_count),
    ...] triples (the caller owns presentation order). The third element is
    #351's, and it is on the tuple for the reason `get_billed_totals_by_customer`
    above gives at length: these are invoice lines, so a line that is a floor and
    says nothing is money not charged.

    ⚠ **``group_by`` IS AN AXIS FROM :func:`grouping_options`, NOT A KEY** (#503,
    slice 7 §11). It took a free-text `"tag:<key>"` reading of the open bag, and
    anything else meant the first slot whatever the stored configuration spelled
    — the third of ADR-0005's ad-hoc label reads, the sharpest of its three
    free-text hatches, *and the only one a paying customer reads*. An unbounded
    key driving invoice line labels is how a 5,000-line invoice happens; a silent
    fall-through to a column nobody named is how a tenant is billed under
    headings they never chose. Both are gone: a word this tenant's discovery
    contract does not publish for the invoice surface is REFUSED, with the same
    sentence every other surface refuses it with.

    **The lines are money-only, and the rule is the revenue state's.** Postings
    carrying no customer liability are excluded before anything is grouped —
    `INVOICE_LINE_STATES_WITH_NO_LIABILITY` argues each one — so a fixed-price
    unit of work is ONE line, labelled by that unit, and the metered calls
    beneath it are none at all. **An unresolved SUPPLIER COST never delays,
    blocks or alters any of this**: it is read nowhere in this function, which is
    the whole of §11's rule underneath, and the cost's own completeness lives on
    the surfaces that report cost.

    Label semantics are the invoice's rather than the analytics contract's: a
    NULL, an empty slot value and an identity filed under no rollup heading ALL
    collapse into `INVOICE_LINE_OTHER`, which argues why. SQL GROUP BY pushdown;
    the collapse and the rollup's fold happen post-query, over at most as many
    rows as the axis has values.
    """
    from apps.metering.usage.models import Posting

    refusal = grouping_refusal(tenant_id, axes=[group_by],
                               surface=SURFACE_INVOICE_LINES)
    if refusal is not None:
        raise ValueError(refusal)
    # ⚠ THE REFUSAL ABOVE IS ALSO WHAT GUARANTEES `plan["column"]` IS A COLUMN.
    # The one axis with none is the measurement rollup, which groups records
    # BENEATH an event — and `_option` leaves it off this surface's list for
    # that reason, so it never reaches here. That is the discovery contract
    # deciding availability rather than this function keeping a second list,
    # which is §5.4's rule; it is written down because the coupling is real and
    # a reader would otherwise have to find it.
    plan = _axis_plan(tenant_id, group_by)

    rows = (_carrying_customer_liability(Posting.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    )).values(plan["column"])
      .annotate(**cost_total_annotations(CUSTOMER_PRICE, key="total"))
      .order_by())
    merged: dict = {}
    counts: dict = {}
    for r in rows:
        row = carry_cost_total(CUSTOMER_PRICE, dict(r), key="total")
        label = _invoice_line_label(plan, row[plan["column"]])
        merged[label] = merged.get(label, 0) + row["total"]
        counts[label] = counts.get(label, 0) + row[UNPRICED_EVENT_COUNT_KEY]
    return [(label, billed, counts[label]) for label, billed in merged.items()]


def _invoice_line_label(plan, raw) -> str:
    """The heading one group is charged under.

    A rollup's heading is what its identity is filed under, resolved through the
    membership the plan carries — and an identity nobody has filed has no
    heading, which lands in `INVOICE_LINE_OTHER` exactly as an empty column
    does. Both are *this line has no value on the chosen axis*, which is one
    fact on an invoice however many ways a chart needs to tell it apart.
    """
    value = raw
    if plan["membership"] is not None:
        value = plan["membership"].get(raw)
    return INVOICE_LINE_OTHER if value in (None, "") else str(value)


def invoice_line_cardinality_warning(tenant_id, axis) -> str | None:
    """What a tenant should be told about this axis BEFORE it bills on it.

    ⚠ **CARDINALITY IS THE ONE OF §7's THREE REFUSAL GROUNDS THE DISCOVERY
    CONTRACT CANNOT DECIDE**, and :func:`grouping_refusal` says so in terms: the
    cap is a number the tenant declared and how many lines an axis produces is a
    count over their postings, which only a query that runs them can know. So the
    cap travels on the row and this is the invoice surface's half of deciding
    with it.

    **It warns, and it warns at CONFIGURATION time.** Refusing would be wrong —
    the tenant declared the cap as a keyspace bound, not as an invariant, and a
    period that happens to exceed it is not a period UBB may decline to bill.
    Warning at invoice time would be worse than useless: the first anyone hears
    of it is a 5,000-line invoice that has already gone to a customer. The
    moment a tenant can still act on it is the moment they choose the axis.

    ⚠ **A ROLLUP AND AN ALWAYS-PRESENT AXIS ANSWER `None`, AND THAT IS NOT AN
    OMISSION.** `max_cardinality` is a cap the TENANT declared on an axis they
    declared; UBB's own axes carry none, so there is no maximum to exceed and
    nothing honest to say. The row's own `max_cardinality` is what decides,
    which keeps the rule in one place.

    The count is of distinct values RECORDED, over this tenant's whole history
    rather than over one period, because the question is what the axis *could*
    produce and a quiet month is not evidence. Blank values do not count: they
    are one `INVOICE_LINE_OTHER` line between them however many rows carry them,
    so counting them as values would overstate by as many as there are kinds of
    blank. They are dropped in PYTHON rather than excluded in SQL, which keeps
    this true of a column of any type — the axes with a cap are all declared
    text slots today, and an `.exclude(column="")` would raise the day one of
    them is not. The scan stops a few past the cap, because the answer is only
    ever compared against it and the two kinds of blank need room.
    """
    from apps.metering.usage.models import Posting

    option = {row["key"]: row for row in grouping_options(tenant_id)}.get(axis)
    if option is None or option["max_cardinality"] is None:
        return None
    ceiling = option["max_cardinality"]
    plan = _axis_plan(tenant_id, axis)
    values = (Posting.objects.filter(tenant_id=tenant_id)
              .values_list(plan["column"], flat=True)
              .distinct().order_by()[:ceiling + 3])
    found = len({value for value in values if value not in (None, "")})
    if found <= ceiling:
        return None
    return (f"{axis!r} has recorded more than {ceiling} distinct values, which "
            f"is the maximum this tenant declared for it — an invoice grouped "
            f"by it will carry more than {ceiling} lines. Group by a rollup for "
            f"fewer, more meaningful lines, or raise the axis's declared "
            f"maximum.")


def mark_backfill_dirty_period(tenant_id, customer_id, period_start) -> None:
    """Declare one customer's CLOSED month stale. Idempotent (#502, slice 7 §8).

    The second deliberate WRITE half of the marker contract, and the reason it
    exists on this side of the boundary: the marker table is metering's, and a
    period's economics go stale for reasons that are not (`apps/subscriptions`
    may not reach for the model, ADR-001). A tenant that bills its customers
    elsewhere can state what it earned in a month that closed long ago, and
    revenue is half of every margin the evaluator flags on — so a figure
    supplied late has to be able to reach the same rebuild a late supplier cost
    does.

    **The caller decides the period has closed**, because what counts as closed
    is the caller's own question: the recording path asks it of an event's
    effective month and the supplied-revenue write asks it of a record's stated
    period. Writing a marker for an open month is harmless but pointless — the
    consumer skips a non-prior marker without acking it.
    """
    from django.db import IntegrityError, transaction

    from apps.metering.usage.models import BackfillDirtyPeriod

    try:
        # The savepoint-IntegrityError-swallow the recording path uses on the
        # same unique key: a marker already pending for this period is the same
        # request made twice.
        with transaction.atomic():
            BackfillDirtyPeriod.objects.create(
                tenant_id=tenant_id, customer_id=customer_id,
                period_start=period_start)
    except IntegrityError:
        pass


def mark_backfill_dirty_period_for_posting(posting_id) -> None:
    """Declare the CLOSED month one posting lands in stale (#502, slice 7 §8).

    **The two doors a posting's money columns may move through after the fact
    are the same act twice**, and this is the half they share. A supplier cost
    settled long after the call and a customer price resolved long after it are
    each one ADR-0007 §2 conditional update on an existing posting, at an
    instant that may sit inside a month that closed — and each moves a figure
    two per-customer monthly caches are built from. Instrumenting one and not
    the other is how a cache stops being repairable on the cost side and stays
    unrepairable on the revenue side.

    ⚠ **THE PRICE HALF MATTERS FOR THE SAME REASON THE COST HALF DOES, POINTING
    THE OTHER WAY.** An excluded cost makes a margin a CEILING; an excluded
    price makes it a FLOOR. The customer named unprofitable on a floor is the
    one who might have been fine all along, so a late price is the resolution
    most worth letting reach a closed period.

    ⚠ **The CURRENT month is deliberately not marked.** Markers are only ever
    written for months that have closed — the hourly repair and the daily
    snapshot both cover the open one, and the consumer skips a non-prior marker
    without acking it.

    Nothing about the resolution depends on this succeeding: it is a request to
    rebuild a cache, read after the statement that moved the columns has already
    committed to its own outcome.
    """
    from django.utils import timezone

    from apps.metering.usage.models import Posting
    from core.time_windows import closed_months

    row = (Posting.objects.filter(pk=posting_id)
           .values("tenant_id", "customer_id", "effective_at").first())
    # Unreachable from either resolution door, which reaches here only after its
    # conditional update matched exactly one row. Kept because this is a
    # contract function and its callers are not all written yet: answering
    # "nothing to invalidate" for a posting that is not there beats raising
    # inside a caller that has already moved the money columns.
    if row is None:
        return
    for period_start in closed_months(row["effective_at"], now=timezone.now()):
        mark_backfill_dirty_period(row["tenant_id"], row["customer_id"],
                                   period_start)


def list_backfill_dirty_periods(created_before: datetime | None = None) -> list[dict]:
    """Pending markers for periods whose cached economics are stale (plain
    dicts, oldest first).

    Each: {"id", "tenant_id", "customer_id", "period_start" (date)}. Written
    whenever a fact behind a CLOSED month's cached figures moves — an event
    backfilled into a prior month by record_usage, a supplier cost settled long
    after the call, a figure the tenant supplied late — and consumed by
    subscriptions' resnapshot_dirty_periods, which acks each marker via
    clear_backfill_dirty_period() AFTER its snapshot work succeeds.

    ⚠ **THE NAME IS NARROWER THAN THE MEANING AND THE MEANING IS THE WIDER ONE.**
    Backfilled usage was the first cause and is no longer the only one; renaming
    the record is a migration nothing here needs, so the sentence above is the
    authority on what a marker says.

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
#: ⚠ **EVERY MONEY MEASURE IS REFUSED HERE, AND #498 COULD ONLY NAME ONE OF
#: THEM.** The reason above is about money and not about cost: UBB holds an
#: amount per POSTING on both sides of the margin, so a customer price at this
#: grain is the same event's revenue repeated once per quantity exactly as a
#: supplier cost would be, and a margin over two repeated figures repeats the
#: error twice. The commit that shipped this axis could name only ONE measure —
#: naming all of them would have made the discovery read the measure concept's
#: serving consumer and paid #499's entry by mention, which is the vacuous form
#: both tickets forbid — and it said so at the time. The set those exceptions
#: are exceptions to arrives with the query that computes the measures, so the
#: declaration is completed here, by the ticket that can afford it.
#:
#: **The count is what survives, and it keeps one meaning.** It counts the
#: POSTINGS carrying at least one quantity filed under a heading — not the
#: measurement records — so `recorded_events` still means what it means
#: everywhere else. A posting measured two ways under one heading is one event;
#: a posting measured under two headings is one event in each row, which is
#: what grouping by a many-valued join means and is why these rows do not add
#: up to the ungrouped total. That is a property of the question, not a defect
#: of the answer, and the response says so rather than hiding it.
MEASUREMENT_ROLLUP_UNSUPPORTED = (
    (ANALYTICS_MEASURE_SUPPLIER_COGS,
     "UBB records supplier cost per posting and not per measurement, so a cost "
     "at this grain could only be produced by repeating one event's whole cost "
     "against every quantity that event was measured by."),
    (ANALYTICS_MEASURE_CUSTOMER_REVENUE,
     "UBB records customer revenue per posting and not per measurement, so "
     "revenue at this grain could only be produced by repeating one event's "
     "whole price against every quantity that event was measured by."),
    (ANALYTICS_MEASURE_GROSS_MARGIN,
     "A margin at this grain would be the difference between two figures UBB "
     "holds per posting and not per measurement, so it would repeat one "
     "event's whole economics against every quantity it was measured by."),
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


# ---------------------------------------------------------------------------
# THE ONE ECONOMIC QUERY (#499 — slice 7 §2, §3, §5, §10, §15)
#
# IT IS AN ECONOMIC QUERY AND NOT A POSTING-GRAIN ONE, AND THAT DISTINCTION IS
# THE DESIGN. The measures below no longer share an origin, so each is
# aggregated from its OWN canonical fact source and combined with another only
# where their scopes are compatible. Everything this module did before could
# start from one queryset over one table and add columns; this cannot, and a
# reader who assumes it can will produce exactly the figure the slice exists to
# delete — a margin computed row by row over events that were never going to
# carry revenue.
# ---------------------------------------------------------------------------

#: THE FOUR THINGS THIS QUERY MEASURES, held by reference so the registry stays
#: the one place they are named.
#:
#: The whole set, and the completeness is the point: the answer a caller gets
#: back is built by asking each of these for its own amount and its own state,
#: so a fifth arriving in the registry with no line here would be a measure this
#: module silently never answers. The guard beneath says so loudly instead.
ECONOMIC_MEASURES = (
    ANALYTICS_MEASURE_SUPPLIER_COGS,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE,
    ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_RECORDED_EVENTS,
)

assert set(ECONOMIC_MEASURES) == ANALYTICS_MEASURE_VALUES, (
    "every declared measure needs a line in ECONOMIC_MEASURES")

#: The measures denominated in money, which is what makes them subtractable and
#: what makes them refusable at a grain UBB holds no money at.
MONEY_MEASURES = (ANALYTICS_MEASURE_SUPPLIER_COGS,
                  ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                  ANALYTICS_MEASURE_GROSS_MARGIN)

#: The time grains a caller may bucket at, and the truncation each one is.
#:
#: UBB owns this set and the registry declares no concept for it, on the terms
#: `GROUPING_GRAINS` above takes for its own: the contract does not RESTATE the
#: set, the field publishes as a plain string whose meaning the schema states in
#: prose, and this stays the one place the values live.
BUCKET_HOUR, BUCKET_DAY, BUCKET_MONTH = "hour", "day", "month"
ECONOMIC_BUCKETS = (BUCKET_HOUR, BUCKET_DAY, BUCKET_MONTH)
_BUCKET_TRUNCATIONS = {BUCKET_HOUR: TruncHour, BUCKET_DAY: TruncDay,
                       BUCKET_MONTH: TruncMonth}

assert set(_BUCKET_TRUNCATIONS) == set(ECONOMIC_BUCKETS), (
    "every bucket a caller may ask for needs a truncation to be answered with")

#: What a row says about the value it groups, BESIDE the value itself.
#:
#: ⚠ **TWO DIFFERENT FACTS USED TO SHARE ONE BUCKET, AND THIS IS THE PAIR THAT
#: SEPARATES THEM** (§5's second prohibition). The surfaces this query replaces
#: put every absent value under one `(unattributed)` heading, which conflates
#: *we do not know which provider* with *the question does not apply to these
#: rows at all* — and one of the two has a remedy (record it) while the other
#: never will. A charge projection names no Event Type by construction, because
#: a row wearing an Event Type nobody declared would be quarantined at the
#: catalogue; asking which Event Type it was is not a question with a missing
#: answer.
#:
#: The value is present exactly when the status is `recorded`, so a reader never
#: has to decide what an empty string meant.
GROUPED_VALUE_STATUS_KEY = "grouping_field_value_status"
VALUE_RECORDED = "recorded"
VALUE_NOT_RECORDED = "not_recorded"
VALUE_NOT_APPLICABLE = "not_applicable"
GROUPED_VALUE_STATUSES = (VALUE_RECORDED, VALUE_NOT_RECORDED,
                          VALUE_NOT_APPLICABLE)

#: The axes a charge posting cannot carry a value on, whatever the tenant does.
#:
#: DERIVED FROM THE PROJECTION'S OWN WRITER AND PINNED AGAINST IT. All three are
#: facts a RECORDING states about a metered call, and a charge projection is not
#: one: it is money owed for a delivered piece of work.
#: `pricing/services/charge_projection.py` sets the Event Type to the empty
#: string deliberately — a synthetic row wearing an Event Type nobody declared
#: would be quarantined at the catalogue — and never sets a supplier or the
#: contained kind of work at all, because the Charge it projects carries
#: neither. The TOP-level kind of work it does carry, copied off the Charge,
#: which is why that axis is not here.
#:
#: What a projection does carry beyond that is the declared grouping slots,
#: copied off the Charge, so a blank one there is an absence like anybody's and
#: reads `not_recorded` exactly as it would on a metered posting.
#:
#: It is a list here and a test there:
#: `apps/metering/tests/test_the_one_economic_query.py` projects an actual
#: Charge and asserts that exactly these axes come out blank on it, so the day
#: the projection learns to carry one of them this list goes red rather than
#: quietly answering `not_applicable` about a value that is now recordable.
#: That test wrote this list rather than the other way round — the first draft
#: was one axis short.
AXES_A_CHARGE_POSTING_CANNOT_CARRY = ("provider", "event_type", "subtask_type")

#: The measure states this query can reach, worst last.
#:
#: The ORDER is the precedence, and it runs from most to least informative about
#: the number beside it: a measure that cannot be attributed at this grain is
#: saying the figure is not the answer at all, which outranks a figure that is a
#: real bound. Ranking the other way would let a bound hide an inattributable
#: total. The retention state is last because it outranks even that: a grain
#: problem has a remedy on this surface — ask a coarser question — and an age
#: problem has none, so a figure standing beside it would be a figure about a
#: stretch nothing can be read from.
MEASURE_STATES_WORST_LAST = (MEASURE_STATUS_KNOWN, MEASURE_STATUS_INCOMPLETE,
                             MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN,
                             MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON)

#: ⚠ **FOUR OF THE REGISTRY'S FIVE, AND THE FIFTH IS NAMED RATHER THAN QUIETLY
#: ABSENT — WHICH IS WHY THIS GUARD SPELLS THE WHOLE SET.**
#:
#: `not_applicable` says the measure does not apply here, and nothing this query
#: does produces that: a combination a measure cannot answer is REFUSED against
#: the discovery contract before any row is built, which is §7's whole
#: mechanism, so an answer never contains a measure that does not apply to it.
#: #499 recorded that as a property of the design rather than an omission, and
#: #500 did not find a reading that made it reachable without folding two
#: failures into one value — the exact defect §4 forbids.
#:
#: So this module holds the concept as a SET and says which member it reaches:
#: the four above are computed, the fifth is declared unreachable here, and a
#: SIXTH arriving in the registry fails rather than becoming a state the answer
#: silently never carries. That is what makes this module the authority on the
#: concept rather than a consumer of some of it, and it is the condition the
#: contract's `enum` needs: a closed set is published whole or not at all
#: (publishing three values now and a fourth later is the break a generated
#: client's exhaustive switch cannot survive), so what the document needs is a
#: backend that knows the whole set, not one that can reach every member of it.
#:
#: The `assert` below is the idiom this module already uses twice, and it fails
#: at import on every ordinary run — but it is stripped under `python -O`, so
#: the control that really holds this is
#: `test_the_precedence_holds_every_value_but_the_refused_one`, which pins the
#: same equality. The statement here is for the reader; the test is the gate.
assert (set(MEASURE_STATES_WORST_LAST) | {MEASURE_STATUS_NOT_APPLICABLE}
        == MEASURE_STATUS_VALUES), (
    "every measure state needs a precedence here, or a stated reason this "
    "query cannot reach it")

#: The states under which a row states NO figure at all (#153 §8.5).
#:
#: Both are `unavailable_<why>`, and neither may carry a number: a margin UBB
#: cannot attribute at the requested grain is not a small margin, and a total
#: over a stretch the platform no longer holds is not a small total. `NO_FIGURE`
#: below is what they carry instead.
MEASURE_STATES_WITH_NO_FIGURE = (
    MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN,
    MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON)

#: THE ABSENCE OF THE REVENUE ARGUMENT, WHICH IS NOT THE SAME AS AN EMPTY ONE.
#:
#: A sentinel rather than `None` because `None` is a value a caller arrives at
#: by accident — a variable that was never set, a `dict.get` that missed — and
#: this is the one argument where *I did not think about it* must not be
#: readable as *there was none*, because the second answers a confident margin
#: that is short by a subscription. Asking whether the argument is PRESENT
#: rather than whether it is truthy is also what stops an empty list, a zero and
#: a `False` from all becoming the same request.
_NOTHING_WAS_CONTRIBUTED = object()

class EconomicFilters(NamedTuple):
    """What one economic question is asked ABOUT, as one value.

    ELEVEN VALUES THAT TRAVEL TOGETHER AND NOWHERE SEPARATELY — from the route,
    through the query, into the one function that narrows the postings. Passed
    loose they made a sixteen-parameter call whose order no reader could hold,
    and every surface that adopts this query in the tickets after it would have
    copied that call. Named, they also give the count's comparison rule
    something to ASK: a request pinned to one Event Type holds it constant in
    every row however it is grouped, which loose parameters could not express
    because the rule never saw them.

    Every field defaults, because a question with no filters at all is the
    ordinary tenant-wide one rather than a special case.
    """

    #: The window, inclusive of its end date — the reading every analytics
    #: surface in this module takes, and a strict bound at the NEXT midnight.
    start_date: object = None
    end_date: object = None
    customer_id: object = None
    event_type: str = None
    task_type: str = None
    #: The unit of work, and whether the work contained in it is in scope.
    task_id: object = None
    include_subtasks: bool = False
    #: The three stop-context filters, which compose with every grouping: what
    #: was spent past a stop, in one scope, in one episode.
    past_limit: bool = None
    stop_scope: str = None
    episode_seq: int = None
    #: The tenant's own declared axes, pinned to a value: `(axis word, value)`
    #: pairs, where the axis word is one the discovery contract publishes.
    field_filters: tuple = ()



#: WHAT A ROW HOLDS WHERE THE MEASURE HAS NO FIGURE TO STATE.
#:
#: `None`, never zero, and never the number the measure would have been if the
#: missing half were nothing (#153 §8.5). A margin UBB cannot attribute at the
#: requested grain is not a small margin.
NO_FIGURE = None


class EconomicQuestionRefused(ValueError):
    """A question this surface will not answer, raised where a sentence cannot
    be returned.

    A `ValueError` SUBCLASS, on `usage_service.EffectiveAtError`'s precedent and
    for its reason: the read contract's own door returns a sentence, and this is
    what the query raises when a caller reaches it without having asked. Its own
    type is what lets the composition layer catch THE REFUSAL rather than
    catching `ValueError` — which would turn any incidental one into a 422
    carrying an internal message to a tenant.
    """


def economic_refusal(tenant_id, *, measures, axes, event_type=None,
                     surface=SURFACE_ANALYTICS) -> str | None:
    """Why this economic question may not be answered, or ``None`` where it may.

    Everything :func:`grouping_refusal` refuses, plus the two refusals that are
    about the MEASURE SET rather than about one axis, and which therefore cannot
    be declared per axis on the discovery contract:

    ⚠ **REQUESTING NO MEASURE IS REFUSED, NEVER DEFAULTED.** A default measure
    set is how a caller ends up aggregating three different things to draw one
    line; the question *what did this cost, what did it earn, what is the
    difference* has to be asked before it can be answered.

    ⚠ **AND A COUNT MAY NOT BE COMPARED ACROSS GROUPS THAT MIX EVENT TYPES.**
    `recorded_events` counts records at the tenant's own declared granularity,
    so two rows are only comparable where each is confined to one Event Type or
    one heading over Event Types — otherwise a tenant metering one Event Type
    per token and another per request reads the first as ten thousand times the
    second. #154 §14 is explicit that the NAME makes the honest reading
    available and does not make the dishonest comparison impossible, and that
    the grouping constraint is the actual protection. So the constraint is
    stated here, against the discovery contract's own axes, because it is a
    property of the whole request and not of any one axis: grouping by provider
    is honest the moment the Event Type is grouped beside it, and a per-axis
    declaration could not say that.

    **TIME BUCKETS ARE NOT GROUPS FOR THIS PURPOSE AND THE DIFFERENCE IS REAL.**
    Every bucket of a bucketed query mixes Event Types the same way, so the
    comparison across them is like with like — which is exactly what the rule is
    protecting and not what it forbids.

    **AN UNGROUPED TOTAL IS ONE ROW AND COMPARES WITH NOTHING**, so it is
    answered. What stops a caller putting it on a slide as a headline is the
    measure's own name, which is #154 §14's own division of labour and the half
    it says the rename does buy.

    ⚠ **A FILTER HOLDS THE EVENT TYPE AS STEADY AS A GROUPING DOES, AND NOT
    ASKING ABOUT IT WAS A FALSE REFUSAL.** A request pinned to one Event Type
    has that type constant in every row by construction, however it is grouped —
    so refusing it would have turned down the single most honest shape of the
    question a caller can ask. `event_type` is the filter the route takes, and
    it is passed in here for exactly this.
    """
    if not measures:
        return ("an economic question names the measures it asks for; "
                f"send one or more of {', '.join(sorted(ECONOMIC_MEASURES))}")
    for measure in measures:
        if measure not in ECONOMIC_MEASURES:
            return (f"{measure!r} is not an economic measure; "
                    f"send one or more of {', '.join(sorted(ECONOMIC_MEASURES))}")
    refusal = grouping_refusal(tenant_id, axes=axes, measures=measures,
                               surface=surface)
    if refusal is not None:
        return refusal
    if (ANALYTICS_MEASURE_RECORDED_EVENTS in measures and axes
            and not event_type
            and not _keeps_the_event_type_constant(axes)):
        return (f"{ANALYTICS_MEASURE_RECORDED_EVENTS!r} counts records at the "
                "granularity each Event Type declares, so rows that mix Event "
                "Types are not comparable; group by "
                f"{grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, 'event_type')!r} "
                "or "
                f"{grouping_axis(ANALYTICS_GROUPING_KIND_ROLLUP, ANALYTICS_ROLLUP_EVENT_CATEGORY)!r} "
                "beside the axes you asked for, filter to one event_type, or "
                "drop the measure")
    return None


def _keeps_the_event_type_constant(axes) -> bool:
    """Whether this grouping confines each row to one Event Type or one heading
    over Event Types.

    The two axes that do are read off the vocabulary rather than spelled: the
    always-present Event Type field, and the rollup whose join is over Event
    Types. A third way of holding the Event Type steady would have to be added
    to the vocabulary first, and would be found here.
    """
    holds = {grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "event_type"),
             grouping_axis(ANALYTICS_GROUPING_KIND_ROLLUP,
                           ANALYTICS_ROLLUP_EVENT_CATEGORY)}
    return bool(holds & set(axes))


def economics(tenant_id, *, measures, group_by=(), bucket=None,
              filters=None, basis=None, as_of=None,
              contributed_revenue=_NOTHING_WAS_CONTRIBUTED) -> dict:
    """What this tenant's AI work cost, what it earned, and the difference.

    ONE definition of two numbers, answered over any filters, at any declared
    grouping axes, at hour, day or month — replacing the five backend
    definitions the surfaces above it each carried a copy of.

    ``measures``
        one or more of :data:`ECONOMIC_MEASURES`. Requesting none is refused by
        :func:`economic_refusal` rather than defaulted, and every caller runs
        that first.
    ``group_by``
        zero or more axis words from the discovery contract, each carrying its
        kind. A row holds its values POSITIONALLY under `grouping_field_value`,
        aligned with the words the caller sent — the request already named the
        axes and repeating them once per row would say the same thing over and
        over (`docs/adr/0005-declared-grouping-fields.md` settles the row key
        itself).
    ``bucket``
        ``hour``, ``day``, ``month``, or ``None`` for the whole period as one
        row. Bucketing sits on the same aggregate as the grouping and takes the
        same absence rule, which is vacuous for time and stated so rather than
        implied: a posting's `effective_at` is NOT NULL, so no bucket key is
        ever absent, where an axis value routinely is.
    ``filters``
        an :class:`EconomicFilters` — what the question is asked ABOUT. Absent
        means the ordinary tenant-wide question rather than a special case.
    ``as_of``
        the day the question is being asked, which is what the two retention
        horizons are measured back from. A caller that also resolves a window
        should pass the same day it resolved that window against, so the period
        and the horizons come from ONE reading of the clock — two readings a
        microsecond apart disagree across midnight.
    ``contributed_revenue``
        the revenue rows this product does not hold — see below. Passing
        nothing is a different request from passing none, and the default is
        neither: it is refused where a revenue measure was asked for.

    ⚠ **EACH MEASURE IS AGGREGATED FROM ITS OWN CANONICAL SOURCE**, and the
    sources genuinely differ:

    * ``recorded_events`` — postings, EXCLUDING the charge posting kind.
    * ``supplier_cogs`` — the supplier-cost pair on those same postings.
    * ``customer_revenue`` — the customer-price pair on postings, which is where
      a Charge lands 1:1 as a projection, PLUS the contributed rows, which are
      neither postings nor this product's.
    * ``gross_margin`` — revenue MINUS cost, at the bucket, never at a row.

    ⚠ **MARGIN IS A BUCKET-LEVEL SUBTRACTION, NEVER A ROW-LEVEL ONE** (#153 §2).
    A row-level subtraction produces a per-event margin for an event that was
    never going to carry revenue, which is the figure this whole slice exists to
    delete. Every total on both sides is aggregated first and the subtraction
    happens once, over the two aggregates a row will actually state.

    ⚠ **THE SCOPE RULE: margin is defined at a bucket only when every revenue
    component in that bucket is attributable at that bucket's grain** (§5).
    Where it is not, this answers the cost, answers the revenue it CAN
    attribute, names what it could not in `context`, and publishes NO margin.
    Three prohibitions hold it up, each with a live counterexample on the
    surfaces this replaces:

    * **Never distribute** across an operational axis. Allocating a
      customer-month revenue figure across providers pro-rata by cost produces a
      hypothetical, not an observation. So a contributed row is folded into a
      row's revenue only where every grouped axis is one the row itself declares
      it can be attributed at, and is otherwise reported beside the answer.
    * **Never bucket as unattributed.** See `GROUPED_VALUE_STATUSES`.
    * **Never silently drop.** The coarse revenue appears in `context` so the
      tenant can see the money exists and understand why no margin is drawn.

    **Time is the sole exception, it is explicit, and it is not unconditional.**
    A contributed row is attributed to the window it is asked about, because the
    record it came from declares its own span — interpolation inside a stated
    boundary. It declares no provider, no Event Type and no event, so spreading
    it along an operational axis would invent a boundary the record never
    asserted. ⚠ **And it declares that span in whole days**, so a question
    bucketed by hour is finer than the record itself and withholds the margin
    exactly as an operational axis does: interpolating inside a declared
    boundary is one thing, manufacturing a precision nobody stated is another.
    Each row names the finest bucket it goes to and this asks it.

    ⚠ **THE REVENUE THIS PRODUCT DOES NOT HOLD ARRIVES AS DATA, AND NOT PASSING
    IT IS REFUSED RATHER THAN READ AS ZERO.** A tenant's Stripe subscriptions
    and the figures it supplies itself belong to another product, and ADR-001
    forbids this module reaching for either — rightly, since on a service split
    metering would not have them. So the composition layer reads them from that
    product's own read contract and hands them over, each row saying whose it
    is, which window it lands in, where it came from and what it can be
    attributed at. A default of "none" would make *there was no subscription
    revenue* and *I forgot to ask* the same request, and the second one answers
    a confident margin that is short by a subscription — so the absence of the
    argument is a `ValueError` and only an explicitly empty sequence means
    there was none.

    ⚠ **TWO RETENTION HORIZONS, PUBLISHED ON EVERY ANSWER, TRUNCATED OR NOT**
    (§13). The platform keeps the money for six years and measurement detail on
    a shorter clock; `core.retention` owns both dates and the argument for why
    one is a constant and the other configurable. They are on every answer and
    not only on a truncated one, because *when can this series start* is a
    question a caller has to answer BEFORE choosing a window, and a field that
    appears only once something has gone wrong is a field nobody builds against.

    **WHICH CLOCK GOVERNS A ROW DEPENDS ON THE GROUPING, AND THAT IS THE WHOLE
    OF IT.** All four measures are economic and read from postings, so an
    ordinary question is governed by the six-year clock however it is filtered.
    A question grouped by the measurement-concept rollup reads the child records
    the shorter clock prunes, so those rows are governed by the shorter one.
    ⚠ **The shorter clock therefore never truncates a money chart** — which is
    what makes setting its number later a configuration change rather than a
    silent re-answering of every question a tenant already asks.

    ⚠ **A ROW WHOSE STRETCH REACHES BACK PAST ITS CLOCK STATES NO FIGURE.** Not
    zero, and not the partial total of the part that survived: a total over a
    stretch the platform no longer holds is not a small total, it is not a total.
    Every measure on such a row reads
    `unavailable_outside_retention_horizon` and carries the day its series can
    start. A row's stretch is the requested period where the question is
    unbucketed, and the bucket clamped to that period where it is bucketed — so
    a month bucket straddling the horizon is truncated and the month after it is
    not.

    ⚠ **AND A QUESTION WITH NO START DATE IS NOT A QUESTION ABOUT ALL OF
    HISTORY.** UBB holds nothing before the horizon, so an unbounded question is
    a question about *the horizon onwards*, and no row of it is truncated. The
    truncation bites when a caller NAMES a day the platform cannot answer for,
    which is the case where the old answer was a confident zero.

    ⚠ **AND NO `context` WHERE NOTHING COULD ANSWER, FOR THE SAME REASON IN THE
    OTHER DIRECTION.** A context row is a REMEDY — it names the axes and the
    bucket at which asking again would produce a margin — and a coarser
    question about a released stretch is refused exactly as this one was, so
    offering it there would publish an instruction that cannot work. The test is
    whether ANY row of this answer could state a figure, not whether the period
    reaches back: a window straddling the horizon keeps its context, because the
    buckets inside the horizon are exactly the ones a re-grouping would help.
    The money is not lost either way; it is answerable on any window inside the
    horizon, which this response states.

    ⚠ **THE LIMIT, NAMED RATHER THAN LEFT TO BE DISCOVERED: A GROUPED QUESTION
    OVER A STRETCH THE PLATFORM NO LONGER HOLDS HAS NO ROWS FOR IT.** Rows are
    the groups the data produces, and the groups that existed in a pruned
    stretch are exactly what the horizon no longer holds — there is no honest
    way to invent one, because inventing it would mean naming an axis value
    nobody can read back. What the caller gets is the two horizon fields, which
    say precisely why the series starts where it does. The one shape that is
    guaranteed a row is the ungrouped, unbucketed question, whose row always
    exists — and that is the shape whose old answer was zeros, so it is the one
    the fifth state matters most on.

    ⚠ **NON-GOAL — A CONFIDENT PRICE OVER AN UNRESOLVED COST (§15).** The
    pricing service consults the costing status only inside its margin-over-cost
    branch; every other path returns a confident price, that amount becomes a
    Charge, and the charge projection writes BOTH statuses as known onto the
    posting this sums for revenue. So a revenue measure here can read `known`
    over a cost nobody resolved. **#473 owns the fix and this query does not
    open the pricing service.** What it owes instead is honesty about the
    composite: `gross_margin`'s state is derived from BOTH inputs, so where the
    cost side is incomplete the margin is incomplete whatever the revenue side
    says. That is the honest rendering of a dishonest input, not a repair of it.
    """
    measures = tuple(measures)
    axes = tuple(group_by)
    filters = filters or EconomicFilters()
    refusal = economic_refusal(tenant_id, measures=measures, axes=axes,
                               event_type=filters.event_type)
    if refusal is not None:
        raise EconomicQuestionRefused(refusal)
    if bucket is not None and bucket not in ECONOMIC_BUCKETS:
        raise EconomicQuestionRefused(
            f"{bucket!r} is not a bucket; send one of "
            f"{', '.join(ECONOMIC_BUCKETS)}")
    wants_revenue = bool({ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                          ANALYTICS_MEASURE_GROSS_MARGIN} & set(measures))
    if wants_revenue and contributed_revenue is _NOTHING_WAS_CONTRIBUTED:
        # ⚠ NOT a refusal of the QUESTION — the question is fine and the caller
        # is the one that is wrong — so it raises the bare `ValueError` and the
        # composition layer does NOT translate it into a tenant-facing 422.
        raise ValueError(
            "a revenue measure needs the revenue rows this product does not "
            "hold; pass contributed_revenue=() to state that there are none")
    contributions = ([] if contributed_revenue is _NOTHING_WAS_CONTRIBUTED
                     else list(contributed_revenue))

    plans = [_axis_plan(tenant_id, word) for word in axes]
    postings = _economic_postings(tenant_id, filters)
    # Whether this answer is read out of the child records the shorter clock
    # prunes, which decides BOTH how it is grouped and which horizon governs it.
    # Asked once, because two readings of one fact are two answers waiting to
    # disagree.
    from_measurements = any(
        plan["rollup"] == ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT
        for plan in plans)

    if from_measurements:
        groups = _measurement_grouped(tenant_id, postings, plans, bucket)
    else:
        groups = _posting_grouped(tenant_id, postings, plans, bucket)

    attributable = _contributions_are_attributable(axes, contributions, bucket)
    if attributable and contributions:
        _fold_contributions_in(groups, plans, contributions, bucket)
    if not groups and not axes and bucket is None:
        # ⚠ AN UNGROUPED, UNBUCKETED QUESTION ALWAYS HAS EXACTLY ONE ROW, and
        # over an empty window that row is zeros. *What did all of this cost*
        # has the answer "nothing" when nothing happened, and answering it with
        # SILENCE would make the degenerate preset — three measures, no
        # grouping, no bucket — the one shape of this query that can return no
        # answer at all. A grouped or bucketed question is different in kind:
        # its rows are the groups that exist, and inventing one would be
        # inventing a group.
        groups[(None, ())] = _empty_group()

    horizons = retention_horizons(as_of or _today())
    holds_from = (horizons.measurement if from_measurements
                  else horizons.economic)
    ordered = sorted(groups.items(), key=_row_order)
    series_starts = [_series_start_if_released(key[0], filters, holds_from)
                     for key, _ in ordered]
    rows = [_economic_row(key, group, measures=measures,
                          attributable=attributable or not contributions,
                          available_from=series_start)
            for (key, group), series_start in zip(ordered, series_starts)]
    # ⚠ WHETHER A REMEDY IS WORTH OFFERING AT ALL — see `context` below. Two
    # clauses because there are two ways to deserve one, and an answer with no
    # rows needs the second: a grouped question over an EMPTY window inside the
    # horizon still wants to be told the money exists (that is #499's shape and
    # it is unchanged), while the same question over a released stretch does
    # not, because asking again in any shape reaches the same refusal.
    remediable = (any(start is None for start in series_starts)
                  or _series_start_if_released(None, filters,
                                               holds_from) is None)
    return {
        "group_by": list(axes),
        "bucket": bucket,
        "basis": basis,
        # Both horizons, whether or not anything was truncated — the docstring
        # above gives the reason.
        ECONOMIC_HORIZON_FIELD: horizons.economic.isoformat(),
        MEASUREMENT_HORIZON_FIELD: horizons.measurement.isoformat(),
        "rows": rows,
        # ⚠ AND NO CONTEXT WHERE NOTHING COULD ANSWER, BECAUSE CONTEXT IS A
        # REMEDY AND THERE IS NO RE-GROUPING HERE. Every `context` row carries
        # the axes and the bucket at which asking again WOULD produce a margin
        # — but a coarser question about a stretch the platform no longer holds
        # is refused for the same reason this one was, so offering it would
        # publish an instruction that cannot work. The money is not lost: it is
        # answerable on any window inside the horizon, which the answer states.
        "context": ([] if attributable or not remediable
                    else _context_rows(contributions, axes)),
    }


def _today():
    """The day the question is being asked, read in one place.

    ⚠ **THE ONLY CLOCK THIS MODULE READS, AND IT IS A DEFAULT RATHER THAN THE
    RULE.** Every caller that also resolves a window should pass its own `as_of`
    so the two come from one reading; this exists so that a caller with no
    window of its own — a test, a later surface asking the degenerate question —
    does not have to invent one.
    """
    return timezone.now().date()


def _series_start_if_released(bucket_start, filters, holds_from):
    """The day a row's series can start, where its stretch reaches back past
    that day — and ``None`` where the row is wholly inside the horizon.

    ⚠ **NAMED FOR WHAT IT RETURNS AND NOT FOR THE QUESTION IT ANSWERS.** A
    predicate name over a date-or-``None`` reads as a boolean at every call
    site, and one of those call sites feeds `available_from` straight onto the
    wire.

    The stretch is the requested period for an unbucketed question and the
    bucket for a bucketed one, and the `max` is what clamps a bucket to the
    period: a month bucket opening before the day the caller asked from was only
    ever summed from that day, so it is not truncated for opening early.

    ⚠ **AN ABSENT START DATE IS THE HORIZON, NOT THE BEGINNING OF TIME.** The
    platform holds nothing before it, so a question with no lower bound is a
    question from the horizon onwards and none of its rows is truncated. A
    caller only meets the fifth state by naming a day.
    """
    opens = filters.start_date or holds_from
    if bucket_start is not None:
        opens = max(bucket_start.date(), opens)
    return holds_from if opens < holds_from else None


def _economic_postings(tenant_id, filters):
    """Every posting the question is asked about, and nothing else.

    The filters the one query takes, applied in one place, so the five surfaces
    it replaces stop each having their own idea of what a filter means. The stop
    context trio compose with everything else exactly as they always did: a
    request can total what was spent past a stop, grouped by provider, bucketed
    by day, and each filter narrows the same set.
    """
    from apps.metering.usage.models import Posting

    qs = Posting.objects.filter(tenant_id=tenant_id)
    if filters.start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(filters.start_date))
    if filters.end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight, which is
        # what every window in this module means by an end date.
        qs = qs.filter(effective_at__lt=utc_next_day_start(filters.end_date))
    if filters.customer_id:
        qs = qs.filter(customer_id=filters.customer_id)
    if filters.event_type:
        qs = qs.filter(event_type=filters.event_type)
    if filters.task_type:
        qs = qs.filter(task_type=filters.task_type)
    if filters.past_limit is not None:
        qs = qs.filter(stop_context__isnull=not filters.past_limit)
    if filters.stop_scope is not None:
        qs = qs.filter(
            stop_context__contains=[{"stop_scope": filters.stop_scope}])
    if filters.episode_seq is not None:
        qs = qs.filter(
            stop_context__contains=[{"episode_seq": filters.episode_seq}])
    if filters.task_id is not None:
        from apps.platform.work.models import Task
        ids = [filters.task_id]
        if filters.include_subtasks:
            # Containment is a single level, so the whole tree is this one
            # indexed read — the same shape the event listing uses.
            ids += list(Task.objects.filter(
                tenant_id=tenant_id, parent_id=filters.task_id
            ).values_list("id", flat=True))
        qs = qs.filter(task_id__in=ids)
    for word, value in filters.field_filters:
        plan = _axis_plan(tenant_id, word)
        if plan["column"] is None:
            raise EconomicQuestionRefused(
                f"{word!r} groups records beneath an event and cannot be an "
                "equality filter on the events themselves")
        qs = qs.filter(**{plan["column"]: value})
    return qs


def _axis_plan(tenant_id, word) -> dict:
    """How one request word is answered: the column to group, and the fold after.

    A declared field resolves to its slot through the registry, an always-present
    axis to its own column, and a rollup to the column its join starts from plus
    the membership that folds it. The measurement rollup has no column at all —
    it groups records beneath an event rather than the event — which is why it
    takes a different aggregate and cannot be an equality filter.
    """
    from apps.platform.grouping_fields.queries import slot_map

    parsed = parse_grouping_axis(word)
    if parsed is None:
        raise ValueError(f"{word!r} names no grouping kind")
    kind, name = parsed
    if kind == ANALYTICS_GROUPING_KIND_ROLLUP:
        if name == ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT:
            return {"word": word, "column": None, "rollup": name,
                    "membership": None, "field": None}
        return {"word": word, "column": "event_type", "rollup": name,
                "membership": rollup_membership(tenant_id, name),
                "field": "event_type"}
    if name in RESERVED_KEYS:
        # The customer is grouped by IDENTITY, which is what the per-customer
        # margin list this replaces returned and what a caller can look a
        # customer up by. Its external id is the tenant's own word for the same
        # row and belongs to the surface that renders it.
        column = "customer_id" if name == "customer" else name
        return {"word": word, "column": column, "rollup": None,
                "membership": None, "field": name}
    slot = slot_map(tenant_id).get(name)
    if slot is None:
        raise ValueError(f"{word!r} is not a grouping axis this tenant has "
                         "declared")
    return {"word": word, "column": slot, "rollup": None, "membership": None,
            "field": name}


def _posting_grouped(tenant_id, postings, plans, bucket) -> dict:
    """The money and the count, grouped by the requested axes and the bucket.

    ⚠ **THE POSTING KIND IS ALWAYS A GROUP KEY AND IS ALWAYS FOLDED AWAY
    AFTERWARDS**, which buys two separate things in one aggregate. It is what
    lets `recorded_events` exclude the charge posting kind while the money
    measures keep it — a Task must not count its own invoice as work, and its
    invoice is nonetheless revenue. And it is what tells an absent value's two
    causes apart, because whether an axis APPLIES to a row is a fact about the
    kind of row it is.
    """
    # The columns are named in `values()` directly and the alias a row publishes
    # is only ever POSITIONAL, in Python. An annotation per axis would have to
    # invent a name, and any name it invented could collide with the model field
    # it was aliasing — which Django answers with a `ValueError` naming neither
    # the axis nor the request that asked for it.
    columns = [plan["column"] for plan in plans]
    grouped = (postings
               .values("kind", *columns,
                       **({"bucket_start": _BUCKET_TRUNCATIONS[bucket](
                           "effective_at")} if bucket is not None else {}))
               .annotate(
                   event_count=Count("id"),
                   **cost_total_annotations(SUPPLIER_COST,
                                            key="provider_cost_micros"),
                   **cost_total_annotations(CUSTOMER_PRICE,
                                            key="billed_cost_micros"))
               .order_by())

    groups = {}
    for raw in grouped:
        row = carry_cost_total(SUPPLIER_COST, dict(raw),
                               key="provider_cost_micros")
        row = carry_cost_total(CUSTOMER_PRICE, row, key="billed_cost_micros")
        values = tuple(_grouped_value(plan, row[plan["column"]], row["kind"])
                       for plan in plans)
        _accumulate(groups, (row.get("bucket_start"), values), row)
    return groups


def _measurement_grouped(tenant_id, postings, plans, bucket) -> dict:
    """The count, grouped by a heading over the quantities beneath an event.

    ⚠ **IT COUNTS POSTINGS AND NOT MEASUREMENT RECORDS**, which is what keeps
    `recorded_events` meaning one thing on every axis: a posting measured two
    ways under one heading is one event. It is also why the rows of such a query
    do not add up to the ungrouped total — a posting whose quantities sit under
    two headings is one event in each row — and that is a property of asking a
    many-valued question rather than a defect in the answer.

    ⚠ **THE FOLD IS IN PYTHON AND THAT IS THE COST §7 NARROWED THE AXIS OVER.**
    The heading a quantity sits under is a map keyed by the PAIR of an Event
    Type and a code, and the quantities themselves live in a bag on the child
    record, so no `GROUP BY` can reach them. The per-call window bound is what
    keeps it finite today; the row that makes this cheap is #513's, by name.

    The clock is the POSTING's, not the child record's. The child carries the
    moment its quantities were recorded, which for rows folded out of their
    posting long predates them; an economic question is asked about when the
    work was effective, and one query answers on one clock.
    """
    from apps.metering.usage.models import PostingMeasurement

    membership = rollup_membership(tenant_id,
                                   ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT)
    other = [plan for plan in plans
             if plan["rollup"] != ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT]
    fields = ["posting_id", "posting__kind", "posting__event_type",
              "posting__effective_at", "measurements"]
    fields += [f"posting__{plan['column']}" for plan in other]

    seen = {}
    for record in (PostingMeasurement.objects
                   .filter(posting__in=postings).values(*fields).iterator()):
        headings = {membership[(record["posting__event_type"], code)]
                    for code in record["measurements"]
                    if (record["posting__event_type"], code) in membership}
        if not headings:
            # A quantity nobody has filed is absent rather than present under a
            # sentinel — the kernel's own rule for this map, and §5's second
            # prohibition one layer down.
            continue
        kind = record["posting__kind"]
        bucket_start = _bucket_of(record["posting__effective_at"], bucket)
        for heading in headings:
            values = []
            for plan in plans:
                if plan["rollup"] == ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT:
                    values.append((heading, VALUE_RECORDED))
                else:
                    values.append(_grouped_value(
                        plan, record[f"posting__{plan['column']}"], kind))
            seen.setdefault((bucket_start, tuple(values)), set()).add(
                (record["posting_id"], kind))

    groups = {}
    for key, postings_seen in seen.items():
        counted = sum(1 for _, kind in postings_seen
                      if kind != USAGE_EVENT_KIND_TASK_CHARGE)
        groups[key] = _empty_group()
        groups[key][ANALYTICS_MEASURE_RECORDED_EVENTS] = counted
    return groups


def _bucket_of(moment, bucket):
    """Which bucket a moment falls in, matching the database truncation.

    Python-side because the measurement fold is Python-side; the two have to
    agree, so this states the same three truncations the aggregate uses rather
    than a fourth idea of what a month is.
    """
    if bucket is None:
        return None
    if bucket == BUCKET_HOUR:
        return moment.replace(minute=0, second=0, microsecond=0)
    if bucket == BUCKET_DAY:
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _grouped_value(plan, raw, kind) -> tuple:
    """One axis's value for one group, and what the row says about it.

    Returns the ``(value, status)`` pair the row publishes positionally. A
    rollup's value is the heading its column's value is filed under, and an
    identity nobody has filed has no heading — which is an absence like any
    other and not a sentinel heading of its own.
    """
    value = raw
    if plan["membership"] is not None:
        value = plan["membership"].get(raw)
    if value not in (None, ""):
        return (str(value), VALUE_RECORDED)
    if (kind == USAGE_EVENT_KIND_TASK_CHARGE
            and plan["field"] in AXES_A_CHARGE_POSTING_CANNOT_CARRY):
        return (None, VALUE_NOT_APPLICABLE)
    return (None, VALUE_NOT_RECORDED)


def _empty_group() -> dict:
    """One group's accumulators, all of them present from the start.

    Every key exists whether or not a row contributed to it, because a measure
    that reads its own total with `.get` cannot tell a group that summed to zero
    from one the aggregate never reached.
    """
    return {ANALYTICS_MEASURE_RECORDED_EVENTS: 0,
            "provider_cost_micros": 0, UNRESOLVED_EVENT_COUNT_KEY: 0,
            "posting_revenue_micros": 0, UNPRICED_EVENT_COUNT_KEY: 0,
            "contributed_revenue_micros": 0}


def _accumulate(groups, key, row) -> None:
    """Fold one aggregate row into its group.

    ⚠ The count excludes the charge posting kind and the money does not, which
    is the whole reason the kind was a group key: **a Task must not count its
    own invoice as work**, and that invoice is still revenue the tenant earned.
    """
    group = groups.setdefault(key, _empty_group())
    if row["kind"] != USAGE_EVENT_KIND_TASK_CHARGE:
        group[ANALYTICS_MEASURE_RECORDED_EVENTS] += row["event_count"]
    group["provider_cost_micros"] += row["provider_cost_micros"]
    group[UNRESOLVED_EVENT_COUNT_KEY] += row[UNRESOLVED_EVENT_COUNT_KEY]
    group["posting_revenue_micros"] += row["billed_cost_micros"]
    group[UNPRICED_EVENT_COUNT_KEY] += row[UNPRICED_EVENT_COUNT_KEY]


def _contributions_are_attributable(axes, contributions, bucket) -> bool:
    """Whether every contributed row can be placed at the requested grain.

    ⚠ **THE ROWS SAY WHAT THEY CAN BE ATTRIBUTED AT AND THIS ASKS THEM**, rather
    than holding a list of the other product's axes. An ungrouped question
    places everything by construction; a question grouped only by axes every row
    admits places everything too; anything else does not, and no amount of
    arithmetic makes it.

    ⚠ **TIME IS THE EXCEPTION AND IT IS NOT AN UNCONDITIONAL ONE.** Distributing
    a figure inside the span its own record declares is interpolation; placing
    it at a grain FINER than that span is manufacturing a precision the record
    never stated. Each row names the finest bucket it goes to, so a question
    bucketed more finely than that withholds the margin exactly as an
    operational axis does — rather than landing a month's subscription at
    midnight and calling it an hourly figure.
    """
    if not contributions:
        return True
    admitted = set.intersection(*[
        {grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, name)
         for name in row["attributable_axes"]}
        for row in contributions])
    if not set(axes) <= admitted:
        return False
    if bucket is None:
        return True
    coarsest = max(ECONOMIC_BUCKETS.index(row["finest_bucket"])
                   for row in contributions)
    return ECONOMIC_BUCKETS.index(bucket) >= coarsest


def _fold_contributions_in(groups, plans, contributions, bucket) -> None:
    """Add each contributed row to the group its window and its customer name.

    Only ever called where every row is attributable, so there is no branch here
    deciding to drop one — a function that could silently drop revenue is the
    third prohibition wearing a helper's clothes.
    """
    # ⚠ EVERY AXIS PRESENT HERE IS ONE THE ROWS ADMIT, which is what being
    # called at all means — so there is no "some other axis" case to write, and
    # writing one would have produced a value-less row claiming a RECORDED
    # status, against this module's own rule that the value is present exactly
    # when the status says `recorded`. Asserted rather than branched on, so the
    # day a contribution admits a second axis this fails loudly instead of
    # quietly filing the money under a blank.
    assert all(plan["field"] == "customer" and plan["rollup"] is None
               for plan in plans), (
        "a contribution is only folded in where every grouped axis is one it "
        "declares it can be attributed at")
    for row in contributions:
        bucket_start = (_bucket_of(_as_moment(row["window_start"]), bucket)
                        if bucket is not None else None)
        values = tuple((row["customer_id"], VALUE_RECORDED) for _ in plans)
        key = (bucket_start, values)
        group = groups.setdefault(key, _empty_group())
        group["contributed_revenue_micros"] += row["amount_micros"]


def _as_moment(day):
    """A window's opening date as the UTC instant the aggregate would bucket."""
    return utc_day_start(day)


def _context_rows(contributions, axes) -> list[dict]:
    """The revenue that exists and could not be placed at this grouping.

    ⚠ **THE THIRD PROHIBITION, WHICH IS THE ONE WITH NOTHING TO SHOW FOR IT
    ANYWHERE ELSE.** Never distributing and never bucketing as unattributed both
    leave a visible mark in the answer; silently dropping leaves none, and a
    tenant looking at a chart with no margin on it has no way to tell whether
    there was no money or whether UBB declined to place it. So the money is
    presented beside the answer, with whose it is, where it came from, and the
    axes at which asking again WOULD produce a margin.
    """
    rows = []
    for row in contributions:
        rows.append({
            "source": row["source"],
            "customer_id": row["customer_id"],
            "amount_micros": row["amount_micros"],
            "window_start": row["window_start"].isoformat(),
            "window_end": row["window_end"].isoformat(),
            "attributable_axes": [
                grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, name)
                for name in row["attributable_axes"]],
            # The other half of the remedy, and it is a different one: where
            # the question was bucketed too finely rather than grouped too
            # operationally, changing the axes would not help and this says so.
            "attributable_bucket": row["finest_bucket"],
        })
    return rows


def _row_order(item):
    """Rows in a stable, readable order: oldest bucket first, then by value.

    A tuple of `(value, status)` pairs sorts on the value and then on the status,
    and a `None` value cannot be compared with a string — so absences sort after
    everything recorded, together, which is where a reader expects them.
    """
    (bucket_start, values), _ = item
    return (bucket_start.isoformat() if bucket_start is not None else "",
            tuple((value is None, value or "", status)
                  for value, status in values))


def _economic_row(key, group, *, measures, attributable,
                  available_from) -> dict:
    """One row of the answer: what it groups, and each requested measure.

    The subtraction happens HERE and only here, over the two totals this row
    will actually state — which is what "a bucket-level subtraction" means in
    code rather than in prose.

    ``available_from`` is the day this row's series can start, passed exactly
    where the row's stretch reaches back past the horizon governing it — so the
    KEY is absent from this plain data otherwise, which is not the same as what
    the wire carries: the published field is on every measure and holds `null`
    where there is a figure, and the schema says so at its own field. It
    decides every measure at once: there is no figure to state and no partial
    one worth stating, so the row says which day it could have answered from
    instead. ⚠ **The four figure slots stay exactly the slots each measure fills
    when the figure IS known** — one `return`, so the two branches can only
    differ in what they state about a measure, and held to that by
    `apps/metering/tests/test_the_one_economic_query.py` besides, because a
    measure that filled one slot with a number and nulled a different one would
    publish a count as money on the very rows a reader is least able to check.
    """
    bucket_start, values = key
    # ⚠ THE COUNT DOES NOT SHARE THE MONEY'S FIELD, AND THE MEASURE'S OWN NAME
    # IS WHAT SAYS WHICH ONE IT FILLS. Three of the four are denominated in
    # micros and the fourth is a number of records; putting a count in a field
    # whose name ends `_micros` would be a hundredth-of-a-cent reading of two,
    # which is the kind of quiet unit error this whole programme is about. So
    # each measure fills exactly one, and the other is null — in BOTH branches
    # below, which is what makes a truncated row the same shape as an answered
    # one rather than a second shape a reader has to learn.
    if available_from is not None:
        gone = {"status": MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON,
                AVAILABLE_FROM_FIELD: available_from.isoformat()}
        built = {
            ANALYTICS_MEASURE_SUPPLIER_COGS: {
                "amount_micros": NO_FIGURE,
                UNRESOLVED_EVENT_COUNT_KEY: NO_FIGURE, **gone},
            ANALYTICS_MEASURE_CUSTOMER_REVENUE: {
                "amount_micros": NO_FIGURE,
                UNPRICED_EVENT_COUNT_KEY: NO_FIGURE, **gone},
            ANALYTICS_MEASURE_RECORDED_EVENTS: {
                "event_count": NO_FIGURE, **gone},
            ANALYTICS_MEASURE_GROSS_MARGIN: {
                "amount_micros": NO_FIGURE, **gone},
        }
    else:
        revenue = (group["posting_revenue_micros"]
                   + group["contributed_revenue_micros"])
        cost_state = (MEASURE_STATUS_INCOMPLETE
                      if group[UNRESOLVED_EVENT_COUNT_KEY]
                      else MEASURE_STATUS_KNOWN)
        if not attributable:
            revenue_state = MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN
        elif group[UNPRICED_EVENT_COUNT_KEY]:
            revenue_state = MEASURE_STATUS_INCOMPLETE
        else:
            revenue_state = MEASURE_STATUS_KNOWN
        built = {
            ANALYTICS_MEASURE_SUPPLIER_COGS: {
                "amount_micros": group["provider_cost_micros"],
                "status": cost_state,
                UNRESOLVED_EVENT_COUNT_KEY: group[UNRESOLVED_EVENT_COUNT_KEY]},
            ANALYTICS_MEASURE_CUSTOMER_REVENUE: {
                "amount_micros": revenue,
                "status": revenue_state,
                UNPRICED_EVENT_COUNT_KEY: group[UNPRICED_EVENT_COUNT_KEY]},
            ANALYTICS_MEASURE_RECORDED_EVENTS: {
                "event_count": group[ANALYTICS_MEASURE_RECORDED_EVENTS],
                "status": MEASURE_STATUS_KNOWN},
            ANALYTICS_MEASURE_GROSS_MARGIN: _margin(
                revenue, group["provider_cost_micros"],
                revenue_state=revenue_state, cost_state=cost_state),
        }
    return {
        "bucket_start": (bucket_start.isoformat()
                         if bucket_start is not None else None),
        GROUPED_VALUE_KEY: [value for value, _ in values],
        GROUPED_VALUE_STATUS_KEY: [status for _, status in values],
        # IN THE REGISTRY'S ORDER RATHER THAN THE REQUEST'S, and every row of
        # every answer therefore lists them the same way. A caller reads a
        # measure by its own name — that is what the name on each entry is for
        # — so honouring the request's order would buy nothing and would make
        # two requests for the same four measures answer in two shapes.
        "measures": [{"measure": measure, **built[measure]}
                     for measure in ECONOMIC_MEASURES if measure in measures],
    }


def _margin(revenue, cost, *, revenue_state, cost_state) -> dict:
    """Revenue minus cost, and what the difference is worth.

    ⚠ **ITS STATE IS DERIVED FROM BOTH INPUTS, NEVER FROM THE REVENUE SIDE
    ALONE** (§15). Where the cost side is incomplete the margin is incomplete
    whatever the revenue side says — which matters precisely because the revenue
    side CAN read `known` over a cost nobody resolved, since the pricing service
    returns a confident price outside its margin-over-cost branch and the charge
    projection writes both statuses as known. #473 owns that; this states it
    rather than hiding it.

    Where either side cannot be attributed at this grain there is no margin at
    all — not a small one, and not one computed from the half that could be
    placed — so the figure is absent and the state says why. The test is against
    the whole family of unavailable states rather than against one of them, so a
    state added to that family cannot arrive carrying a subtraction.
    """
    state = max((revenue_state, cost_state),
                key=MEASURE_STATES_WORST_LAST.index)
    if state in MEASURE_STATES_WITH_NO_FIGURE:
        return {"amount_micros": NO_FIGURE, "status": state}
    return {"amount_micros": revenue - cost, "status": state}
