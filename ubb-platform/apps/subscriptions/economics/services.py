from decimal import Decimal, ROUND_HALF_UP

from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
from apps.subscriptions.economics.revenue import RevenueService


def _compose(subscription_revenue, usage_billed, provider_cost):
    total_revenue = subscription_revenue + usage_billed
    margin = total_revenue - provider_cost
    pct = (Decimal(margin) / Decimal(total_revenue) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP) if total_revenue > 0 else Decimal("0")
    return total_revenue, margin, pct


class MarginService:
    @staticmethod
    def compute_live(tenant_id, customer_id, start_date, end_date) -> dict:
        """Live margin for any window from UsageEvent + revenue. No persistence."""
        from apps.metering.queries import get_customer_cost_totals
        costs = get_customer_cost_totals(tenant_id, customer_id, start_date, end_date)
        subscription_revenue = RevenueService.revenue_for_window(
            tenant_id, customer_id, start_date, end_date)
        _, margin, pct = _compose(subscription_revenue, costs["billed_cost_micros"], costs["provider_cost_micros"])
        return {
            "customer_id": str(customer_id),
            "subscription_revenue_micros": subscription_revenue,
            "usage_billed_micros": costs["billed_cost_micros"],
            "provider_cost_micros": costs["provider_cost_micros"],
            "gross_margin_micros": margin,
            "margin_percentage": float(pct),
            "event_count": costs["event_count"],
        }

    @staticmethod
    def snapshot_customer(tenant_id, customer_id, period_start, period_end) -> CustomerEconomics:
        """Monthly snapshot from the accumulator + full-month revenue. Persists CustomerEconomics."""
        acc = CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start).first()
        provider_cost = acc.total_provider_cost_micros if acc else 0
        usage_billed = acc.total_billed_cost_micros if acc else 0
        subscription_revenue = RevenueService.revenue_for_window(
            tenant_id, customer_id, period_start, period_end)
        _, margin, pct = _compose(subscription_revenue, usage_billed, provider_cost)
        econ, _ = CustomerEconomics.objects.update_or_create(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start,
            defaults={
                "period_end": period_end,
                "subscription_revenue_micros": subscription_revenue,
                "usage_billed_micros": usage_billed,
                "provider_cost_micros": provider_cost,
                "gross_margin_micros": margin,
                "margin_percentage": pct,
            })
        return econ

    @staticmethod
    def snapshot_all(tenant_id, period_start, period_end):
        """Snapshot every customer with cost or revenue activity this period."""
        from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerRevenueProfile
        ids = set(CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id, period_start=period_start).values_list("customer_id", flat=True))
        ids |= set(CustomerRevenueProfile.objects.filter(
            tenant_id=tenant_id).values_list("customer_id", flat=True))
        return [MarginService.snapshot_customer(tenant_id, cid, period_start, period_end) for cid in ids]
