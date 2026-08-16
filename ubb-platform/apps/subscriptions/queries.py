"""Subscriptions Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(and the API layer) to read subscriptions data.

If subscriptions becomes a separate service, these functions
become HTTP calls. All callers remain untouched.

Consumers:
- api/v1/subscriptions_endpoints.py (future)
"""
from datetime import date


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
    from core.cost_totals import UNRESOLVED_EVENT_COUNT_KEY

    totals = qs.aggregate(
        total_subscription_revenue=Sum("subscription_revenue_micros"),
        total_usage_billed=Sum("usage_billed_micros"),
        total_provider_cost=Sum("provider_cost_micros"),
        total_unresolved=Sum("unresolved_event_count"),
        total_margin=Sum("gross_margin_micros"),
    )
    return {
        "subscription_revenue_micros": totals["total_subscription_revenue"] or 0,
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
        "total_margin_micros": totals["total_margin"] or 0,
        "customer_count": qs.count(),
    }


def get_customer_subscription(tenant_id, customer_id):
    """Returns latest StripeSubscription or None."""
    from apps.subscriptions.models import StripeSubscription

    return StripeSubscription.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
    ).order_by("-created_at").first()
