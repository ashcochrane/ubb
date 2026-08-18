from typing import NamedTuple, Optional

from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment
from apps.metering.pricing.receipts import Resolution, build_receipt
from apps.platform.event_types.costing import cost_declaration
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_MODE_EVENT_PRICED,
    PRICING_STATUS_KNOWN,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    UNRESOLVED_REASON_REPORTED_COST_MISSING,
)

PRICING_ENGINE_VERSION = "2.1.0"


def _component(measurement_key, quantity, card):
    """ONE LINE OF AN EXPLANATION: the quantity, the rule's terms, the amount.

    **THE RECEIPT HAS TO OUTLIVE THE MEASUREMENTS IT EXPLAINS (#350, #153
    §12.4).** The detailed measurement rows are a child record with a retention
    horizon of its own; the receipt is kept for six years. So a component that
    recorded only a quantity and a total would explain nothing the day the
    detail expires — a tenant asked why a line is what it is would have a number
    and a pointer, and the recovery runs that re-price an unresolved cost would
    have nothing to work from. Every term the arithmetic used is therefore
    written down here **by value**: the quantity, the per-unit rate, the
    denominator it is divided by, and the flat addend. With those and the
    amount, a reader with only this record can redo the sum.

    **The denominator is not decoration.** A rate is "so much per N", and a
    component holding the rate without the N cannot be recomputed at all — the
    rounding is half-up on that N, so even the last micro of the answer depends
    on it.

    ⚠ **THE QUANTITY IS NOW IN TWO PLACES ON PURPOSE, AND THEY ARE NOT TWO
    SOURCES OF TRUTH (#165 §6).** The measurement record holds what was
    *reported*; this holds what was *used to compute an amount*. **They are not
    required to be equal and nothing ever reconciles them.** There is no drift
    check, no repair and no test asserting they agree, deliberately: if they
    ever disagree that is information — the engine priced something other than
    what was reported, and the record of each is what shows it — rather than a
    fault for a job to correct. Building the reconciliation would also
    re-create, one layer down, exactly the two-authorities shape the receipt
    exists to remove.

    Written once and used by both sections, because a cost component and a price
    component are the same fact about different rules, and two spellings of one
    shape is how the two come to differ exactly where a reader compares them.
    The pointer to the rule itself does not ride here — it is in `provenance`,
    in one place, so that nothing in a component is a reference somebody could
    follow for a figure.

    ⚠ Two of the keys below are spelled with words the registry has retired and
    they stay that way here. Not because nowhere else says them — the rate's own
    model and the book service both do — but because THIS file's occurrences are
    what keep it inside the counted sets those words are ledgered at. Re-spelling
    them would take the file out and report a word leaving the tree, in a commit
    that is not about the word: the ledger refuses an entry recording more files
    than the tree has. The ticket that renames the rule's arithmetic shape owns
    both.
    """
    return {
        "measurement_key": measurement_key,
        "units": quantity,
        "pricing_model": card.pricing_model,
        "rate_per_unit_micros": card.rate_per_unit_micros,
        "unit_quantity": card.unit_quantity,
        "fixed_micros": card.fixed_micros,
        "micros": card.compute(quantity),
    }


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
    #: The Pricing Receipt — the authoritative record of why these amounts are
    #: what they are (#349), built and validated by
    #: `apps.metering.pricing.receipts.build_receipt` and by nothing else. Named
    #: for the record it is (ADR-0006) — the column and the wire key it is
    #: eventually stored under still carry the retired word, and re-spelling
    #: either belongs to the ticket that owns them.
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
        quantity it priced would charge the same for all of them.

        **THE MATCH IS STILL ON THE NAME, THROUGH THE REFERENCE (#326).** The
        rate holds the declared record rather than a spelling of it, and this
        line reads the name back off it. Matching on the record's IDENTITY
        instead would be a different rule, not a tidier spelling of this one:
        declarations are Event-Type-local, so a rate that leaves `event_type`
        unpinned prices the quantity under every Event Type that declares that
        name, and identity matching would silently narrow it to one of them.
        `Measurement`'s own docstring called this — *"a Cost Rate still matches
        on measurement_key"* — before the reference existed.

        A rate the conversion could not place references nothing, so it cannot
        match here at all. That is what "deactivated" means in practice: the row
        is still readable, still lists, still says what it was written to price,
        and prices nothing."""
        if book is None:
            return None
        qs = Rate.objects.filter(
            rate_card=book, measurement__code=measurement_key, currency=currency,
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
    def _compute(*, subject, currency, effective_at, measurements,
                 caller_provider_cost, caller_billed,
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

        **THE SPINE DECIDES THE STATUSES AND THE RECEIPT RECORDS THEM (#349).**
        Nothing here assembles the stored record by hand: the two sides are
        collected as :class:`~apps.metering.pricing.receipts.Resolution`s and
        handed to the one construction boundary at the foot of this method,
        which validates them together before anybody can persist the result.
        The method beside each status is *how that amount was arrived at*, so it
        is null wherever no amount was — the rule the boundary enforces for both
        sides at once.

        `effective_at` is a PARAMETER and no clock is read below it: this method
        resolves as of an instant the caller names, and everything
        configuration-dependent arrives through `resolve_card` /
        `resolve_declaration`.

        Always returns a :class:`Costing`."""
        measurements = measurements or {}
        # THE RECEIPT'S PER-LINE NAME KEY MOVED WITH THE COLUMN (#275), and
        # receipts already written are NOT rewritten. A receipt records what the
        # engine did on a day, so back-dating one to a vocabulary that did not
        # exist when it was written would make it a worse record, not a better
        # one.
        #
        # `pricing_engine_version` DOES NOT SEPARATE THOSE TWO SHAPES and is
        # deliberately not bumped for a spelling: it describes what the engine
        # COMPUTED, and the arithmetic, the resolution order and every amount
        # are identical either side of the rename. Moving it would spend the one
        # signal that means "the numbers were produced differently" on a change
        # where they were not. What separates a record's SHAPE from its
        # behaviour is `receipt_schema_version`, which is the other half of the
        # pair the receipt carries and the half a rename moves.
        #
        # The per-quantity lines below are the receipt's components: what the
        # engine actually charged for, by value, in the section that produced
        # them — quantity, the rule's terms, the denominator and the amount they
        # produced, which is what makes each one reproducible with the measured
        # detail gone (`_component`). The ids they used to carry ride in
        # `provenance` instead, in one place, so a reader asking "which records
        # was this resolved against" does not reassemble the answer out of the
        # components — and so that nothing in a component is a pointer somebody
        # could follow for a figure.
        cost_components, price_components = [], []
        cost_rate_ids, price_rate_ids = {}, {}
        # THE QUANTITIES A RECOVERY WILL NEED, KEPT BY VALUE RATHER THAN
        # EXEMPTED FROM PRUNING (#350, #153 §12.4). An unresolved cost is
        # settled later, and what it needs to settle is the quantity that
        # matched no rule. The alternative ruling — mark the source payload
        # exempt from pruning until the record resolves — was refused: an
        # exemption is a second retention rule a pruning job must implement
        # correctly forever, and the day it does not the recovery runs stop
        # working silently, on exactly the records that most need fixing. A
        # snapshot is a fact that is either there or not.
        uncosted_quantities = {}

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
            # A FIGURE THAT ARRIVED IS A REPORTED COST, whoever declared what.
            # The method names how UBB came by the amount, and it came by being
            # told; the declaration is not consulted on this branch at all, so
            # reading `calculated` off one would be recording something this
            # branch never did.
            costing_method = COSTING_METHOD_REPORTED
        elif (declaration := resolve_declaration()) is not None \
                and declaration.declares_no_cost:
            # Not an outstanding task. The method is deliberately null through
            # here and the branch below: it names how an amount was arrived at,
            # and neither branch arrives at one.
            costing_method = None
            computed_micros = 0
            costing_status = COSTING_STATUS_NOT_APPLICABLE
        elif declaration is not None \
                and declaration.costing_method == COSTING_METHOD_REPORTED:
            costing_method = None
            computed_micros = 0
            costing_status = COSTING_STATUS_UNRESOLVED
            unresolved_reason = UNRESOLVED_REASON_REPORTED_COST_MISSING
        else:
            # Calculated, or declared nowhere at all — the registry is opt-in
            # and this is how everything recorded against an undeclared key has
            # always costed.
            computed_micros = 0
            uncosted = {}
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
            # ⚠ `units_val` KEEPS ITS NAME AND THAT IS NOT AN OVERSIGHT. A
            # contract control asserts the forbidden-term matcher walks past
            # seven near misses — identifiers that merely CONTAIN the retired
            # plural — and requires each to be a spelling real code has, because
            # skipping a spelling nothing uses proves nothing about over-firing.
            # It reads a named list of six files, and this module is the only
            # one of them carrying this identifier. Renaming the local to say
            # `quantity` was tried and emptied that near miss, which is the
            # vacuity failure this programme keeps paying for, in the direction
            # where a gate goes red rather than quiet. The rename belongs to the
            # ticket that owns the word.
            for measurement_key, units_val in measurements.items():
                card = resolve_card("cost", measurement_key)
                if card is None:
                    uncosted[measurement_key] = units_val
                    continue
                component = _component(measurement_key, units_val, card)
                computed_micros += component["micros"]
                cost_components.append(component)
                cost_rate_ids[measurement_key] = str(card.id)
            if uncosted:
                uncosted_quantities = uncosted
                costing_method = None
                costing_status = COSTING_STATUS_UNRESOLVED
                unresolved_reason = UNRESOLVED_REASON_COST_RATE_MISSING
            else:
                costing_method = COSTING_METHOD_CALCULATED
                costing_status = COSTING_STATUS_KNOWN

        # ---- PRICE ----
        if caller_billed is not None:
            billed = caller_billed
            # A PRICE THE CALLER STATED IS A PRICE ATTACHED TO THE EVENT, which
            # is what `direct_event_price` names — the ratified concept has two
            # values and the distinction it draws is margin-over-cost versus
            # a price of its own, not which door the price came through.
            pricing_method = PRICING_METHOD_DIRECT_EVENT_PRICE
        else:
            price_total, matched = 0, False
            for measurement_key, units_val in sorted(measurements.items()):
                card = resolve_card("price", measurement_key)
                if card is None:
                    continue
                matched = True
                component = _component(measurement_key, units_val, card)
                price_total += component["micros"]
                price_components.append(component)
                price_rate_ids[measurement_key] = str(card.id)
            if matched:
                billed = price_total
                pricing_method = PRICING_METHOD_DIRECT_EVENT_PRICE
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
                # price may call ITSELF unsettled is `pricing_status`, and #349
                # gave the receipt a place to say so without yet moving the
                # answer: the record below reports `known` for every price this
                # engine derives, because there is no price status column and no
                # rule that writes another value. The tickets that add both are
                # where this branch's floor stops reporting itself as settled —
                # and re-pricing after a settlement is theirs too.
                #
                # Pinned by `TestNoBilledFigureMoves` for the population that
                # does not move, and by the two cases below it for the one that
                # does. Both halves are asserted; neither is left to a comment.
                billed = apply_markup(computed_micros)
                pricing_method = PRICING_METHOD_MARGIN_OVER_COST

        # The receipt records what the engine DID; the columns record what UBB
        # KNOWS. Where the two differ the receipt keeps its resolved components
        # and the amount below is None — see the `_compute` docstring.
        recorded_cost = (computed_micros if costing_status == COSTING_STATUS_KNOWN
                         else None)
        # ⚠ EVERY PRICE THIS ENGINE DERIVES IS `known` TODAY, AND THAT IS A
        # STATEMENT WITH AN EXPIRY DATE. There is no price status column yet:
        # the price is never null, so the receipt's price side reports the only
        # answer the system currently holds. The three other price statuses —
        # and in particular the ruling that a margin over a supplier cost UBB
        # never learned is `waived` rather than a settled figure — arrive with
        # the nullable price column and the rules that write it, in the tickets
        # that follow this one. When they do, this line is the one that moves,
        # and the receipt's shape already admits every answer they need.
        pricing_receipt = build_receipt(
            subject=subject, effective_at=effective_at, currency=currency,
            pricing_engine_version=PRICING_ENGINE_VERSION,
            costing=Resolution(
                method=costing_method, status=costing_status,
                amount_micros=recorded_cost,
                detail={
                    "components": cost_components,
                    # THE LIST IS DERIVED FROM THE MAPPING AND NOT WRITTEN
                    # BESIDE IT. Readers have always asked which declarations
                    # went uncosted and that answer does not change; what is
                    # new is the quantity each of them carried. Taking the
                    # names off the mapping is what stops the pair being two
                    # statements that can disagree about the same fact — the
                    # shape this ticket refuses everywhere else, applied to
                    # its own record.
                    "uncosted_measurement_keys": list(uncosted_quantities),
                    "uncosted_quantities": uncosted_quantities,
                }),
            pricing=Resolution(
                method=pricing_method, status=PRICING_STATUS_KNOWN,
                amount_micros=billed,
                detail={
                    "components": price_components,
                    # THE SUBJECT'S WHOLE-JOB PRICING REGIME, BY VALUE (#151
                    # §8.4). The third axis: whether a whole unit of work is
                    # priced event by event or sold for one agreed price
                    # decides whether an event carries a customer price at all,
                    # so it explains this section's outcome and rides here
                    # rather than being looked up live against configuration
                    # that can have moved since.
                    #
                    # ⚠ EVERY UNIT OF WORK IN THIS SYSTEM IS EVENT-PRICED
                    # TODAY, AND THAT IS A STATEMENT WITH AN EXPIRY DATE. The
                    # concept is declared and its value set is closed, and
                    # there is no column anywhere to read it from: the slice
                    # that rebuilds the unit of work owns that column and the
                    # regime's whole vocabulary, and none of it is coined here.
                    # This is the one value the system can produce, said out
                    # loud rather than left out, so a receipt written today is
                    # still explicit about the axis six years from now. When
                    # the column lands this is the line that reads it — the
                    # same shape `usage/measurements.py` uses for the posting
                    # kind it is waiting on.
                    "pricing_mode": PRICING_MODE_EVENT_PRICED,
                }),
            provenance={"cost_rate_ids": cost_rate_ids,
                        "price_rate_ids": price_rate_ids})
        return Costing(provider_cost_micros=recorded_cost,
                       billed_cost_micros=billed,
                       pricing_receipt=pricing_receipt,
                       costing_status=costing_status,
                       unresolved_reason=unresolved_reason)

    @staticmethod
    def price(*, subject, tenant, customer, selectors, measurements, currency,
              caller_provider_cost, caller_billed, as_of=None):
        """Exact pricing: the compute spine over as_of-exact ORM card
        resolution (the Pricing Receipt it builds is persisted with the event)
        and live-ORM markup. ``selectors`` is the full {provider, event_type,
        task_type, subtask_type, the ten slots} map (Rate.SELECTORS keys) — an
        absent/"" value wildcards against a rate that leaves it unpinned.

        ``subject`` is a :class:`~apps.metering.pricing.receipts.ReceiptSubject`
        and is REQUIRED, with no default. A receipt explains one named thing,
        and a default here would hand every caller who omitted the argument one
        subject's answer — the same defect a default column name is, one level
        up. It is an input rather than a stamp applied afterwards, which is why
        the caller generates the row's id before it records the row."""
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
            subject=subject, currency=currency,
            effective_at=as_of.isoformat(),
            measurements=measurements,
            caller_provider_cost=caller_provider_cost,
            caller_billed=caller_billed,
            resolve_declaration=resolve_declaration,
            resolve_card=resolve_card, apply_markup=apply_markup)
