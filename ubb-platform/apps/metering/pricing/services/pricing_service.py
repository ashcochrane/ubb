from dataclasses import dataclass
from typing import Any, NamedTuple, Optional

from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard, RateCardAssignment
from apps.metering.pricing.receipts import ReceiptSubject, Resolution, build_receipt
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
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    UNRESOLVED_REASON_REPORTED_COST_MISSING,
)

PRICING_ENGINE_VERSION = "2.1.0"

#: WHERE A RULE CAME FROM — the ladder's MINOR key (#356, #147 §5.1).
#:
#: Two sources and no more: the rules a customer's own book holds, and the rules
#: in the book selected for that customer. They are ranked so that at equal
#: specificity the customer's own answer wins, which is what makes "override"
#: mean *replace the rule at the level you are overriding* rather than *replace
#: the catalogue*.
#:
#: They are integers rather than names because they are only ever compared, and
#: the comparison is the whole of what they are for.
FROM_THE_CUSTOMERS_OWN_RULES = 1
FROM_THE_SELECTED_BOOK = 0


def ladder_rank(rule, source):
    """THE COMPOSITE RANKING RULE, AND THE ONE PLACE IT IS STATED (#356).

    **How specifically a rule names the event is compared FIRST; where it came
    from is only the tie-break within a level.** So a tenant writes a broad
    default plus narrow overrides and gets the behaviour they expect without
    reasoning about book precedence, and the ladder reads as four rungs:

    1. the customer's own rule for this exact Event Type
    2. the selected book's rule for this exact Event Type
    3. the customer's blanket rule
    4. the selected book's default rule

    **WHY SPECIFICITY OUTRANKS SOURCE** (#147 §5.2). The alternative — the
    customer's own contract answering first at every level — was the ladder as
    first stated and was rejected on its consequence: a customer's blanket 15%
    would shadow every specific price the tenant configured, so agreeing a small
    discount silently deletes a catalogue with nothing anywhere reporting that
    it had. The tenant's only defence would be to restate every specific rule
    inside every override. ADR-0005 §8 called book tier dominating rate
    specificity a sharp edge; specificity-major ordering is what dissolves it,
    because then there is one ranking and source is a tie-break inside it.

    **STATED HERE AND NOWHERE ELSE.** It used to live as a sentence on
    ``Rate.specificity``, a property that counts pinned selectors — one of the
    two ingredients, and no place from which the composition can be true or
    false. The remaining tie-break on ``valid_from`` is not part of the ruling:
    it decides between two rules a tenant made equally specific from the same
    source, where the later decision is the one they meant.
    """
    return (rule.specificity, source, rule.valid_from)


def a_margin_has_no_basis(costing_status):
    """A MARGIN OVER A COST UBB NEVER LEARNED IS `waived`, NOT DEFERRED (#147 §7.3).

    A margin is a percentage of what the call cost, and where UBB never learned
    the cost there is nothing to take it over. Holding such a charge open
    forever is how a receivable nobody will ever collect sits in a tenant's
    figures, so it is recorded as a decided loss rather than queued: `waived` is
    never a candidate for a recovery run.

    **STATED ONCE AND ASKED AT BOTH RUNGS.** A markup and a rule declaring a
    margin are the SAME METHOD at two rungs, which is the whole reason
    specificity-before-source is coherent — so a rule about that method that
    held at one rung and not the other would make a tenant's answer depend on
    where they wrote the percentage down.

    ⚠ **`not_applicable` IS A BELIEVED BASIS AND NOT A MISSING ONE.** An Event
    Type that declares no cost is the tenant saying there is none, so the basis
    is genuinely zero and a margin over it settles — at the uplift, which may
    well be nothing. `unresolved` is UBB not knowing. The two look identical in
    the amount, because both null the cost, and the status is the only thing
    that tells them apart — which is why this asks the status rather than the
    figure.
    """
    return costing_status == COSTING_STATUS_UNRESOLVED


def _priced_by_rules(rules, total_micros, costing_status):
    """WHAT THE RULE RUNGS ANSWERED — the amount, and the method that derived it.

    Returns `(amount, method, status)`.

    **THE METHOD COMES FROM THE RULE AND NOT FROM THE ENGINE'S HABIT (#355).** A
    rule declares which method it would derive by, or declares none; a rule that
    declares none prices the event's own quantities by its own terms, which is
    `direct_event_price` — an amount attached to the event regardless of what
    the call cost. That is what every rate on disk is today, and reading it as
    anything else would put a value on the record no tenant chose.

    **A RULE DECLARING A MARGIN IS THE MARKUP RUNG'S METHOD AT A DIFFERENT
    RUNG, AND IT GETS THE SAME TWO ANSWERS.** Where the cost is one UBB never
    learned, `a_margin_has_no_basis` says `waived` — the same ruling the markup
    rung takes, because the two are one method and a tenant should not get a
    different status for writing the percentage in a different place. Where the
    cost IS believed, the answer is `unknown`: the percentage lives on a
    separate record while markup is one, and the check that keeps a rule from
    composing refuses the two money terms this table can express, so such a rule
    carries nothing to compute with. Computing its terms anyway would answer a
    settled zero for a price nobody stated. The ticket that moves a percentage
    onto the rule is the ticket that makes that branch compute.

    **AND A PARTLY RESOLVED PRICE IS NOT A RESOLVED PRICE**, which is the cost
    side's rule at the sibling site: one quantity priced by a rule that cannot
    compute makes the whole answer unsettled, because the alternative is a total
    that silently omits a line.
    """
    declared = {rule.pricing_method for rule in rules} - {None}
    if PRICING_METHOD_MARGIN_OVER_COST in declared:
        if a_margin_has_no_basis(costing_status):
            return None, None, PRICING_STATUS_WAIVED
        return None, None, PRICING_STATUS_UNKNOWN
    return total_micros, PRICING_METHOD_DIRECT_EVENT_PRICE, PRICING_STATUS_KNOWN


def _priced_by_markup(markup, basis_micros, costing_status):
    """WHAT THE MARKUP RUNG ANSWERED — the last rung, and its two refusals.

    Returns `(amount, method, status)`.

    **NO MARKUP RUNG IS `unknown`, NEVER A ZERO AND NEVER THE COST** (#356).
    UBB ships no catalogue: a tenant with no declared markup has no markup rung,
    and answering the supplier's own cost would charge a customer exactly what
    the call cost and call it a settled decision. A price nobody stated is
    information UBB does not have.

    ⚠ **THAT QUESTION IS ASKED FIRST, AND THE ORDER IS THE RULING.** No rung at
    all is `unknown` even where the basis is also missing, because `waived` says
    somebody decided not to pursue a charge and a tenant who has declared
    nothing has decided nothing. Only once a rung exists does the basis matter,
    and then `a_margin_has_no_basis` answers for it.
    """
    if markup is None:
        return None, None, PRICING_STATUS_UNKNOWN
    if a_margin_has_no_basis(costing_status):
        return None, None, PRICING_STATUS_WAIVED
    return (markup.applied_to(basis_micros),
            PRICING_METHOD_MARGIN_OVER_COST, PRICING_STATUS_KNOWN)


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
    #: What the customer is charged — `None` when UBB could not resolve it,
    #: which is what the posting column stores and what its `CHECK` enforces
    #: (#351). It was `int` and documented as "never `None`" until this slice
    #: gave the price half the same shape the cost half above has had since
    #: #317.
    billed_cost_micros: Optional[int]
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
    #: `known` · `waived` · `unknown` · `not_applicable`, held by reference from
    #: `core.vocabulary` (#351), and read off the receipt's price section rather
    #: than decided again here.
    #:
    #: THREE OF THE FOUR ARE NOW REACHED (#356). The ladder answers `known`
    #: where a rung priced the event, `waived` where a margin was taken over a
    #: supplier cost UBB never learned, and `unknown` where no rung answered at
    #: all. `not_applicable` is the fourth and nothing produces it: it is a fact
    #: about the tenant's posture and the job's pricing regime rather than about
    #: resolution, the regime's whole vocabulary belongs to the slice that
    #: rebuilds the unit of work, and the rule that decides its REASON is
    #: written and waiting in `pricing/applicability.py`.
    pricing_status: str
    #: Which of two mutually exclusive causes produced `not_applicable`, and
    #: `None` for every other status. The rule is
    #: `apps.metering.pricing.applicability.not_applicable_reason_for`.
    not_applicable_reason: Optional[str] = None


class PricingService:
    @staticmethod
    def _matching_rules_across(books, selectors, measurement_key, currency, as_of):
        """Every rule in the books in play that matches this event, unranked.

        One matching semantic for all ten selectors (design D3): a rate's ""
        selector is a WILDCARD; a pinned selector must equal the event's value.
        `measurement_key` alone keeps exact-match semantics — a rate prices one
        named quantity, and a rate that wildcarded WHICH quantity it priced
        would charge the same for all of them.

        **RANKING IS NOT DONE HERE, AND THAT IS THE CHANGE (#356).** This
        returns candidates paired with where each came from; `ladder_rank`
        orders them across every book in play at once. While each book ranked
        its own matches and the caller walked the books in order, book tier
        dominated rate specificity — so a broad rule in a higher-precedence book
        beat a narrow rule in a lower one, which is the sharp edge #147 §5.2
        removes.

        **ONE QUERY FOR ALL OF THEM, WHICH IS FEWER THAN THE WALK IT REPLACES.**
        Ranking across books needs every candidate, so a query per book would
        have made the hottest write path in the system pay two or three where it
        used to short-circuit at one. `rate_card__in` asks once instead, and the
        source each rule carries is read back off the book it belongs to.

        ⚠ **AND THE RESULT IS RETURNED IN BOOK-SELECTION ORDER, NOT IN ROW
        ORDER.** One query means the database decides what order the rules come
        back in, and the ranking above is a STABLE sort — so a tie it cannot
        break would silently be decided by the query plan, differently on
        different days. Ordering the candidates by the book they came from
        restores the one answer a tenant can predict: `_selected_books` puts
        the narrowest book first.

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
        source_of = {book.id: source for source, book in books}
        position_of = {book.id: index for index, (_, book) in enumerate(books)}
        qs = Rate.objects.filter(
            rate_card__in=list(source_of), measurement__code=measurement_key,
            currency=currency, valid_from__lte=as_of,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
        for name in Rate.SELECTORS:
            qs = qs.filter(Q(**{name: selectors.get(name) or ""}) | Q(**{name: ""}))
        return sorted(((rule, source_of[rule.rate_card_id]) for rule in qs),
                      key=lambda pair: position_of[pair[0].rate_card_id])

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
    def _selected_books(tenant, customer, card_type, provider, currency):
        """WHICH BOOKS THIS SUBJECT'S PRICE MAY BE RESOLVED FROM, chosen once.

        Selection and resolution are two steps and this is the first (#147
        §5.3). A book becomes readable for one event in exactly two ways: it is
        the tenant's default for the event's provider, or the customer is
        assigned to it. Anything else — a book nobody is assigned to, another
        customer's book, the default book of a provider this event is not from —
        is unreachable, and no rule inside it can be the answer however well it
        matches.

        **THE PROVIDER-AGNOSTIC DEFAULT IS SELECTION, NOT A THIRD TIER.** A ""
        `provider_key` book is the tenant's provider-agnostic default (D3's
        headline fix applied at the book layer), so it is in play alongside the
        provider's own default rather than after it. It used to be reached by
        falling through when the provider's book held no matching rule, which is
        the cross-book walk #147 §5.3 deletes; ranking both books' rules
        together answers the same events the same way for a better reason,
        because a rule pinning the provider outranks one that does not on
        SPECIFICITY.

        Returns `(source, book)` pairs. `ladder_rank` is what orders the rules
        they hold — but the ORDER of this list is load-bearing all the same, and
        it is the narrowest book first: two rules a tenant made equally specific
        from the same source are separated by nothing else, and the stable sort
        over that tie keeps whichever book came back first here. The provider's
        own default book is therefore ahead of the provider-agnostic one, which
        is the answer the tiered walk used to give and the only one a tenant
        could predict.

        ⚠ **EACH BOOK APPEARS EXACTLY ONCE, AND THE FIRST WAY IT WAS REACHED IS
        THE ONE THAT COUNTS.** A customer can be assigned to the very book that
        is also the tenant's default, so the same rows are reachable twice; a
        second entry for it would let the ranking read the customer's own rules
        as the tenant's, silently demoting every override such a tenant wrote.
        Assigned is appended first, so keeping the first entry keeps the higher
        source.
        """
        books, seen = [], set()
        assigned = PricingService._assigned_book(
            tenant, customer, card_type, currency)
        if assigned is not None:
            books.append((FROM_THE_CUSTOMERS_OWN_RULES, assigned))
            seen.add(assigned.id)
        # A LIST AND NOT A SET, because the order above is load-bearing: a set's
        # iteration order would decide ties between the provider's own default
        # book and the provider-agnostic one, differently between processes.
        for provider_key in ([provider, ""] if provider else [""]):
            default = PricingService._default_book(
                tenant, card_type, provider_key, currency)
            if default is not None and default.id not in seen:
                books.append((FROM_THE_SELECTED_BOOK, default))
                seen.add(default.id)
        return books

    @staticmethod
    def _resolve_card(tenant, customer, card_type, selectors, measurement_key,
                      currency, as_of, books=None):
        """THE LADDER: one ranking over every rule in every book in play.

        There is no fallthrough between books. The books are selected first,
        every matching rule in all of them competes in ONE ranking, and a
        quantity with no matching rule anywhere in them resolves to nothing —
        which on the price side is what sends the answer to the markup rung, and
        on the cost side is what makes the posting unresolved.

        `ladder_rank` holds the ordering and the argument for it. Ties beyond it
        are left to the stable sort, which keeps the order the books came back
        in; two rules a tenant made identically specific, from one source, on
        one instant are not a distinction the ladder claims to draw.

        ``books`` lets a caller resolving MANY quantities for one event select
        them once instead of once per quantity — which is what
        :func:`resolve_price` does, and the reason selection and ranking are two
        steps rather than one. It is configuration and not a clock, so
        re-reading it when a caller has not supplied it is a default rather than
        an override.
        """
        if books is None:
            books = PricingService._selected_books(
                tenant, customer, card_type,
                selectors.get("provider") or "", currency)
        candidates = PricingService._matching_rules_across(
            books, selectors, measurement_key, currency, as_of)
        if not candidates:
            return None
        candidates.sort(key=lambda pair: ladder_rank(*pair), reverse=True)
        return candidates[0][0]

    @staticmethod
    def _compute(*, subject, currency, effective_at, measurements,
                 caller_provider_cost, caller_billed,
                 resolve_declaration, resolve_card, resolve_markup):
        """The ONE compute spine (#112): cost → status → price → markup rung,
        returning the receipt. ``resolve_price`` is this spine under one card
        resolver — ``resolve_card(card_type, measurement_key)``,
        ``resolve_declaration()`` and ``resolve_markup()`` are the parameters —
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

        Always returns a Pricing Receipt — the whole record, validated at the
        one construction boundary at the foot of this method. It is what the
        recording path reads every column it writes back off (:class:`Costing`),
        so there is one statement of what the engine concluded rather than two
        that can drift."""
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
        resolved_markup = None
        if caller_billed is not None:
            billed = caller_billed
            # A PRICE THE CALLER STATED IS A PRICE ATTACHED TO THE EVENT, which
            # is what `direct_event_price` names — the ratified concept has two
            # values and the distinction it draws is margin-over-cost versus
            # a price of its own, not which door the price came through.
            pricing_method = PRICING_METHOD_DIRECT_EVENT_PRICE
            pricing_status = PRICING_STATUS_KNOWN
        else:
            price_total, matched = 0, []
            for measurement_key, units_val in sorted(measurements.items()):
                card = resolve_card("price", measurement_key)
                if card is None:
                    continue
                matched.append(card)
                component = _component(measurement_key, units_val, card)
                price_total += component["micros"]
                price_components.append(component)
                price_rate_ids[measurement_key] = str(card.id)
            if matched:
                billed, pricing_method, pricing_status = _priced_by_rules(
                    matched, price_total, costing_status)
            else:
                # THE MARKUP RUNG — REACHED ONLY BECAUSE NO RULE WAS (#356).
                #
                # This is the else-branch of rule resolution and it stays one.
                # "Base cost -> markup -> final charge" is false for any tenant
                # with pricing rules, and a pipeline that marked up a rule's
                # answer would silently re-price every catalogue in the system.
                # What the rung supplies is a percentage AND its source, which
                # is why it resolves a value here rather than being handed a
                # number to multiply — `_priced_by_markup` says what it does
                # with the three answers it can reach.
                resolved_markup = resolve_markup()
                billed, pricing_method, pricing_status = _priced_by_markup(
                    resolved_markup, computed_micros, costing_status)

        # The receipt records what the engine DID; the columns record what UBB
        # KNOWS. Where the two differ the receipt keeps its resolved components
        # and the amount below is None — see the `_compute` docstring.
        recorded_cost = (computed_micros if costing_status == COSTING_STATUS_KNOWN
                         else None)
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
                    # WHICH INPUT DID NOT ARRIVE, ON THE RECORD RATHER THAN
                    # ONLY ON THE COLUMN (#356). The status says a cost is
                    # unresolved and this says why, which is the difference
                    # between a reader who can fix the configuration and one
                    # who has to guess. It rides here rather than beside the
                    # status because `detail` is what explains a section's
                    # outcome by value, and it is what the recording path now
                    # reads the posting's own column back off — so the record
                    # and the column cannot come to disagree, because there is
                    # one of them.
                    "unresolved_reason": unresolved_reason,
                }),
            pricing=Resolution(
                method=pricing_method, status=pricing_status,
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
            # ⚠ `resolved_markup` IS IN SCOPE HERE AND THE RECORD DOES NOT YET
            # NAME IT (#357). The rung that supplied a markup, and the record
            # its percentage came from, are what a tenant asked "why is this
            # line £36?" has to be able to show — and that cannot be
            # reconstructed afterwards, because the record can be edited. The
            # value reaches this writer carrying its source rather than as a
            # bare number, which is the half that had to happen with the rung;
            # writing it into this section is the ticket that makes a markup
            # charge explicable.
            provenance={"cost_rate_ids": cost_rate_ids,
                        "price_rate_ids": price_rate_ids})
        return pricing_receipt

    @staticmethod
    def price(*, subject, tenant, customer, selectors, measurements, currency,
              caller_provider_cost, caller_billed, as_of=None):
        """The recording path's adapter over :func:`resolve_price`.

        It does two things the seam deliberately does not. It assembles the
        loose arguments the recording input arrives as into one
        :class:`PricingSubject`, and it names the instant for a caller that did
        not: **the clock is read HERE**, once, because a recording with no
        effective moment of its own is being priced as of now and something has
        to say so out loud. Nothing below this line reads one.

        ``selectors`` is the full {provider, event_type, task_type,
        subtask_type, the ten slots} map (Rate.SELECTORS keys) — an absent/""
        value wildcards against a rate that leaves it unpinned.

        ``subject`` is a :class:`~apps.metering.pricing.receipts.ReceiptSubject`
        and is REQUIRED, with no default. A receipt explains one named thing,
        and a default here would hand every caller who omitted the argument one
        subject's answer — the same defect a default column name is, one level
        up. It is an input rather than a stamp applied afterwards, which is why
        the caller generates the row's id before it records the row.
        """
        return costing_of(resolve_price(
            PricingSubject(
                receipt_subject=subject, tenant=tenant, customer=customer,
                selectors=selectors, measurements=measurements or {},
                currency=currency,
                caller_provider_cost=caller_provider_cost,
                caller_billed=caller_billed),
            as_of or timezone.now()))


@dataclass(frozen=True)
class PricingSubject:
    """WHAT IS BEING PRICED — everything configuration-dependent, in one value.

    The resolver takes a subject and an instant, so everything that decides an
    answer other than the instant lives here: who the tenant is, whose price it
    is, what the event named, what it measured, and the two figures a caller may
    state for itself.

    **IT CARRIES THE RECEIPT'S SUBJECT RATHER THAN BEING IT.**
    :class:`~apps.metering.pricing.receipts.ReceiptSubject` is the declared
    IDENTITY of the thing a receipt explains — a typed pair, published, and the
    same value whatever configuration exists. This is that identity plus
    everything resolution reads about it, and none of the rest belongs on a
    record's subject.

    Frozen, because a resolution is a question asked once: a caller that
    re-pointed the subject between the ladder and the receipt would produce a
    record explaining an answer to a different question. ⚠ **That holds the
    BINDINGS and not the containers** — `frozen=True` refuses a new `selectors`
    map, not an edit to the one already there — so it is a statement about this
    value's own fields rather than a guarantee about what a caller may still
    reach through them. Making it the stronger claim would mean copying both
    maps on every recording call, on the hottest write path in the system, to
    defend against a caller that has no reason to do it.
    """

    receipt_subject: ReceiptSubject
    tenant: Any
    customer: Any
    selectors: dict
    measurements: dict
    currency: str
    #: THE SUPPLIER'S OWN FIGURE, where the caller stated it. Whether it may be
    #: stated at all is decided before resolution and has its own refusal.
    caller_provider_cost: Optional[int] = None
    #: THE CUSTOMER PRICE THE CALLER STATED, which is not a rung of the ladder:
    #: it sits above it, and the ladder arrives closed with no caller rung
    #: (#147 §5.1). The request field it comes from is deleted later in this
    #: slice, and the day it is, this is the field that goes with it.
    caller_billed: Optional[int] = None


def resolve_price(subject, as_of):
    """PRICE RESOLUTION IS ONE FUNCTION OF A SUBJECT AND AN INSTANT (#356).

    Returns the Pricing Receipt that explains its answer: the method, the
    amount, the status, the reason where there is one, and the provenance.

    **THE INSTANT IS A PARAMETER AND NO CLOCK IS READ BELOW IT.** That is a live
    bug fix rather than a testing convenience. Resolution keyed on the current
    instant answers for the wrong moment the day a boundary is dated forward: a
    row that faithfully carries a future boundary is not the same as a row that
    is honoured at one, and the difference is invisible until something
    advertises a future effective instant. Everything time-dependent arrives
    through `as_of`; everything configuration-dependent arrives through
    `subject`.

    **WHY THIS IS THE BOUNDARY AND NOT SIX SMALLER ONES.** The four-rung ladder,
    specificity-before-source, markup as a rung rather than a multiplier,
    forward-dated boundaries, the price statuses and the receipt's own shape are
    only observable in combination. Asked through HTTP, each combination costs a
    fixture and puts an endpoint's serialization between the assertion and the
    behaviour; asked here they are one table of cases. It is the only new seam
    this slice introduces, and it would have been required without a test asking
    for it.
    """
    tenant, customer = subject.tenant, subject.customer
    selectors, currency = subject.selectors, subject.currency

    # THE BOOKS ARE SELECTED ONCE PER EVENT, NOT ONCE PER QUANTITY. Selection
    # is two queries and a call prices every quantity the event measured, so
    # asking again per quantity would multiply them by the bag's size on the
    # hottest write path in the system. Nothing about the answer changes: which
    # books are in play is decided by the tenant, the customer, the event's
    # provider and the currency, and a single resolution holds all four fixed.
    books_in_play = {}

    def resolve_card(card_type, measurement_key):
        if card_type not in books_in_play:
            books_in_play[card_type] = PricingService._selected_books(
                tenant, customer, card_type,
                selectors.get("provider") or "", currency)
        return PricingService._resolve_card(
            tenant, customer, card_type, selectors, measurement_key,
            currency, as_of, books=books_in_play[card_type])

    def resolve_declaration():
        """What this event's Event Type declares about cost, or None.

        A function rather than a value so the spine decides *whether* the
        declaration matters, the same way it decides which cards to resolve. A
        caller-supplied figure needs no declaration, and this is a query per
        recording call on the hottest write path in the system — one the spine
        simply never asks for on that branch.
        """
        return cost_declaration(tenant=tenant, key=selectors.get("event_type"))

    def resolve_markup():
        """The markup rung's own answer, WITH the source that supplied it.

        A rung answers a percentage and where it came from, never a finished
        number: the receipt has to be able to say which rung of configuration
        priced an event, and a function that returned the marked-up figure would
        throw that away at the one point it is still known (#357).
        """
        from apps.metering.pricing.services.markup_service import MarkupService
        return MarkupService.resolve(tenant, customer)

    return PricingService._compute(
        subject=subject.receipt_subject, currency=currency,
        effective_at=as_of.isoformat(),
        measurements=subject.measurements,
        caller_provider_cost=subject.caller_provider_cost,
        caller_billed=subject.caller_billed,
        resolve_declaration=resolve_declaration,
        resolve_card=resolve_card, resolve_markup=resolve_markup)


def costing_of(receipt):
    """THE POSTING'S COLUMNS, READ OFF THE RECEIPT THAT DECIDED THEM (#356).

    The receipt is the authority (#148 §3), and this is what makes that true in
    code rather than only in prose: every column the recording path writes is
    read back off the record it stores beside them, so a posting and its receipt
    cannot come to disagree about what the engine concluded. It is an adapter
    and not a second reader of the record's shape — nothing here decides
    anything, and a value it cannot find is a receipt this engine did not build.
    """
    costing, pricing = receipt["costing"], receipt["pricing"]
    return Costing(
        provider_cost_micros=receipt["totals"]["provider_cost_micros"],
        billed_cost_micros=receipt["totals"]["billed_cost_micros"],
        pricing_receipt=receipt,
        costing_status=costing["status"],
        unresolved_reason=costing["detail"]["unresolved_reason"],
        pricing_status=pricing["status"])
