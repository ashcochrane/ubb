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

    ⚠ THIS TOTAL IS NOT A PAIR, AND THE REASON IS THAT IT CANNOT HONESTLY BE ONE
    YET (#327).

    Every other supplier-cost total in the tree now travels with the count of
    postings it excluded, because `Posting.provider_cost_micros` is nullable and
    a bare `Sum` over it silently skips the unresolved rows. **This `Sum` is not
    over that column.** `CustomerEconomics.provider_cost_micros` is a monthly
    SNAPSHOT, `NOT NULL` with a default of zero, so SQL's null-skipping cannot
    reach it — its `Sum` is `None` only when no snapshot matched, which is the
    empty sum and is exactly complete.

    What it CAN inherit is a partiality from upstream: the accumulator these
    snapshots are built from adds the posting's cost up in Python, and that
    reader is #328's, as is the snapshot recording what it excluded. Publishing
    an `unresolved_event_count` here today would mean publishing a zero nothing
    computes — a number indistinguishable from a real one, which is the defect
    this slice exists to end. So the count arrives with the fact, not before it.
    `apps/subscriptions/tests/test_queries.py` holds the column to `NOT NULL`,
    so the claim above fails rather than ages.
    """
    from apps.subscriptions.economics.models import CustomerEconomics
    from django.db.models import Sum

    qs = CustomerEconomics.objects.filter(
        tenant_id=tenant_id,
        period_start__gte=period_start,
        period_end__lte=period_end,
    )
    totals = qs.aggregate(
        total_subscription_revenue=Sum("subscription_revenue_micros"),
        total_usage_billed=Sum("usage_billed_micros"),
        total_provider_cost=Sum("provider_cost_micros"),
        total_margin=Sum("gross_margin_micros"),
    )
    return {
        "subscription_revenue_micros": totals["total_subscription_revenue"] or 0,
        "usage_billed_micros": totals["total_usage_billed"] or 0,
        "provider_cost_micros": totals["total_provider_cost"] or 0,
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
