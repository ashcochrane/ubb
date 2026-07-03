"""Conservative accept-time cost estimation for async ingestion.

Mirrors PricingService.price's card-resolution logic but is read-only: it
never advances a tier counter, never charges a wallet, and always returns a
usable number so the ingest endpoint can hold funds before the real pricing
run executes. The one invariant that matters is that the estimate never
knowingly under-holds relative to what PricingService.price will eventually
charge — see the tiered branch below.
"""
from collections import namedtuple

from apps.metering.pricing.models import TIERED_PRICING_MODELS
from apps.metering.pricing.services.card_cache import CardCache, TierMirror

Estimate = namedtuple("Estimate", "micros exact")


class Unpriceable(Exception):
    """No cached card, no caller cost — route this item down the sync path."""


class EstimationService:
    @staticmethod
    def estimate(tenant, customer, *, event_type, provider, usage_metrics,
                 tags, currency, caller_billed, caller_provider_cost, units, now):
        if caller_billed is not None:
            return Estimate(int(caller_billed), True)
        usage_metrics = usage_metrics or {}
        total, matched, exact = 0, False, True
        for metric, units_val in sorted(usage_metrics.items()):
            card = CardCache.resolve(tenant, customer, "price", provider,
                                     event_type, metric, tags, currency)
            if card is None:
                continue
            matched = True
            if card.pricing_model in TIERED_PRICING_MODELS:
                prior = TierMirror.read(tenant.id, customer.id,
                                        str(card.lineage_id), now)
                # never-under-hold: max over the two anchor positions
                total += max(card.compute_marginal(prior, units_val),
                             card.compute_marginal(0, units_val))
                exact = False
            else:
                total += card.compute(units_val)
        if matched:
            return Estimate(total, exact)
        # markup fallback mirrors PricingService: needs a provider cost
        provider_cost, cost_matched = 0, False
        if caller_provider_cost is not None:
            provider_cost, cost_matched = int(caller_provider_cost), True
        else:
            for metric, units_val in usage_metrics.items():
                card = CardCache.resolve(tenant, customer, "cost", provider,
                                         event_type, metric, tags, currency)
                if card is not None:
                    provider_cost += card.compute(units_val)
                    cost_matched = True
        if not cost_matched and (usage_metrics or (units or 0) > 0):
            raise Unpriceable(f"no price/cost card for event_type={event_type!r}")
        from apps.metering.pricing.services.markup_service import MarkupService
        return Estimate(MarkupService.apply(provider_cost, tenant=tenant,
                                            customer=customer), True)
