"""The one economic query, asked on a route's behalf (#501, #561).

Two routes ask it — the tenant's `GET /metering/analytics/economics` and the end
customer's `GET /me/economics` — and both need the revenue only the
subscriptions product holds wired in beside the postings. That wiring lives here,
once, so the two routes cannot come to compose the answer two ways; each route
keeps its own request reading and its own response.
"""
from datetime import timedelta

from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE,
    ANALYTICS_MEASURE_GROSS_MARGIN,
)


def ask_the_economic_query(tenant_id, *, measures, group_by, bucket, basis,
                           window, filters):
    """The one economic query, with the revenue only subscriptions holds wired
    in — for every route that asks it (the tenant's and, since #561, the
    widget's). Answers the read contract's plain data and how many foreign-
    currency subscriptions its revenue left out.

    ⚠ THE REVENUE THIS PRODUCT DOES NOT HOLD IS READ FROM THE PRODUCT THAT
    DOES, HERE, WHICH IS THE COMPOSITION LAYER'S JOB AND NOT THE READ
    CONTRACT'S. Metering owns the postings a price was resolved on;
    subscriptions owns a tenant's Stripe accruals and the figures it supplied
    itself, and ADR-001 forbids either product reaching into the other — on a
    service split metering would not have them. So they are fetched from that
    product's own read contract and handed over as plain data, each row saying
    whose it is, which window it lands in and what it can be attributed at.
    `economics` REFUSES to answer a revenue measure without them, so this
    wiring cannot be forgotten into a margin that is short by a subscription.

    ⚠ **AND IT IS NOT FETCHED WHERE NO MEASURE WOULD USE IT**, which is two
    fewer queries on a cost-only question and, more than that, a different
    ANSWER: the money a grouping cannot place is reported as context, and
    context on a question that asked nothing about revenue is noise about a
    number the caller did not request.

    ⚠ **AND THE PERIODS A SUPPLIED FIGURE COVERS COME WITH THEM, READ FOR THE
    WHOLE WINDOW AND NOT PER BUCKET** (#537). A supplied figure is the whole
    revenue for the customer and period it covers, so the query supersedes
    the priced usage inside that period — and which period that is belongs to
    the record, not to the basis that decides where its amount lands.

    The foreign count (#564) is what this answer's revenue LEFT OUT:
    subscriptions Stripe holds in a currency UBB does not admit, counted over
    exactly the scope the revenue is fetched for, and 0 on a question that
    asked for no revenue, because such an answer left nothing out.
    """
    from apps.metering.queries import economics
    from apps.subscriptions.queries import (
        foreign_currency_subscription_count, revenue_contributions,
        supplied_revenue_covered_periods)

    revenue_wanted = bool({ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                           ANALYTICS_MEASURE_GROSS_MARGIN} & set(measures))
    supplied = {}
    foreign = 0
    if revenue_wanted:
        customer_ids = [filters.customer_id] if filters.customer_id else None
        foreign = foreign_currency_subscription_count(
            tenant_id, customer_ids=customer_ids)
        supplied["contributed_revenue"] = revenue_contributions(
            tenant_id, windows=_economic_buckets(window, bucket), basis=basis,
            customer_ids=customer_ids)
        supplied["covered_periods"] = supplied_revenue_covered_periods(
            tenant_id, opens=window.opens, closes=window.closes,
            customer_ids=customer_ids)
    answer = economics(tenant_id, measures=measures, group_by=group_by,
                       bucket=bucket, filters=filters, basis=basis,
                       as_of=window.today, **supplied)
    return answer, foreign


def _economic_buckets(window, bucket):
    """The half-open windows the contributed revenue is attributed to.

    One window per bucket the answer will have, so a figure a tenant supplied
    for a month lands in the months, days or hours of that month exactly as the
    postings beside it do — and one window for the whole period where the caller
    asked for no bucket.

    ⚠ **THE END DATE IS INCLUSIVE ON THE WIRE AND HALF-OPEN HERE**, and the
    conversion is the window's own (`core/report_windows.py`), never redone
    here; getting it wrong would drop the last day's revenue while keeping its
    cost.

    ⚠ **EVERY WINDOW IS CLAMPED TO THE PERIOD ASKED ABOUT.** A month bucket
    starting mid-month opens on the first of that month, and an unclamped window
    would attribute revenue from days the postings beside it exclude — a total
    that is right about the cost and wrong about the money, which is the exact
    disagreement the collapse exists to remove.

    An hour bucket asks for DAY windows, and the query then declines to place
    the money at all: a supplied record declares a span in whole days, so hour
    precision is not a narrower answer, it is an invented one.
    """
    start, closes = window.opens, window.closes
    if bucket is None:
        return [(start, closes)]
    windows, opens = [], (start.replace(day=1) if bucket == "month" else start)
    while opens < closes:
        if bucket == "month":
            nxt = (opens.replace(year=opens.year + 1, month=1, day=1)
                   if opens.month == 12 else opens.replace(month=opens.month + 1))
        else:
            nxt = opens + timedelta(days=1)
        windows.append((max(opens, start), min(nxt, closes)))
        opens = nxt
    return windows
