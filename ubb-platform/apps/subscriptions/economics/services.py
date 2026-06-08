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
        results = []
        for cid in ids:
            econ = MarginService.snapshot_customer(tenant_id, cid, period_start, period_end)
            MarginService.evaluate_and_emit(econ)
            results.append(econ)
        return results

    @staticmethod
    def _threshold(tenant_id, customer_id):
        from apps.subscriptions.economics.models import MarginThresholdConfig
        cfg = MarginThresholdConfig.objects.filter(tenant_id=tenant_id, customer_id=customer_id).first()
        if cfg:
            return cfg
        return MarginThresholdConfig.objects.filter(tenant_id=tenant_id, customer__isnull=True).first()

    @staticmethod
    def evaluate_and_emit(econ):
        """Set is_unprofitable + emit margin webhooks, at most once per period (transition-safe)."""
        from decimal import Decimal
        from django.db import transaction
        from apps.platform.events.outbox import write_event
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.schemas import MarginCustomerUnprofitable, MarginProviderCostSpike
        from apps.subscriptions.economics.models import CustomerEconomics

        cfg = MarginService._threshold(econ.tenant_id, econ.customer_id)
        min_pct = Decimal(cfg.min_margin_pct) if cfg else Decimal("0")
        spike_pct = Decimal(cfg.provider_cost_spike_pct) if cfg else Decimal("25")
        consecutive = cfg.consecutive_periods if cfg else 1

        # This period's prior flag (from the last snapshot of THIS period); emit only on transition.
        prev_flag = econ.is_unprofitable
        recent = list(CustomerEconomics.objects.filter(
            tenant_id=econ.tenant_id, customer_id=econ.customer_id,
            period_start__lte=econ.period_start).order_by("-period_start")[:consecutive])
        below = len(recent) >= consecutive and all(e.margin_percentage < min_pct for e in recent)

        if below != prev_flag:
            econ.is_unprofitable = below
            econ.save(update_fields=["is_unprofitable", "updated_at"])
        if below and not prev_flag:
            with transaction.atomic():
                write_event(MarginCustomerUnprofitable(
                    tenant_id=str(econ.tenant_id), customer_id=str(econ.customer_id),
                    period_start=econ.period_start.isoformat(),
                    gross_margin_micros=econ.gross_margin_micros,
                    margin_pct=float(econ.margin_percentage), threshold_pct=float(min_pct)))

        prev = (CustomerEconomics.objects.filter(
            tenant_id=econ.tenant_id, customer_id=econ.customer_id,
            period_start__lt=econ.period_start).order_by("-period_start").first())
        if prev and prev.provider_cost_micros > 0:
            rise = (Decimal(econ.provider_cost_micros - prev.provider_cost_micros)
                    / Decimal(prev.provider_cost_micros) * 100)
            if rise >= spike_pct:
                already = OutboxEvent.objects.filter(
                    event_type="margin.provider_cost_spike", tenant_id=econ.tenant_id,
                    payload__customer_id=str(econ.customer_id),
                    payload__period_start=econ.period_start.isoformat()).exists()
                if not already:
                    with transaction.atomic():
                        write_event(MarginProviderCostSpike(
                            tenant_id=str(econ.tenant_id), customer_id=str(econ.customer_id),
                            period_start=econ.period_start.isoformat(),
                            prev_provider_cost_micros=prev.provider_cost_micros,
                            current_provider_cost_micros=econ.provider_cost_micros,
                            prev_margin_pct=float(prev.margin_percentage),
                            current_margin_pct=float(econ.margin_percentage)))
