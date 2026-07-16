from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment

PRICING_ENGINE_VERSION = "2.1.0"


class PricingError(Exception):
    pass


class PricingService:
    @staticmethod
    def _dimensions_match(card_dimensions, tags):
        tags = tags or {}
        for k, v in (card_dimensions or {}).items():
            if str(tags.get(k)) != str(v):
                return False
        return True

    @staticmethod
    def _resolve_rate_within(book, provider, event_type, metric_name, tags, currency, as_of):
        if book is None:
            return None
        cands = [c for c in Rate.objects.filter(
            rate_card=book, provider=provider or "", event_type=event_type or "",
            metric_name=metric_name, currency=currency, valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
            if PricingService._dimensions_match(c.dimensions, tags)]
        if not cands:
            return None
        cands.sort(key=lambda c: (len(c.dimensions or {}), c.valid_from), reverse=True)
        return cands[0]

    @staticmethod
    def _assigned_book(tenant, customer, card_type, currency):
        if customer is None or card_type != "price":
            return None
        a = RateCardAssignment.objects.filter(
            tenant=tenant, customer=customer, currency=currency,
            rate_card__card_type="price").select_related("rate_card").first()
        return a.rate_card if a else None

    @staticmethod
    def _default_book(tenant, card_type, provider, currency):
        return RateCard.objects.filter(
            tenant=tenant, card_type=card_type, provider_key=provider or "",
            currency=currency, is_default=True).first()

    @staticmethod
    def _resolve_card(tenant, customer, card_type, provider, event_type, metric_name, tags, currency, as_of):
        book = PricingService._assigned_book(tenant, customer, card_type, currency)
        if book is not None:
            rate = PricingService._resolve_rate_within(
                book, provider, event_type, metric_name, tags, currency, as_of)
            if rate is not None:
                return rate
        default_book = PricingService._default_book(tenant, card_type, provider, currency)
        return PricingService._resolve_rate_within(
            default_book, provider, event_type, metric_name, tags, currency, as_of)

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
            for metric, units_val in sorted(usage_metrics.items()):
                card = PricingService._resolve_card(tenant, customer, "price", provider,
                                                    event_type, metric, tags, currency, as_of)
                if card is None:
                    continue
                matched = True
                entry = {"metric": metric, "units": units_val, "card_type": "price",
                         "rate_card_id": str(card.id), "pricing_model": card.pricing_model}
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
