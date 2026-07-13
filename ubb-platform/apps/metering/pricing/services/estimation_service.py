"""Conservative accept-time cost estimation for async ingestion.

Mirrors PricingService.price's card-resolution logic but is read-only: it
never advances a tier counter, never charges a wallet, and always returns a
usable number so the ingest endpoint can hold funds before the real pricing
run executes. The one invariant that matters is that the estimate never
knowingly under-holds relative to what PricingService.price will eventually
charge — see the tiered branch below. Unpriceable is raised only where the
real pricer would raise PricingError (strict cost coverage), so the endpoint
can route the item down the sync path to surface the real error.
"""
from collections import namedtuple

from apps.metering.pricing.models import TIERED_PRICING_MODELS
from apps.metering.pricing.services.card_cache import CardCache, TierMirror

Estimate = namedtuple("Estimate", "micros exact")


class Unpriceable(Exception):
    """Estimation cannot proceed safely — route this item down the sync path."""


class EstimationService:
    @staticmethod
    def estimate(tenant, customer, *, event_type, provider, usage_metrics,
                 tags, currency, caller_billed, caller_provider_cost, units, now):
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
                # never-under-hold: the mirror lags the TRUE ladder position
                # downward only (pending settles raise it), so anchor at the
                # mirror and at 0...
                est = max(card.compute_marginal(prior, units_val),
                          card.compute_marginal(0, units_val))
                # ...but on INCREASING-rate ladders the marginal grows with
                # prior, so those anchors under-hold. graduated: guard with
                # the spec's "estimate at the max applicable rate" over the
                # tiers not fully below the mirror. (package cards have
                # tiers == [] and are covered by the marginal(0) anchor.)
                if card.tiers:
                    remaining = [t for t in card.tiers
                                 if t["up_to"] is None or t["up_to"] > prior]
                    if remaining:
                        # Ceiling division (not half-up): pricing ALL units at
                        # a single tier's rate must dominate the real marginal
                        # even when the true split rounds EACH band up
                        # separately (half-up on the single-rate estimate can
                        # itself round DOWN by just under one unit_quantity's
                        # worth, which — stacked against two bands each
                        # rounding up — could under-hold by a few micros).
                        # ceil() never rounds down, closing that gap.
                        worst_rate = max(
                            (units_val * t["rate_per_unit_micros"]
                             + t.get("unit_quantity", 1_000_000) - 1)
                            // t.get("unit_quantity", 1_000_000)
                            for t in remaining)
                        est = max(est, worst_rate + sum(
                            t.get("flat_micros", 0) for t in remaining))
                total += est
                exact = False
            else:
                total += card.compute(units_val)
        if matched:
            return Estimate(total, exact)
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
