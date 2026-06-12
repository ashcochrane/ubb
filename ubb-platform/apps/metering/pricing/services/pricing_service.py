from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import RateCard, TIERED_PRICING_MODELS
from apps.metering.pricing.services.tier_counter_service import (
    TierCounterService, month_bounds,
)

PRICING_ENGINE_VERSION = "2.1.0"


class PricingError(Exception):
    pass


def _event_bands(card, prior, new_total):
    """Bands of T(q) this event actually touched, decomposed per band as
    cumulative differences so the band micros sum EXACTLY to the event's
    marginal amount (flat_micros appears on the band the event first enters)."""
    if new_total <= prior:
        return []
    if card.pricing_model == "package":
        return [{
            "up_to": None,
            "units_in_band": new_total - prior,
            "rate_per_unit_micros": card.rate_per_unit_micros,
            "unit_quantity": card.unit_quantity,
            "flat_micros": card.fixed_micros if prior <= 0 else 0,
            "micros": card.compute_marginal(prior, new_total - prior),
        }]
    bands, lower = [], 0
    for tier in card.tiers:
        up_to = tier["up_to"]
        rate = tier["rate_per_unit_micros"]
        unit_quantity = tier.get("unit_quantity", 1_000_000)
        flat = tier.get("flat_micros", 0)
        seg_before = max(0, (prior if up_to is None else min(prior, up_to)) - lower)
        seg_after = max(0, (new_total if up_to is None else min(new_total, up_to)) - lower)
        if seg_after > seg_before:
            entered = prior <= lower  # this event is the first past `lower`
            micros = ((flat if entered else 0)
                      + (seg_after * rate + unit_quantity // 2) // unit_quantity
                      - (seg_before * rate + unit_quantity // 2) // unit_quantity)
            bands.append({
                "up_to": up_to,
                "units_in_band": seg_after - seg_before,
                "rate_per_unit_micros": rate,
                "unit_quantity": unit_quantity,
                "flat_micros": flat if entered else 0,
                "micros": micros,
            })
        if up_to is None or new_total <= up_to:
            break
        lower = up_to
    return bands


class PricingService:
    @staticmethod
    def _dimensions_match(card_dimensions, tags):
        tags = tags or {}
        for k, v in (card_dimensions or {}).items():
            if str(tags.get(k)) != str(v):
                return False
        return True

    @staticmethod
    def _resolve_card(tenant, customer, card_type, provider, event_type, metric_name, tags, currency, as_of):
        base = list(RateCard.objects.filter(
            tenant=tenant, card_type=card_type, provider=provider or "", event_type=event_type or "",
            metric_name=metric_name, currency=currency, valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of)))
        owners = ([customer.id] if customer is not None else []) + [None]
        for owner in owners:
            cands = [c for c in base if c.customer_id == owner
                     and PricingService._dimensions_match(c.dimensions, tags)]
            if cands:
                cands.sort(key=lambda c: (len(c.dimensions or {}), c.valid_from), reverse=True)
                return cands[0]
        return None

    @staticmethod
    def price(*, tenant, customer, event_type, provider, usage_metrics, tags, currency,
              caller_provider_cost, caller_billed, units=None, as_of=None):
        as_of = as_of or timezone.now()
        usage_metrics = usage_metrics or {}
        prov = {"engine_version": PRICING_ENGINE_VERSION, "metrics": []}

        # ---- COST ----
        if caller_provider_cost is not None:
            provider_cost = caller_provider_cost
            prov["cost_source"] = "caller"
            # When the strict coverage flag is on, every metric in usage_metrics must have
            # a matching cost card even when the caller supplies the aggregate cost.
            # Without this check the caller-cost path silently bypasses the guarantee.
            if usage_metrics and getattr(tenant, "require_cost_card_coverage", False):
                uncosted = [m for m in usage_metrics
                            if PricingService._resolve_card(
                                tenant, customer, "cost", provider,
                                event_type, m, tags, currency, as_of) is None]
                if uncosted:
                    prov["uncosted_metrics"] = uncosted
                    raise PricingError(f"No cost rate card for metrics: {uncosted}")
        else:
            provider_cost = 0
            uncosted = []
            # Strict mode: units > 0 with no usage_metrics means cost is unknowable —
            # no metric name to resolve a rate card against.  Caller-supplied
            # provider_cost_micros is still accepted (cost is explicitly known).
            if (units or 0) > 0 and not usage_metrics and getattr(tenant, "require_cost_card_coverage", False):
                raise PricingError(
                    "strict cost coverage: units > 0 with no usage_metrics — no cost rate "
                    "card can match; pass usage_metrics or provider_cost_micros")
            for metric, units_val in usage_metrics.items():
                card = PricingService._resolve_card(tenant, customer, "cost", provider,
                                                    event_type, metric, tags, currency, as_of)
                if card is None:
                    uncosted.append(metric)
                    continue
                if card.pricing_model in TIERED_PRICING_MODELS:
                    # Defensive: validate_tiers forbids tiered cost cards at the
                    # API; a hand-crafted row must fail loudly, not mis-price.
                    raise PricingError(
                        f"tiered pricing_model '{card.pricing_model}' is not allowed "
                        f"on cost cards (rate card {card.id})")
                amt = card.compute(units_val)
                provider_cost += amt
                prov["metrics"].append({"metric": metric, "units": units_val, "card_type": "cost",
                    "rate_card_id": str(card.id), "pricing_model": card.pricing_model, "micros": amt})
            prov["cost_source"] = "rate_card"
            if uncosted:
                prov["uncosted_metrics"] = uncosted
                if getattr(tenant, "require_cost_card_coverage", False):
                    raise PricingError(f"No cost rate card for metrics: {uncosted}")

        # ---- PRICE ----
        if caller_billed is not None:
            billed = caller_billed
            prov["price_source"] = "caller"
        else:
            price_total, matched = 0, False
            # sorted(): deterministic counter-lock order across metrics — deadlock-free
            # when concurrent events share multiple tiered metrics.
            for metric, units_val in sorted(usage_metrics.items()):
                card = PricingService._resolve_card(tenant, customer, "price", provider,
                                                    event_type, metric, tags, currency, as_of)
                if card is None:
                    continue
                matched = True
                entry = {"metric": metric, "units": units_val, "card_type": "price",
                         "rate_card_id": str(card.id), "pricing_model": card.pricing_model}
                if card.pricing_model in TIERED_PRICING_MODELS:
                    # Incrementally exact tiered rating: advance the period
                    # ladder under a row lock, price the marginal difference.
                    prior, new_total = TierCounterService.lock_and_advance(
                        tenant, customer, card, units_val, as_of)
                    amt = card.compute_marginal(prior, units_val)
                    cumulative_before = card.compute_cumulative(prior)
                    entry["tier_breakdown"] = {
                        "prior_units": prior,
                        "units_total_after": new_total,
                        "cumulative_before_micros": cumulative_before,
                        "cumulative_after_micros": cumulative_before + amt,
                        "period_start": month_bounds(as_of)[0].isoformat(),
                        "lineage_id": str(card.lineage_id),
                        "bands": _event_bands(card, prior, new_total),
                    }
                else:
                    amt = card.compute(units_val)
                entry["micros"] = amt
                price_total += amt
                prov["metrics"].append(entry)
            if matched:
                billed = price_total
                prov["price_source"] = "rate_card"
            else:
                from apps.metering.pricing.services.markup_service import MarkupService
                billed = MarkupService.apply(provider_cost, tenant=tenant, customer=customer)
                prov["price_source"] = "markup"

        prov["provider_cost_micros"] = provider_cost
        prov["billed_cost_micros"] = billed
        return provider_cost, billed, prov
