from typing import NamedTuple, Optional

from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment
from apps.platform.event_types.costing import cost_declaration
from core.vocabulary import (
    COSTING_METHOD_REPORTED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    UNRESOLVED_REASON_REPORTED_COST_MISSING,
)

PRICING_ENGINE_VERSION = "2.1.0"


class Costing(NamedTuple):
    """What the compute spine concluded — five facts, named rather than ordered.

    This replaced a three-tuple when the spine started deciding the costing
    status (#320). Two of the five are new and one changed meaning, and a
    positional unpack cannot say which is which: `provider_cost_micros` is now
    `None` wherever the status is not `known`, and a caller that kept reading
    position zero as a number would have found a `None` in it with nothing
    naming the reason. Five names cost one line at each of four call sites and
    make every one of them say what it is reading.
    """

    #: WHAT UBB KNOWS THE SUPPLIER CHARGED — `None` when it does not know, which
    #: is what the posting column stores and what its `CHECK` enforces (#317).
    #: Never a partial sum: a cost that is partly resolved is not resolved.
    provider_cost_micros: Optional[int]
    #: What the customer is charged. Never `None` — the price half of an
    #: uncosted event is slice 4's (`pricing_status`), and until then a price
    #: derived by markup from an incomplete cost is a floor, exactly as it was
    #: before this ticket.
    billed_cost_micros: int
    #: The Pricing Receipt: engine version, per-quantity lines, sources. Named
    #: for the record it is (ADR-0006) — the column and the wire key it is
    #: eventually stored under still carry the retired word, and re-spelling
    #: either belongs to the slice that owns them.
    pricing_receipt: dict
    #: `known` · `unresolved` · `not_applicable`, held by reference from
    #: `core.vocabulary`.
    costing_status: str
    #: Which input did not arrive, and `None` unless the status is `unresolved`.
    unresolved_reason: Optional[str]


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
    def _compute(*, measurements, caller_provider_cost, caller_billed,
                 resolve_declaration, resolve_card, apply_markup):
        """The ONE compute spine (#112): cost → status → price → markup
        fallback. ``price`` is this spine under one card resolver —
        ``resolve_card(card_type, measurement_key)``, ``resolve_declaration()``
        and the matching ``apply_markup(provider_cost)`` are the parameters —
        and it is the only rider left since #239 deleted the accept-time
        estimate that was the second. The parameterisation stays: it is what
        kept the two in agreement by construction, and what a future second
        rider would use rather than forking a pricing body.

        **THIS IS WHERE A COSTING STATUS IS DECIDED, AND THE ONLY PLACE (#320).**
        Nothing raises here any more. An event UBB cannot cost is *recorded*
        with the cost it does not have said out loud, because the supplier has
        already run the call and already charged for it: refusing the record
        does not undo the spend, it hides it, and the missing margin turns up a
        month later as a gap nobody can account for.

        The four answers, in the order they are asked:

        1. the caller supplied a figure → `known`, and it is that figure
        2. the Event Type declares no cost at all → `not_applicable`, no amount
           and no reason, because a design decision is not an outstanding task
        3. the Event Type declares a *reported* cost and no figure arrived →
           `unresolved`, `reported_cost_missing`
        4. otherwise the quantities resolve against Cost Rates → `known` and the
           sum (**zero is a resolved amount**: a call that genuinely cost
           nothing), or `unresolved`, `cost_rate_missing` and the list of
           quantities that matched no rate

        **A partly resolved cost is not a resolved cost.** Where any quantity
        matched no rate the amount is `None` and the resolved lines stay in the
        receipt below, which is where the floor lives. Storing the partial sum
        is the ambiguity #317's column exists to remove, one layer up.

        Always returns a :class:`Costing`."""
        measurements = measurements or {}
        # THE RECEIPT'S PER-LINE NAME KEY MOVED WITH THE COLUMN (#275), and
        # receipts already written are NOT rewritten. A receipt records what the
        # engine did on a day, so back-dating one to a vocabulary that did not
        # exist when it was written would make it a worse record, not a better
        # one.
        #
        # `engine_version` DOES NOT SEPARATE THE TWO SHAPES and is deliberately
        # not bumped for this: it describes what the engine COMPUTED, and the
        # arithmetic, the resolution order and every amount are identical either
        # side of the rename. Moving it for a spelling would spend the one signal
        # that means "the numbers were produced differently" on a change where
        # they were not. A reader tells the shapes apart by which key the line
        # carries, which is the honest discriminator because it is the only thing
        # that actually differs.
        #
        # That costs nobody a lookup, because nothing in the tree reads this key.
        # What IS read off the receipt is the uncosted-quantity list — by the
        # endpoint below and by the console's test-event panel — and #320 took
        # the canonical word for a declared quantity into that key's name, in
        # the break the recording response was already making.
        receipt = {"engine_version": PRICING_ENGINE_VERSION, "metrics": []}

        # ---- COST ----
        unresolved_reason = None
        if caller_provider_cost is not None:
            # A figure the caller supplied IS the answer, and no declaration is
            # consulted to confirm it. WHERE such a figure may be supplied at
            # all is a separate question, answered before this runs and with
            # its own 422 — `metering_endpoints.admit_supplier_cost` (#324).
            # Costing a figure that arrived is this one.
            computed_micros = caller_provider_cost
            costing_status = COSTING_STATUS_KNOWN
            receipt["cost_source"] = "caller"
        elif (declaration := resolve_declaration()) is not None \
                and declaration.declares_no_cost:
            # Not an outstanding task. `cost_source` is deliberately absent
            # through here and the branch below: the key names which source
            # produced the amount, and no source produced one.
            computed_micros = 0
            costing_status = COSTING_STATUS_NOT_APPLICABLE
        elif declaration is not None \
                and declaration.costing_method == COSTING_METHOD_REPORTED:
            computed_micros = 0
            costing_status = COSTING_STATUS_UNRESOLVED
            unresolved_reason = UNRESOLVED_REASON_REPORTED_COST_MISSING
        else:
            # Calculated, or declared nowhere at all — the registry is opt-in
            # and this is how everything recorded against an undeclared key has
            # always costed.
            computed_micros = 0
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
                computed_micros += amt
                receipt["metrics"].append({"measurement_key": measurement_key,
                    "units": units_val, "card_type": "cost",
                    "rate_card_id": str(card.id), "pricing_model": card.pricing_model, "micros": amt})
            receipt["cost_source"] = "rate_card"
            if uncosted:
                receipt["uncosted_measurement_keys"] = uncosted
                costing_status = COSTING_STATUS_UNRESOLVED
                unresolved_reason = UNRESOLVED_REASON_COST_RATE_MISSING
            else:
                costing_status = COSTING_STATUS_KNOWN

        # ---- PRICE ----
        if caller_billed is not None:
            billed = caller_billed
            receipt["price_source"] = "caller"
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
                receipt["metrics"].append(entry)
            if matched:
                billed = price_total
                receipt["price_source"] = "rate_card"
            else:
                # MARKUP APPLIES TO WHAT THE COST BRANCH ARRIVED AT, AND THAT
                # MOVES FOR EXACTLY ONE POPULATION (#320).
                #
                # An event with no declaration — every event in this repository
                # before the registry is adopted — takes the rate-card branch
                # above, so its markup basis is the same partial sum it always
                # was and its billed figure does not move at all.
                #
                # A DECLARED `reported` OR NO-COST EVENT TYPE IS DIFFERENT, and
                # it is a real change rather than an oversight: those branches
                # arrive at nothing, so a tenant with such a declaration, cost
                # rates for its quantities and NO price rate now bills
                # `markup(0)` where they billed markup over those rates. That is
                # the honest answer, because the declaration is the tenant
                # saying those rates are not this Event Type's cost: `reported`
                # means the supplier's own figure is the cost, and no-cost means
                # there is none. Marking up a basis the declaration disowns
                # would be inventing a number, which is the failure this slice
                # exists to delete — and it would be inventing it in the
                # flattering direction.
                #
                # `markup(0)` IS THE FLOOR, WHICH IS THIS SLICE'S SHAPE FOR
                # INCOMPLETE INFORMATION EVERYWHERE ELSE. The same event once
                # its supplier figure arrives takes the caller branch and bills
                # `markup(figure)`; until then the basis is missing and the
                # price built on it is a floor, on a posting already marked
                # `unresolved` so nobody reads it as settled. Whether such a
                # price may call ITSELF unsettled is `pricing_status`, which is
                # slice 4's word and not one this slice may coin (spec §3.12) —
                # and re-pricing after a settlement is that slice's too.
                #
                # Pinned by `TestNoBilledFigureMoves` for the population that
                # does not move, and by the two cases below it for the one that
                # does. Both halves are asserted; neither is left to a comment.
                billed = apply_markup(computed_micros)
                receipt["price_source"] = "markup"

        # The receipt records what the engine DID; the columns record what UBB
        # KNOWS. Where the two differ the receipt keeps its resolved lines and
        # the amount below is None — see the `_compute` docstring.
        recorded_cost = (computed_micros if costing_status == COSTING_STATUS_KNOWN
                         else None)
        receipt["provider_cost_micros"] = recorded_cost
        receipt["billed_cost_micros"] = billed
        return Costing(provider_cost_micros=recorded_cost,
                       billed_cost_micros=billed,
                       pricing_receipt=receipt,
                       costing_status=costing_status,
                       unresolved_reason=unresolved_reason)

    @staticmethod
    def price(*, tenant, customer, selectors, measurements, currency,
              caller_provider_cost, caller_billed, as_of=None):
        """Exact pricing: the compute spine over as_of-exact ORM card
        resolution (the full provenance receipt is persisted with the event)
        and live-ORM markup. ``selectors`` is the full {provider, event_type,
        task_type, subtask_type, the ten slots} map (Rate.SELECTORS keys) — an
        absent/"" value wildcards against a rate that leaves it unpinned."""
        as_of = as_of or timezone.now()

        def resolve_card(card_type, measurement_key):
            return PricingService._resolve_card(
                tenant, customer, card_type, selectors, measurement_key,
                currency, as_of)

        def resolve_declaration():
            """What this event's Event Type declares about cost, or None.

            A function rather than a value so the spine decides *whether* the
            declaration matters, the same way it decides which cards to
            resolve. A caller-supplied figure needs no declaration, and this is
            a query per recording call on the hottest write path in the system
            — one the spine simply never asks for on that branch.
            """
            return cost_declaration(tenant=tenant,
                                    key=selectors.get("event_type"))

        def apply_markup(provider_cost):
            from apps.metering.pricing.services.markup_service import MarkupService
            return MarkupService.apply(provider_cost, tenant=tenant, customer=customer)

        return PricingService._compute(
            measurements=measurements,
            caller_provider_cost=caller_provider_cost,
            caller_billed=caller_billed,
            resolve_declaration=resolve_declaration,
            resolve_card=resolve_card, apply_markup=apply_markup)
