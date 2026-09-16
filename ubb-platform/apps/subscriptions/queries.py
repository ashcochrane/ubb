"""Subscriptions Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(and the API layer) to read subscriptions data.

If subscriptions becomes a separate service, these functions
become HTTP calls. All callers remain untouched.

Consumers:
- api/v1/subscriptions_endpoints.py (future)
- api/v1/metering_endpoints.py → revenue_contributions() (the one economic
  query's revenue half, #499 — the composition layer wires it to metering's
  read contract, which is where the measures are computed)
"""
from datetime import date

from core.vocabulary import REVENUE_BASIS_VALUES

#: WHERE A REVENUE FIGURE THIS PRODUCT HOLDS CAME FROM.
#:
#: Two sources that stay apart all the way to the wire, which is #496's whole
#: subject: a Stripe subscription UBB mirrors and a figure the tenant supplied
#: itself are two different facts, and summing them one layer early is how the
#: provenance of a revenue number was destroyed before.
#:
#: UBB owns this pair and the registry declares no concept for it — legal, and
#: legal for the reason `event_types.VALUE_TYPE_CHOICES` gives for its own pair:
#: the contract does not RESTATE the set. The one economic query publishes these
#: words on a plain string whose meaning its schema states in prose, so this
#: stays the one place the values live.
REVENUE_SOURCE_SUBSCRIPTION = "subscription"
REVENUE_SOURCE_TENANT_SUPPLIED = "tenant_supplied"
REVENUE_SOURCES = (REVENUE_SOURCE_SUBSCRIPTION, REVENUE_SOURCE_TENANT_SUPPLIED)

#: THE ONLY AXIS EITHER SOURCE CAN BE ATTRIBUTED AT, and the reason the one
#: economic query needs to be told rather than to assume.
#:
#: Neither record names a provider, an event type or an event. A subscription is
#: an agreement with a CUSTOMER and a supplied figure is a statement about one,
#: so a customer is the finest operational grain either can honestly reach —
#: spreading one along an operational axis would invent a boundary the record
#: never asserted (slice 7 §5).
#:
#: ⚠ TIME IS NOT IN THIS LIST AND THAT IS NOT AN OMISSION. A contribution is
#: attributed to a window, so the window IS the time attribution; each record
#: declares its own span, which is what makes distributing inside one
#: interpolation rather than invention. This names the operational axes only.
REVENUE_ATTRIBUTABLE_AXES = ("customer",)

#: THE FINEST TIME GRAIN EITHER SOURCE CAN HONESTLY BE PLACED AT.
#:
#: Both declare their spans in WHOLE DAYS — a supplied record's period opens and
#: closes on a date, and a mirrored subscription's accrual divides a monthly
#: amount by days in the month — so a day is as fine as either goes. Asked to
#: place one inside an hour, the honest answer is that it cannot be placed:
#: interpolation inside a boundary the record declared is one thing, and
#: manufacturing a precision it never stated is another. The query reads this
#: and withholds the margin rather than landing a month's subscription at
#: midnight.
REVENUE_FINEST_BUCKET = "day"


def get_customer_economics(tenant_id, customer_id, period_start: date, period_end: date):
    """Returns CustomerEconomics or None."""
    from apps.subscriptions.economics.models import CustomerEconomics

    return CustomerEconomics.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
        period_start__gte=period_start,
        period_end__lte=period_end,
    ).order_by("-period_start").first()


def get_economics_summary(tenant_id, period_start: date, period_end: date):
    """Returns aggregated economics for all customers.

    THIS TOTAL IS A PAIR, AND ITS COUNT IS INHERITED RATHER THAN MEASURED HERE
    (#327, #328).

    Every supplier-cost total in the tree travels with the count of postings it
    excluded, because `Posting.provider_cost_micros` is nullable and a bare
    `Sum` over it silently skips the unresolved rows. **This `Sum` is not over
    that column.** `CustomerEconomics.provider_cost_micros` is a monthly
    SNAPSHOT, `NOT NULL` with a default of zero, so SQL's null-skipping cannot
    reach it — its `Sum` is `None` only when no snapshot matched, which is the
    empty sum and is exactly complete.

    What it inherits instead is a partiality from upstream, which is why #327
    left the figure alone and #328 did not: the accumulator these snapshots are
    built from now COUNTS the costs it could not add, and the snapshot freezes
    that count beside the total. So the number summed here is a real one every
    row computed, not a zero published to look like the others — the count
    arrived with the fact, and the fact is what is being added up.
    `apps/subscriptions/tests/test_queries.py` holds the cost column to `NOT
    NULL`, so the paragraph above fails rather than ages.
    """
    from apps.subscriptions.economics.models import CustomerEconomics
    from django.db.models import Sum

    qs = CustomerEconomics.objects.filter(
        tenant_id=tenant_id,
        period_start__gte=period_start,
        period_end__lte=period_end,
    )
    from core.cost_totals import (
        UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY)

    totals = qs.aggregate(
        total_subscription_revenue=Sum("subscription_revenue_micros"),
        total_supplied_revenue=Sum("supplied_revenue_micros"),
        total_usage_billed=Sum("usage_billed_micros"),
        total_provider_cost=Sum("provider_cost_micros"),
        total_unresolved=Sum("unresolved_event_count"),
        total_unpriced=Sum("unpriced_event_count"),
        total_margin=Sum("gross_margin_micros"),
    )
    return {
        "subscription_revenue_micros": totals["total_subscription_revenue"] or 0,
        # THE SECOND REVENUE SOURCE, SUMMED SEPARATELY (#496). A caller adding
        # the two gets the tenant's whole non-usage revenue; a caller reading
        # either alone knows which kind of money it has. Summing them here
        # would put a Stripe figure and a tenant's own statement back in one
        # number, which is the defect the column beside it exists to end.
        "supplied_revenue_micros": totals["total_supplied_revenue"] or 0,
        "usage_billed_micros": totals["total_usage_billed"] or 0,
        # ⚠ THE `or 0` ON THESE TWO LINES IS THE EMPTY SUM AND NOTHING ELSE, and
        # that is what makes it different from every coalesce this slice deleted
        # (#328). Both columns are NOT NULL on the snapshot, so `None` can only
        # mean no snapshot matched the window — and a window with no snapshots
        # spent nothing and excluded nothing, which is a complete answer. The
        # coalesce this slice removed stood over a NULLABLE column, where the
        # same 0 could also have meant "UBB has not learned this".
        "provider_cost_micros": totals["total_provider_cost"] or 0,
        UNRESOLVED_EVENT_COUNT_KEY: totals["total_unresolved"] or 0,
        UNPRICED_EVENT_COUNT_KEY: totals["total_unpriced"] or 0,
        "total_margin_micros": totals["total_margin"] or 0,
        "customer_count": qs.count(),
    }


def revenue_contributions(tenant_id, *, windows, basis, customer_ids=None) -> list[dict]:
    """Every revenue figure THIS product holds, per window, per customer, per source.

    The revenue half of the one economic query (slice 7 §2/§3). Metering owns
    the postings a price was resolved on; this product owns the two sources that
    are not postings at all, and the query that composes them may not reach
    across the boundary for either (ADR-001). So they arrive here as plain data,
    each row saying which window it lands in, whose it is and where it came
    from, and metering's read contract decides what a grouping can do with it.

    ``windows``
        half-open ``(start, end)`` date pairs — the query's buckets, or one pair
        for the whole period where it asked for none. The database is read ONCE
        for the union of them and every window is then attributed in Python, so
        a year bucketed by day costs two queries rather than seven hundred.
    ``basis``
        ``recorded`` or ``recognised``, applied to the supplied records only.
        ⚠ The subscription accrual has exactly one view and is NOT affected:
        Stripe states an amount per interval and nothing else, so there is no
        second reading of it to offer and pretending otherwise would publish a
        basis that means nothing on half the rows.

    A row is emitted for every contribution the sources make, INCLUDING a zero:
    a tenant recording a free month is stating that revenue was nothing, which
    is a different fact from having supplied nothing at all (#153 §3.4), and a
    caller that inferred contribution from a non-zero amount would erase exactly
    the distinction the record exists to make.

    ⚠ **NO CURRENCY TRAVELS ON A ROW**, matching every money figure the margin
    composition already carries and for the same reason: a tenant has exactly
    one currency (CUR-1). The per-currency answer exists and is the
    supplied-revenue read's own totals, which is the surface to consult when the
    question is what was supplied rather than what the margin is.
    """
    from apps.subscriptions.economics.models import TenantSuppliedRevenue
    from apps.subscriptions.economics.revenue import (
        RevenueService, SuppliedRevenueService)
    from django.db.models import Q

    if basis not in REVENUE_BASIS_VALUES:
        raise ValueError(f"{basis!r} is not a declared revenue basis")
    windows = [(start, end) for start, end in windows]
    if not windows:
        return []
    span_opens = min(start for start, _ in windows)
    span_closes = max(end for _, end in windows)

    # The same database narrowing `SuppliedRevenueService.in_window` uses, over
    # the whole span rather than one window, with the per-basis rule then
    # applied in Python exactly as that helper applies it — so the two cannot
    # drift apart and this one never re-states the attribution rule.
    supplied = TenantSuppliedRevenue.objects.filter(
        Q(tenant_id=tenant_id, period_start__lt=span_closes),
        Q(period_end__isnull=True) | Q(period_end__gt=span_opens))
    subscriptions = RevenueService.accruing(tenant_id)
    if customer_ids is not None:
        wanted = {str(customer_id) for customer_id in customer_ids}
        supplied = supplied.filter(customer_id__in=list(wanted))
        subscriptions = subscriptions.filter(customer_id__in=list(wanted))
    supplied = list(supplied.order_by("period_start", "source_reference"))
    subscriptions = list(subscriptions.order_by("created_at"))

    rows = []
    for start, end in windows:
        for record in supplied:
            if not SuppliedRevenueService.contributes(record, start, end, basis):
                continue
            rows.append(_contribution(
                start, end, record.customer_id, REVENUE_SOURCE_TENANT_SUPPLIED,
                SuppliedRevenueService.attributed_micros(
                    record, start, end, basis)))
        for subscription in subscriptions:
            accrued = RevenueService.nominal_for_window(subscription, start, end)
            if not accrued:
                # A NOMINAL OF NOTHING IS SILENCE RATHER THAN A STATED ZERO —
                # the opposite of the supplied record above, where somebody
                # wrote the number down. Emitting it would put a row against
                # every customer in every bucket of every query.
                #
                # ⚠ IT DOES NOT MEAN THE WINDOW MISSED THE SUBSCRIPTION'S OWN
                # PERIOD. The accrual is NOMINAL: it reads the amount and the
                # interval and never the subscription's dates, so an accruing
                # subscription contributes to every window it is asked about.
                # That is the behaviour the margin surfaces this query replaces
                # have always had, and matching it is what makes their totals
                # comparable — it is not a rule this function invented, and
                # nothing here is the place to change it.
                continue
            rows.append(_contribution(
                start, end, subscription.customer_id,
                REVENUE_SOURCE_SUBSCRIPTION, accrued))
    return rows


def _contribution(window_start, window_end, customer_id, source, amount_micros):
    """One row of :func:`revenue_contributions`, built in one place.

    ⚠ **THE ROW CARRIES WHAT IT CAN BE ATTRIBUTED AT, rather than leaving the
    reader to know.** The query that composes these is in another product and
    may not import this one, so a constant on this side and a matching constant
    on that side would be two statements of one rule with nothing holding them
    together. Travelling on the row, it is stated once and read where it is
    used.
    """
    return {"window_start": window_start, "window_end": window_end,
            "customer_id": str(customer_id), "source": source,
            "amount_micros": amount_micros,
            "attributable_axes": REVENUE_ATTRIBUTABLE_AXES,
            "finest_bucket": REVENUE_FINEST_BUCKET}


def get_customer_subscription(tenant_id, customer_id):
    """Returns latest StripeSubscription or None."""
    from apps.subscriptions.models import StripeSubscription

    return StripeSubscription.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
    ).order_by("-created_at").first()
