from decimal import Decimal, ROUND_HALF_UP

from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
from apps.subscriptions.economics.revenue import RevenueService
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY


def _compose(subscription_revenue, usage_billed, provider_cost, revenue_mode):
    usage_revenue = usage_billed if revenue_mode == "billed" else 0
    total_revenue = subscription_revenue + usage_revenue
    margin = total_revenue - provider_cost
    pct = (Decimal(margin) / Decimal(total_revenue) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP) if total_revenue > 0 else Decimal("0")
    return total_revenue, usage_revenue, margin, pct


class MarginService:
    @staticmethod
    def compute_live(tenant_id, customer_id, start_date, end_date) -> dict:
        """Live margin for any window from Posting + revenue. No persistence.

        The margin CARRIES the cost total's completeness rather than growing one
        of its own (#328): subtracting a floor from a revenue figure produces a
        ceiling on the margin, and there is one fact underneath both — which
        postings the cost excluded. A derived figure that minted a second
        counter would be counting the same events twice.
        """
        from apps.metering.queries import get_customer_cost_totals
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        costs = get_customer_cost_totals(tenant_id, customer_id, start_date, end_date)
        tenant = Tenant.objects.get(id=tenant_id)
        customer = Customer.objects.get(id=customer_id)
        mode = RevenueService.resolve_revenue_mode(tenant, customer)
        subscription_revenue = RevenueService.accrued_subscription_revenue(
            tenant_id, customer_id, start_date, end_date)
        total_revenue, usage_revenue, margin, pct = _compose(
            subscription_revenue, costs["billed_cost_micros"], costs["provider_cost_micros"], mode)
        return {
            "customer_id": str(customer_id),
            "revenue_mode": mode,
            "subscription_revenue_micros": subscription_revenue,
            "usage_billed_micros": costs["billed_cost_micros"],
            "usage_revenue_micros": usage_revenue,
            "provider_cost_micros": costs["provider_cost_micros"],
            UNRESOLVED_EVENT_COUNT_KEY: costs[UNRESOLVED_EVENT_COUNT_KEY],
            UNPRICED_EVENT_COUNT_KEY: costs[UNPRICED_EVENT_COUNT_KEY],
            "total_revenue_micros": total_revenue,
            "gross_margin_micros": margin,
            "margin_percentage": float(pct),
            "event_count": costs["event_count"],
        }

    @staticmethod
    def compute_business(tenant_id, business, start_date, end_date) -> dict:
        seats = list(business.seats.all())
        per_seat = [MarginService.compute_live(tenant_id, s.id, start_date, end_date) for s in seats]
        # The rollup's completeness is its seats' completeness added up (#328):
        # a business total that excluded one seat's cost has excluded it, and
        # summing the counts is the same arithmetic as summing the costs.
        keys = ["subscription_revenue_micros", "usage_revenue_micros", "provider_cost_micros",
                UNRESOLVED_EVENT_COUNT_KEY, UNPRICED_EVENT_COUNT_KEY,
                "total_revenue_micros", "gross_margin_micros", "event_count"]
        totals = {k: 0 for k in keys}
        for d in per_seat:
            for k in keys:
                totals[k] += d.get(k, 0) or 0
        business_sub = RevenueService.accrued_subscription_revenue(
            tenant_id, business.id, start_date, end_date)
        totals["subscription_revenue_micros"] += business_sub
        totals["total_revenue_micros"] += business_sub
        totals["gross_margin_micros"] += business_sub
        return {"business_id": str(business.id), "external_id": business.external_id,
                "totals": totals, "seats": per_seat}

    @staticmethod
    def snapshot_customer(tenant_id, customer_id, period_start, period_end) -> CustomerEconomics:
        """Monthly snapshot from the accumulator + full-month revenue. Persists CustomerEconomics."""
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        acc = CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start).first()
        provider_cost = acc.total_provider_cost_micros if acc else 0
        # The snapshot freezes what the accumulator excluded ALONGSIDE what it
        # totalled (#328). Both come from the same row or neither does: a
        # customer with no accumulator has no cost and nothing left out, which
        # is a complete answer rather than an unknown one.
        unresolved = acc.unresolved_event_count if acc else 0
        usage_billed = acc.total_billed_cost_micros if acc else 0
        # And what the BILLED total excluded (#351), frozen on the same terms.
        # Two counts because they bound the derived figures in opposite
        # directions: an excluded cost makes the margin below a ceiling, an
        # excluded price makes it a floor, and a snapshot can be both.
        unpriced = acc.unpriced_event_count if acc else 0
        tenant = Tenant.objects.get(id=tenant_id)
        customer = Customer.objects.get(id=customer_id)
        mode = RevenueService.resolve_revenue_mode(tenant, customer)
        subscription_revenue = RevenueService.accrued_subscription_revenue(
            tenant_id, customer_id, period_start, period_end)
        total_revenue, usage_revenue, margin, pct = _compose(
            subscription_revenue, usage_billed, provider_cost, mode)
        econ, _ = CustomerEconomics.objects.update_or_create(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start,
            defaults={
                "period_end": period_end,
                "subscription_revenue_micros": subscription_revenue,
                "usage_billed_micros": usage_billed,
                "provider_cost_micros": provider_cost,
                UNRESOLVED_EVENT_COUNT_KEY: unresolved,
                UNPRICED_EVENT_COUNT_KEY: unpriced,
                "total_revenue_micros": total_revenue,
                "revenue_mode": mode,
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
        from apps.platform.events.schemas import CustomerUnprofitable, ProviderCostSpike
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
                write_event(CustomerUnprofitable(
                    tenant_id=str(econ.tenant_id), customer_id=str(econ.customer_id),
                    period_start=econ.period_start.isoformat(),
                    gross_margin_micros=econ.gross_margin_micros,
                    margin_pct=float(econ.margin_percentage), threshold_pct=float(min_pct)))

        prev = (CustomerEconomics.objects.filter(
            tenant_id=econ.tenant_id, customer_id=econ.customer_id,
            period_start__lt=econ.period_start).order_by("-period_start").first())
        # AN UNRESOLVED PREVIOUS COST IS NOT A SPIKE OF ANY SIZE (#328).
        #
        # The comparison is a RATIO and the previous period is its denominator.
        # A previous total that excluded costs is too small, so every rise
        # computed against it is too big — and the failure direction is a false
        # alarm about somebody's money, which is worse than silence. There is no
        # substitute figure to divide by either: the true previous cost is
        # unknown, not zero, and answering "no spike" is the only claim the data
        # supports. The window still says it is incomplete — the count is on the
        # snapshot both readings come from, so nothing is hidden by declining to
        # compare.
        #
        # The CURRENT period being partial is the opposite case and still fires:
        # a floor understates the rise, so a threshold crossed on one has really
        # been crossed. What the consumer gets told is that the number under the
        # alarm is a lower bound — see the count on the payload below.
        if prev and prev.provider_cost_micros > 0 and not prev.unresolved_event_count:
            rise = (Decimal(econ.provider_cost_micros - prev.provider_cost_micros)
                    / Decimal(prev.provider_cost_micros) * 100)
            if rise >= spike_pct:
                already = OutboxEvent.objects.filter(
                    event_type="provider.cost_spike", tenant_id=econ.tenant_id,
                    payload__customer_id=str(econ.customer_id),
                    payload__period_start=econ.period_start.isoformat()).exists()
                if not already:
                    with transaction.atomic():
                        write_event(ProviderCostSpike(
                            tenant_id=str(econ.tenant_id), customer_id=str(econ.customer_id),
                            period_start=econ.period_start.isoformat(),
                            prev_provider_cost_micros=prev.provider_cost_micros,
                            current_provider_cost_micros=econ.provider_cost_micros,
                            unresolved_event_count=econ.unresolved_event_count,
                            prev_margin_pct=float(prev.margin_percentage),
                            current_margin_pct=float(econ.margin_percentage)))
