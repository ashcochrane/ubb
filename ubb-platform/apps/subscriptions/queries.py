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
    """Returns aggregated economics for all customers."""
    from apps.subscriptions.economics.models import CustomerEconomics
    from django.db.models import Sum

    qs = CustomerEconomics.objects.filter(
        tenant_id=tenant_id,
        period_start__gte=period_start,
        period_end__lte=period_end,
    )
    totals = qs.aggregate(
        total_revenue=Sum("subscription_revenue_micros"),
        total_cost=Sum("usage_cost_micros"),
        total_margin=Sum("gross_margin_micros"),
    )
    return {
        "total_revenue_micros": totals["total_revenue"] or 0,
        "total_cost_micros": totals["total_cost"] or 0,
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
