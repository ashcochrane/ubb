from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice


class EconomicsService:
    @staticmethod
    def calculate_customer_economics(tenant_id, customer_id, period_start, period_end):
        """Calculate unit economics for a single customer in a period.

        Revenue: from synced Stripe invoices (SubscriptionInvoice)
        Cost: from event-bus accumulated usage data (CustomerCostAccumulator)
        """
        # Revenue from synced Stripe invoices
        revenue = SubscriptionInvoice.objects.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            period_start__gte=period_start,
            period_end__lte=period_end,
        ).aggregate(total=Sum("amount_paid_micros"))["total"] or 0

        # Usage cost from accumulator (populated by event bus handler)
        cost = CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            period_start__gte=period_start,
            period_end__lte=period_end,
        ).aggregate(total=Sum("total_cost_micros"))["total"] or 0

        margin = revenue - cost
        if revenue > 0:
            margin_pct = (Decimal(margin) / Decimal(revenue) * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            margin_pct = Decimal("0")

        economics, _ = CustomerEconomics.objects.update_or_create(
            tenant_id=tenant_id,
            customer_id=customer_id,
            period_start=period_start,
            defaults={
                "period_end": period_end,
                "subscription_revenue_micros": revenue,
                "usage_cost_micros": cost,
                "gross_margin_micros": margin,
                "margin_percentage": margin_pct,
            },
        )
        return economics

    @staticmethod
    def calculate_all_economics(tenant_id, period_start, period_end):
        """Calculate unit economics for all customers with active subscriptions."""
        customer_ids = StripeSubscription.objects.filter(
            tenant_id=tenant_id,
            status="active",
        ).values_list("customer_id", flat=True).distinct()

        results = []
        for customer_id in customer_ids:
            result = EconomicsService.calculate_customer_economics(
                tenant_id, customer_id, period_start, period_end,
            )
            results.append(result)
        return results
