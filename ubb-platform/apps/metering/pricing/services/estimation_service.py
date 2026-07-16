"""Accept-time cost estimation for async ingestion.

Mirrors PricingService.price's card-resolution logic but is read-only: it
never charges a wallet, and always returns a usable number so the ingest
endpoint can hold funds before the real pricing run executes. With only
per_unit/flat pricing models (ADR-0003 deleted tiered pricing), every
estimate equals what PricingService.price will charge by construction —
the only remaining accept-vs-settle difference is rate-card config drift
between the two instants. Unpriceable is raised only where the real pricer
would raise PricingError (strict cost coverage), so the endpoint can route
the item down the sync path to surface the real error.

``Estimate.exact`` is kept as belt-and-braces provenance: it records that
the estimate was exact at accept time, and stays load-bearing if a future
pricing model reintroduces inexact estimates.
"""
from collections import namedtuple

from apps.metering.pricing.services.card_cache import CardCache

Estimate = namedtuple("Estimate", "micros exact")


class Unpriceable(Exception):
    """Estimation cannot proceed safely — route this item down the sync path."""


class EstimationService:
    @staticmethod
    def estimate(tenant, customer, *, event_type, provider, usage_metrics,
                 tags, currency, caller_billed, caller_provider_cost, units):
        if caller_billed is not None:
            return Estimate(caller_billed, True)
        usage_metrics = usage_metrics or {}
        # Strict cost coverage mirrors the pricer's PricingError risk exactly:
        # it checks coverage BEFORE pricing, even when price cards match and
        # even when the caller supplies the aggregate cost.
        if getattr(tenant, "require_cost_card_coverage", False):
            if caller_provider_cost is None and (units or 0) > 0 and not usage_metrics:
                raise Unpriceable(
                    "strict cost coverage: units > 0 with no usage_metrics")
            uncosted = [m for m in usage_metrics
                        if CardCache.resolve(tenant, customer, "cost", provider,
                                             event_type, m, tags, currency) is None]
            if uncosted:
                raise Unpriceable(f"no cost rate card for metrics: {uncosted}")
        total, matched = 0, False
        for metric, units_val in sorted(usage_metrics.items()):
            card = CardCache.resolve(tenant, customer, "price", provider,
                                     event_type, metric, tags, currency)
            if card is None:
                continue
            matched = True
            total += card.compute(units_val)
        if matched:
            return Estimate(total, True)
        # Markup fallback mirrors PricingService exactly: billed is
        # markup(provider cost); a non-strict tenant with no matching cost
        # cards simply bills markup(0) — never a failure.
        if caller_provider_cost is not None:
            provider_cost = caller_provider_cost
        else:
            provider_cost = 0
            for metric, units_val in usage_metrics.items():
                card = CardCache.resolve(tenant, customer, "cost", provider,
                                         event_type, metric, tags, currency)
                if card is not None:
                    provider_cost += card.compute(units_val)
        from apps.metering.pricing.services.markup_cache import MarkupCache
        return Estimate(MarkupCache.apply(provider_cost, tenant=tenant,
                                          customer=customer), True)
