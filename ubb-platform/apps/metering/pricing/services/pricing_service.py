from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment

PRICING_ENGINE_VERSION = "2.1.0"


class PricingError(Exception):
    pass


class PricingService:
    @staticmethod
    def _resolve_rate_within(book, selectors, measurement_key, currency, as_of):
        """One matching semantic for all ten selectors (design D3).

        A rate's "" selector is a WILDCARD; a pinned selector must equal the
        event's value. Among matches the most-pinned rate wins, tie-broken by
        latest valid_from. `measurement_key` alone keeps exact-match semantics —
        a rate prices one named quantity, and a rate that wildcarded WHICH
        quantity it priced would charge the same for all of them."""
        if book is None:
            return None
        qs = Rate.objects.filter(
            rate_card=book, measurement_key=measurement_key, currency=currency,
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
    def _resolve_card(tenant, customer, card_type, selectors, measurement_key, currency, as_of):
        book = PricingService._assigned_book(tenant, customer, card_type, currency)
        if book is not None:
            rate = PricingService._resolve_rate_within(
                book, selectors, measurement_key, currency, as_of)
            if rate is not None:
                return rate
        provider = selectors.get("provider") or ""
        default_book = PricingService._default_book(tenant, card_type, provider, currency)
        if default_book is not None:
            rate = PricingService._resolve_rate_within(
                default_book, selectors, measurement_key, currency, as_of)
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
            wildcard_book, selectors, measurement_key, currency, as_of)

    @staticmethod
    def _compute(*, tenant, measurements, caller_provider_cost, caller_billed,
                 resolve_card, apply_markup):
        """The ONE compute spine (#112): coverage → cost → price → markup
        fallback. ``price`` is this spine under one card resolver —
        ``resolve_card(card_type, measurement_key)`` and the matching
        ``apply_markup(provider_cost)`` are the parameters — and it is the
        only rider left since #239 deleted the accept-time estimate that was
        the second. The parameterisation stays: it is what kept the two in
        agreement by construction, and what a future second rider would use
        rather than forking a pricing body. Raises PricingError exactly where
        strict cost coverage fails; always returns
        (provider_cost, billed, provenance)."""
        measurements = measurements or {}
        # THE RECEIPT'S PER-LINE NAME KEY MOVED WITH THE COLUMN (#275), and
        # receipts already written are NOT rewritten. A receipt is a record of
        # what the engine did on a day, so back-dating one to a vocabulary that
        # did not exist when it was written would make it a worse record, not a
        # better one; `engine_version` above is how a reader tells the two
        # apart. Nothing in the tree reads this key — the response surfaces
        # `uncosted_metrics` and the whole receipt as an opaque object, and the
        # console reads neither — so the split costs no reader a lookup today.
        # The list key beside it is untouched: it is not the retired word.
        prov = {"engine_version": PRICING_ENGINE_VERSION, "metrics": []}

        # ---- COST ----
        if caller_provider_cost is not None:
            provider_cost = caller_provider_cost
            prov["cost_source"] = "caller"
            # When the strict coverage flag is on, every quantity in
            # measurements must have a matching cost card even when the caller
            # supplies the aggregate cost. Without this check the caller-cost
            # path silently bypasses the guarantee.
            if measurements and getattr(tenant, "require_cost_card_coverage", False):
                uncosted = [m for m in measurements
                            if resolve_card("cost", m) is None]
                if uncosted:
                    prov["uncosted_metrics"] = uncosted
                    raise PricingError(f"No cost rate card for metrics: {uncosted}")
        else:
            provider_cost = 0
            uncosted = []
            # F2.4's second strict-mode refusal RETIRED WITH ITS INPUT (#272).
            # It rejected an event that declared a nameless magnitude with no
            # quantity name to resolve a rate card against — "you told us there
            # was volume, but not of what". That magnitude was the posting's
            # inline unit total, and a caller can no longer state it at all, so
            # the condition is not weakened here, it has become unexpressible.
            #
            # NO EXPRESSIBLE REQUEST CHANGES VERDICT. The refusal only ever
            # fired above zero; an event with no quantities and no caller cost
            # was already accepted as a marker at zero or omitted, and that is
            # what every such request now is. The coverage guarantee for events
            # that DO name their quantities is untouched — the `uncosted` branch
            # below and the caller-cost branch above, both unchanged.
            #
            # ONE CALLER DOES SEE A DIFFERENT ANSWER, AND IT IS WORTH SAYING SO.
            # The request schema ignores unknown fields, so a STALE client still
            # posting the retired field under strict coverage now gets a 200 and
            # a zero-cost marker where it used to get a 422. Nothing is
            # mis-metered — there was never anything to multiply that number by,
            # and billed is markup(0) — but a loud refusal became a quiet accept
            # for a caller that has not migrated. That is the cost of the
            # removal rather than an oversight in it, and it is why the drop is
            # recorded as a reviewed break on the request side too.
            for measurement_key, units_val in measurements.items():
                card = resolve_card("cost", measurement_key)
                if card is None:
                    uncosted.append(measurement_key)
                    continue
                amt = card.compute(units_val)
                provider_cost += amt
                prov["metrics"].append({"measurement_key": measurement_key,
                    "units": units_val, "card_type": "cost",
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
            for measurement_key, units_val in sorted(measurements.items()):
                card = resolve_card("price", measurement_key)
                if card is None:
                    continue
                matched = True
                entry = {"measurement_key": measurement_key, "units": units_val,
                         "card_type": "price",
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
    def price(*, tenant, customer, selectors, measurements, currency,
              caller_provider_cost, caller_billed, as_of=None):
        """Exact pricing: the compute spine over as_of-exact ORM card
        resolution (the full provenance receipt is persisted with the event)
        and live-ORM markup. ``selectors`` is the full {provider, event_type,
        task_type, subtask_type, dim1..dim6} map (Rate.SELECTORS keys) — an
        absent/"" value wildcards against a rate that leaves it unpinned."""
        as_of = as_of or timezone.now()

        def resolve_card(card_type, measurement_key):
            return PricingService._resolve_card(
                tenant, customer, card_type, selectors, measurement_key,
                currency, as_of)

        def apply_markup(provider_cost):
            from apps.metering.pricing.services.markup_service import MarkupService
            return MarkupService.apply(provider_cost, tenant=tenant, customer=customer)

        return PricingService._compute(
            tenant=tenant, measurements=measurements,
            caller_provider_cost=caller_provider_cost,
            caller_billed=caller_billed,
            resolve_card=resolve_card, apply_markup=apply_markup)
