from decimal import Decimal, ROUND_HALF_UP

from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
from apps.subscriptions.economics.revenue import (
    RevenueService, SuppliedRevenueService)
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY
from core.vocabulary import REVENUE_BASIS_RECOGNISED

#: THE BASIS EVERY MARGIN FIGURE HERE IS STATED UNDER (#496).
#:
#: ⚠ **`recognised`, NOT THE `recorded` DEFAULT, AND THE REASON IS THAT A
#: MARGIN IS TAKEN OVER A WINDOW THE CALLER CHOOSES.** These surfaces answer
#: arbitrary windows — `_window()` defaults to month-to-DATE, and a report
#: window may be any span up to a year — and `recorded` lands each supplied
#: amount whole on the day its record opens. On the third of June that would
#: put a whole month's revenue against three days of cost and call the result
#: a margin: a flattering figure, which is the direction this codebase already
#: refuses to be wrong in (#328's floors and ceilings are the same argument
#: about the cost half).
#:
#: **AND IT IS NOT THE UNLABELLED PRORATION THE PROFILE WAS RETIRED FOR.** The
#: retired accrual divided one amount by day because it had no other choice and
#: said nothing about having done it. Here the division happens only where the
#: record's OWN `recognition_method` says it should: an `on_receipt` record
#: lands whole under this basis too, because that is what its method means.
#: UBB is obeying a label the tenant chose rather than inventing a boundary.
#:
#: ⚠ **WHAT THESE SURFACES DO NOT DO IS PUBLISH THE BASIS**, and that is a real
#: limit rather than an oversight: none of the five margin schemas ever carried
#: a basis field for any of its figures, and adding one to routes the collapse
#: was about to delete would have been contract churn. #501 then deleted them;
#: what still reads this constant — the business tree and the alerting record
#: — publishes no basis either. The surfaces where a caller CHOOSES a basis and
#: is told which one it got are the supplied-revenue read (#495) and the one
#: economic query that replaced those five (slice 7 §5). `test_economics.py`
#: pins the choice so it cannot drift silently.
MARGIN_REVENUE_BASIS = REVENUE_BASIS_RECOGNISED


def total_revenue_micros(subscription_revenue, supplied_revenue, usage_revenue):
    """THE ONE PLACE THAT KNOWS HOW MANY SOURCES A REVENUE TOTAL HAS (#496).

    Public, and public for a reason: the margin module's tenant-wide summary
    and its per-customer list each build a total of their own from figures they
    have already accumulated, and before this they each re-derived the sum. A
    third source then took four edits in four places to add, and the fourth was
    found by a review rather than by a gate. Adding a fourth source is now one
    edit here.

    ⚠ **THE SOURCES STAY SEPARATE EVERYWHERE ELSE AND MEET ONLY HERE.** Summing
    a tenant-supplied figure into the Stripe subscription argument on the way
    in would put the two back in one number one layer earlier, which is the
    defect this slice exists to end rather than a shortcut around it.

    ⚠ **A RESIDUAL #537 DID NOT REACH: THIS STILL ADDS THE SUPPLIED FIGURE TO
    THE BILLED USAGE.** The one economic query makes a supplied figure the whole
    revenue for the customer and period it covers and supersedes the priced
    usage there; this alerting total, which decides `is_unprofitable`, sums the
    three sources as it always did. The ruling was about the query, so a tenant
    that prices its usage AND supplies its invoiced revenue is alerted on a
    total the economic query would not state. Unowned; named here so the next
    reader of this sum finds it.
    """
    return subscription_revenue + supplied_revenue + usage_revenue


def _compose(subscription_revenue, supplied_revenue, usage_billed, provider_cost):
    """The three revenue sources added up, and the margin that falls out.

    ⚠ **THE BILLED USAGE IS REVENUE FOR EVERY TENANT, AND THE BRANCH THAT USED
    TO DECIDE OTHERWISE IS GONE** (#497, slice 7 §9). A customer-level setting
    stood here, resolved from the tenant's billing mode wherever it was blank,
    and struck the usage out of the revenue for anyone UBB does not invoice.
    That is the inversion #141 §1.1 forbids: who sends the invoice is not who
    earned the money, and a tenant that meters with UBB and bills elsewhere has
    its prices resolved by the same resolver as anybody, *because its own
    margin reporting is what they are resolved for*
    (`apps/metering/pricing/applicability.py`).

    **The figure is therefore only as complete as the postings are**, which is
    the honest form of the answer the branch was faking. Usage a tenant has
    declared no price for resolves `unknown`, contributes nothing, and travels
    with `unpriced_event_count` saying the total is a floor; work that was
    never going to carry customer revenue is `not_applicable` and contributes
    nothing either, with no caveat, because nothing is missing from it. None of
    that is a fact about a billing mode, and none of it is decided here.
    """
    usage_revenue = usage_billed
    total_revenue = total_revenue_micros(
        subscription_revenue, supplied_revenue, usage_revenue)
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
        costs = get_customer_cost_totals(tenant_id, customer_id, start_date, end_date)
        subscription_revenue = RevenueService.accrued_subscription_revenue(
            tenant_id, customer_id, start_date, end_date)
        supplied_revenue = SuppliedRevenueService.attributed_total(
            tenant_id, customer_id, start_date, end_date, MARGIN_REVENUE_BASIS)
        total_revenue, usage_revenue, margin, pct = _compose(
            subscription_revenue, supplied_revenue, costs["billed_cost_micros"],
            costs["provider_cost_micros"])
        return {
            "customer_id": str(customer_id),
            "subscription_revenue_micros": subscription_revenue,
            "supplied_revenue_micros": supplied_revenue,
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
        keys = ["subscription_revenue_micros", "supplied_revenue_micros",
                "usage_revenue_micros", "provider_cost_micros",
                UNRESOLVED_EVENT_COUNT_KEY, UNPRICED_EVENT_COUNT_KEY,
                "total_revenue_micros", "gross_margin_micros", "event_count"]
        totals = {k: 0 for k in keys}
        for d in per_seat:
            for k in keys:
                totals[k] += d.get(k, 0) or 0
        business_sub = RevenueService.accrued_subscription_revenue(
            tenant_id, business.id, start_date, end_date)
        # The business's OWN revenue, on top of its seats' — both sources of
        # it, each staying in its own column on the way through (#496). A
        # business billed outside UBB supplies revenue against the business
        # customer, exactly as a seat does against a seat.
        business_supplied = SuppliedRevenueService.attributed_total(
            tenant_id, business.id, start_date, end_date, MARGIN_REVENUE_BASIS)
        totals["subscription_revenue_micros"] += business_sub
        totals["supplied_revenue_micros"] += business_supplied
        totals["total_revenue_micros"] += business_sub + business_supplied
        totals["gross_margin_micros"] += business_sub + business_supplied
        return {"business_id": str(business.id), "external_id": business.external_id,
                "totals": totals, "seats": per_seat}

    @staticmethod
    def snapshot_customer(tenant_id, customer_id, period_start, period_end) -> CustomerEconomics:
        """Monthly snapshot from the accumulator + full-month revenue. Persists CustomerEconomics."""
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
        subscription_revenue = RevenueService.accrued_subscription_revenue(
            tenant_id, customer_id, period_start, period_end)
        supplied_revenue = SuppliedRevenueService.attributed_total(
            tenant_id, customer_id, period_start, period_end, MARGIN_REVENUE_BASIS)
        total_revenue, usage_revenue, margin, pct = _compose(
            subscription_revenue, supplied_revenue, usage_billed, provider_cost)
        econ, _ = CustomerEconomics.objects.update_or_create(
            tenant_id=tenant_id, customer_id=customer_id, period_start=period_start,
            defaults={
                "period_end": period_end,
                "subscription_revenue_micros": subscription_revenue,
                "supplied_revenue_micros": supplied_revenue,
                "usage_billed_micros": usage_billed,
                "provider_cost_micros": provider_cost,
                UNRESOLVED_EVENT_COUNT_KEY: unresolved,
                UNPRICED_EVENT_COUNT_KEY: unpriced,
                "total_revenue_micros": total_revenue,
                "gross_margin_micros": margin,
                "margin_percentage": pct,
            })
        return econ

    @staticmethod
    def snapshot_all(tenant_id, period_start, period_end):
        """Snapshot every customer with cost or revenue activity this period.

        ⚠ **THE REVENUE HALF OF THAT SENTENCE NOW ASKS ABOUT THE PERIOD, WHICH
        THE RECURRING PROFILE COULD NOT** (#496). The profile had no periods,
        so the only question that could be asked of it was *does this customer
        have one at all* — and every customer who had ever had one was
        snapshotted for every period afterwards, including periods it said
        nothing about. Per-period records answer the question that was actually
        meant, and a customer with neither cost nor supplied revenue this
        period is one the alerting record has nothing to evaluate about.
        """
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        ids = set(CustomerCostAccumulator.objects.filter(
            tenant_id=tenant_id, period_start=period_start).values_list("customer_id", flat=True))
        ids |= SuppliedRevenueService.customer_ids_with_revenue_in(
            tenant_id, period_start, period_end, MARGIN_REVENUE_BASIS)
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
        """Set is_unprofitable + emit margin webhooks, at most once per period (transition-safe).

        ⚠ **EVERY FIGURE UNDER BOTH ALARMS IS READ THROUGH `alerting`, WHICH IS
        WHAT RE-SOURCES THEM** (#502, slice 7 §8). The record these come off is
        the margin snapshot DEMOTED: no reporting surface may take a margin
        figure from it, because a stored figure is a cache of facts that move
        after a period closes. What travels on these two payloads is a fact
        about an ALARM — the number the flag was raised on, which the tenant is
        entitled to be told exactly as it stood — and reading it through the
        alerting record's own door is what keeps the two kinds of read
        distinguishable now that only one of them is allowed.
        """
        from decimal import Decimal
        from django.db import transaction
        from apps.platform.events.outbox import write_event
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.schemas import CustomerUnprofitable, ProviderCostSpike
        from apps.subscriptions.economics import alerting

        cfg = MarginService._threshold(econ.tenant_id, econ.customer_id)
        min_pct = Decimal(cfg.min_margin_pct) if cfg else Decimal("0")
        spike_pct = Decimal(cfg.provider_cost_spike_pct) if cfg else Decimal("25")
        consecutive = cfg.consecutive_periods if cfg else 1

        this_period = alerting.state_of(econ)
        # This period's prior flag (from the last snapshot of THIS period); emit only on transition.
        prev_flag = this_period["is_unprofitable"]
        recent = alerting.look_back(
            econ.tenant_id, econ.customer_id, econ.period_start,
            periods=consecutive)
        below = len(recent) >= consecutive and all(
            state["margin_pct"] < min_pct for state in recent)

        if below != prev_flag:
            econ.is_unprofitable = below
            econ.save(update_fields=["is_unprofitable", "updated_at"])
        if below and not prev_flag:
            with transaction.atomic():
                write_event(CustomerUnprofitable(
                    tenant_id=str(econ.tenant_id),
                    customer_id=this_period["customer_id"],
                    period_start=this_period["period_start"].isoformat(),
                    gross_margin_micros=this_period["gross_margin_micros"],
                    margin_pct=float(this_period["margin_pct"]),
                    threshold_pct=float(min_pct)))

        prev = alerting.period_before(
            econ.tenant_id, econ.customer_id, econ.period_start)
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
        if (prev and prev["provider_cost_micros"] > 0
                and not prev[UNRESOLVED_EVENT_COUNT_KEY]):
            rise = (Decimal(this_period["provider_cost_micros"]
                            - prev["provider_cost_micros"])
                    / Decimal(prev["provider_cost_micros"]) * 100)
            if rise >= spike_pct:
                already = OutboxEvent.objects.filter(
                    event_type=ProviderCostSpike.EVENT_TYPE, tenant_id=econ.tenant_id,
                    payload__customer_id=this_period["customer_id"],
                    payload__period_start=this_period["period_start"].isoformat()
                ).exists()
                if not already:
                    with transaction.atomic():
                        write_event(ProviderCostSpike(
                            tenant_id=str(econ.tenant_id),
                            customer_id=this_period["customer_id"],
                            period_start=this_period["period_start"].isoformat(),
                            prev_provider_cost_micros=prev["provider_cost_micros"],
                            current_provider_cost_micros=this_period["provider_cost_micros"],
                            unresolved_event_count=this_period[UNRESOLVED_EVENT_COUNT_KEY],
                            prev_margin_pct=float(prev["margin_pct"]),
                            current_margin_pct=float(this_period["margin_pct"])))
