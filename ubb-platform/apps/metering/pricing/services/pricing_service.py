from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment

PRICING_ENGINE_VERSION = "2.1.0"


class PricingError(Exception):
    pass


class PricingService:
    @staticmethod
    def _resolve_rate_within(book, selectors, metric_name, currency, as_of):
        """One matching semantic for all ten selectors (design D3).

        A rate's "" selector is a WILDCARD; a pinned selector must equal the
        event's value. Among matches the most-pinned rate wins, tie-broken by
        latest valid_from. `metric_name` alone keeps exact-match semantics —
        pricing is per-metric and a metric wildcard would be meaningless."""
        if book is None:
            return None
        qs = Rate.objects.filter(
            rate_card=book, metric_name=metric_name, currency=currency,
            valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
        for name in Rate.SELECTORS:
            qs = qs.filter(Q(**{name: selectors.get(name) or ""}) | Q(**{name: ""}))
        cands = list(qs)
        if not cands:
            return None
        cands.sort(key=lambda c: (c.specificity, c.valid_from), reverse=True)
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
    def _resolve_card(tenant, customer, card_type, selectors, metric_name, currency, as_of):
        book = PricingService._assigned_book(tenant, customer, card_type, currency)
        if book is not None:
            rate = PricingService._resolve_rate_within(
                book, selectors, metric_name, currency, as_of)
            if rate is not None:
                return rate
        provider = selectors.get("provider") or ""
        default_book = PricingService._default_book(tenant, card_type, provider, currency)
        if default_book is not None:
            rate = PricingService._resolve_rate_within(
                default_book, selectors, metric_name, currency, as_of)
            if rate is not None:
                return rate
        # Book-selection (provider_key) is a separate layer from the Rate-level
        # selector wildcarding above: a "" provider_key book is the tenant's
        # provider-AGNOSTIC default book (D3's headline fix applied at the book
        # layer too), so a non-empty provider that found no book, or a book
        # with no matching rate, falls back to it. Skipped when the request was
        # already provider-less — that IS the "" bucket, already tried above.
        if not provider:
            return None
        wildcard_book = PricingService._default_book(tenant, card_type, "", currency)
        return PricingService._resolve_rate_within(
            wildcard_book, selectors, metric_name, currency, as_of)

    @staticmethod
    def _compute(*, tenant, usage_metrics, caller_provider_cost, caller_billed,
                 units, resolve_card, apply_markup):
        """The ONE compute spine (#112): coverage → cost → price → markup
        fallback. ``price`` is this spine under one card resolver —
        ``resolve_card(card_type, metric)`` and the matching
        ``apply_markup(provider_cost)`` are the parameters — and it is the
        only rider left since #239 deleted the accept-time estimate that was
        the second. The parameterisation stays: it is what kept the two in
        agreement by construction, and what a future second rider would use
        rather than forking a pricing body. Raises PricingError exactly where
        strict cost coverage fails; always returns
        (provider_cost, billed, provenance)."""
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
                            if resolve_card("cost", m) is None]
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
                card = resolve_card("cost", metric)
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
                card = resolve_card("price", metric)
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
                billed = apply_markup(provider_cost)
                prov["price_source"] = "markup"

        prov["provider_cost_micros"] = provider_cost
        prov["billed_cost_micros"] = billed
        return provider_cost, billed, prov

    @staticmethod
    def price(*, tenant, customer, selectors, usage_metrics, currency,
              caller_provider_cost, caller_billed, units=None, as_of=None):
        """Exact pricing: the compute spine over as_of-exact ORM card
        resolution (the full provenance receipt is persisted with the event)
        and live-ORM markup. ``selectors`` is the full {provider, event_type,
        task_type, subtask_type, dim1..dim6} map (Rate.SELECTORS keys) — an
        absent/"" value wildcards against a rate that leaves it unpinned."""
        as_of = as_of or timezone.now()

        def resolve_card(card_type, metric):
            return PricingService._resolve_card(
                tenant, customer, card_type, selectors, metric, currency, as_of)

        def apply_markup(provider_cost):
            from apps.metering.pricing.services.markup_service import MarkupService
            return MarkupService.apply(provider_cost, tenant=tenant, customer=customer)

        return PricingService._compute(
            tenant=tenant, usage_metrics=usage_metrics,
            caller_provider_cost=caller_provider_cost,
            caller_billed=caller_billed, units=units,
            resolve_card=resolve_card, apply_markup=apply_markup)
