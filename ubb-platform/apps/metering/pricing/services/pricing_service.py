from dataclasses import dataclass
from typing import Any, NamedTuple, Optional

from django.db.models import Q
from django.utils import timezone

from apps.metering.pricing.models import CostBook, PricingBook, Rate, TaskPrice
from apps.metering.pricing.receipts import (
    MARKUP_TERMS_KEY, ReceiptSubject, Resolution, build_receipt,
)
from apps.platform.event_types.costing import cost_declaration
from apps.platform.plans.queries import get_pricing_book_for_customer
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
    TASK_TYPE_KIND_SUBTASK,
    TASK_TYPE_KIND_TASK,
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


def _markup_terms(markup, basis_micros):
    """WHAT THE MARGIN WAS, BY VALUE — the percentage and what it was taken over.

    The two numbers a reader holding only the receipt needs to redo the sum,
    which is the whole content obligation applied to the path that produces most
    of this system's prices (#357, #153 §12.4). The record the percentage came
    from can be edited or withdrawn, so re-reading it later is not an answer;
    `receipts.REQUIRED_MARKUP_KEYS` is what refuses a margin that arrives
    without them.

    ⚠ **A THIRD TERM LEFT WITH THE RECORDS THAT COULD SUPPLY ONE (#369).** A
    flat per-event addend was written here because the customer-override record
    and the plan catalog each carried one; both are deleted, and the rung that
    remains has no such column, so a receipt carrying the term would be
    recording a zero nobody declared.

    **THE BASIS IS RECORDED RATHER THAN LEFT TO THE TOTALS.** They coincide for
    a cost UBB resolved and they do not for one an Event Type declares does not
    exist: that nulls `totals.provider_cost_micros` and is still a genuine zero
    to take a margin over, so a reader taking the basis from the totals would
    find nothing to multiply on exactly the case where the arithmetic is least
    obvious.
    """
    return {"micro_percent": markup.markup_micro_percent,
            "basis_micros": basis_micros}


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

    ⚠ **ONE OF THE TWO RETIRED SPELLINGS BELOW IS PAID HERE AND THE OTHER IS
    NOT, AND THE INHERITED SENTENCE SAID OTHERWISE.** It read "the ticket that
    renames the rule's arithmetic shape owns both". It owns one. The shape's key
    is the rate's column name, so it follows `Rate.STRUCTURE_COLUMN` and moves
    with the rename — the constant exists precisely so a reader tracks the
    column instead of going quietly vacuous on the day it lands.

    The QUANTITY key does not, and the difference is mechanical rather than a
    preference. That word is a retired **sense**, not a retired term: it is not
    sweep input, it holds no ledger seat, and no slice-4 entry counts it. So
    re-spelling it here would be a change to the shape of a stored record with
    no ticket behind it, in a commit whose subject is a different column — and
    it would move the sense's own evidence block for a word this slice does not
    own. It stays, and the ratchet's list is where it is claimed.
    """
    return {
        "measurement_key": measurement_key,
        "units": quantity,
        # KEY THROUGH THE CONSTANT, VALUE OFF THE COLUMN — so the record's key
        # and the column it holds cannot be renamed apart. Rename the column and
        # this raises `AttributeError` on the first call rather than writing a
        # component under a key nothing reads.
        Rate.STRUCTURE_COLUMN: card.rate_structure,
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
    #: for the record it is (ADR-0006) — and since #370 the column and the wire
    #: key it is stored and published under carry that same name, which is what
    #: ADR-0006 §2 asks for: one public name per concept. This field was named
    #: first and the column came to it.
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
    def _matching_rules_across(books, book_column, selectors, measurement_key,
                               currency, as_of):
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
        used to short-circuit at one. One `__in` asks once instead, and the
        source each rule carries is read back off the book it belongs to.

        ⚠ **`book_column` IS WHICH POINTER TO FOLLOW, NOT WHICH KIND TO ASK
        FOR (#368).** A rule points at a Pricing Book or at a cost book, two
        separate tables, so a caller resolving prices hands `"pricing_book"`
        and a caller resolving costs hands `"cost_book"` — and every book in
        `books` is already of that kind, because selection is what chose them.
        This is not the discriminator coming back: the old code asked ONE table
        twice with a different value each time, and there was a value on a row
        that could be wrong. There is no value here to be wrong about; there
        are two columns, and a caller reads the one it means.

        ⚠ **AND THE RESULT IS RETURNED IN BOOK-SELECTION ORDER, NOT IN ROW
        ORDER.** One query means the database decides what order the rules come
        back in, and the ranking above is a STABLE sort — so a tie it cannot
        break would silently be decided by the query plan, differently on
        different days. Ordering the candidates by the book they came from
        restores the one answer a tenant can predict: the selection functions
        put the narrowest book first.

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
        book_id_attribute = f"{book_column}_id"
        qs = Rate.objects.filter(
            measurement__code=measurement_key,
            currency=currency, valid_from__lte=as_of,
            **{f"{book_column}__in": list(source_of)},
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
        for name in Rate.SELECTORS:
            qs = qs.filter(Q(**{name: selectors.get(name) or ""}) | Q(**{name: ""}))
        return sorted(((rule, source_of[getattr(rule, book_id_attribute)])
                       for rule in qs),
                      key=lambda pair: position_of[
                          getattr(pair[0], book_id_attribute)])

    @staticmethod
    def _override_book(tenant, customer):
        """THE BOOK HOLDING THIS CUSTOMER'S OWN RULES, IF THEY HAVE ONE (#361).

        A tenant honouring a negotiated deal gives one customer their own
        pricing rules, and this is where they live: a Pricing Book carrying
        that customer, whose every rule is one of that customer's own. There is
        at most one, held by the constraint named on the model
        (`PricingBook.Meta.constraints`).

        **NOT A SUBSTITUTE FOR A BOOK, AND #362 IS WHERE THAT BITES.** An
        override is a rule at a rung *inside* resolution; it is not a way for a
        customer to have pricing without a book being selected for them. A
        customer with overrides and nothing else resolves their overrides and
        nothing else — a partial catalogue, not a complete one — and #362's
        required `Plan.pricing_book` is what makes that state unreachable.

        ⚠ **THE COST SIDE DOES NOT ASK THIS QUESTION AT ALL ANY MORE (#368).**
        It used to, and answered `None` from a discriminator check on the first
        line — a branch inside a shared function. A cost book has no customer
        column, so a supplier's prices cannot acquire a customer and there is
        nothing for the cost path to ask: `_selected_cost_books` simply does
        not call this. The special case is gone rather than moved.
        """
        if customer is None:
            return None
        return PricingBook.objects.filter(
            customer=customer, tenant=tenant).first()

    @staticmethod
    def _the_plans_book(tenant, customer):
        """THE BOOK THIS CUSTOMER'S PLAN PRICES THEM FROM (#362, #151 §7.2).

        Assigning a plan is all it takes to price a customer: the plan names a
        Pricing Book, the reference is `NOT NULL`, and this is where that
        becomes a price.

        ⚠ **AND IT IS NOW THE ONLY WAY A BOOK IS SELECTED *FOR* A CUSTOMER
        (#368).** The record that assigned a book to a customer directly is
        deleted in the same commit as this sentence. #362 said this rung is
        what made that deletion possible; this is that deletion, and the rung
        below it in the old code — `_assigned_book` — is gone rather than
        deprecated.

        **THE READ CROSSES ADR-001's `queries.py` CHANNEL, AND METERING NEVER
        IMPORTS THE PLAN.** The plan catalog is the kernel's; the contract
        returns plain data and this app loads the book from its own models by
        the id it answers. A plan the tenant has archived answers nothing,
        which the read contract decides rather than this line.

        **`FROM_THE_SELECTED_BOOK`, NOT THE CUSTOMER'S OWN RUNG, AND THE
        DIFFERENCE IS LOAD-BEARING.** A plan's book is a catalogue shared by
        every customer on the plan — the override book above holds rules
        written for ONE customer. Ranking it at the customer's-own rung would
        put it level with an override, where `ladder_rank`'s last key is
        `valid_from`: a tenant repricing the plan's catalogue would then
        out-rank a negotiated deal agreed before it, silently deleting the
        override #361 exists to honour. At this rung an override beats it on
        SOURCE at every specificity, whenever it was written.

        It is appended ahead of the tenant's default book, which is the
        narrowest-first order the list has: a plan's book is a statement about
        the customers on that plan, a default is the tenant's answer for
        everybody.
        """
        if customer is None:
            return None
        book_id = get_pricing_book_for_customer(tenant.id, customer.id)
        if book_id is None:
            return None
        return PricingBook.objects.filter(id=book_id, tenant=tenant).first()

    @staticmethod
    def _default_pricing_book(tenant):
        """THE TENANT'S ANSWER FOR EVERYBODY — one book, not one per provider.

        ⚠ **THE PROVIDER LEFT THIS LOOKUP WITH THE COLUMN (#368).** A Pricing
        Book is pinned to no provider, because a tenant's price for a unit of
        work does not change because they switched supplier — so the
        provider's-own-default / provider-agnostic-default pair that
        `_selected_cost_books` still has is not a pair here. There is one
        default Pricing Book per tenant and `uq_pricing_book_one_default` is
        what says so. A rule that wants to price one provider's work
        differently still pins `provider` as a SELECTOR, which is where that
        distinction belongs: it is a property of the rule, not of the book.
        """
        return PricingBook.objects.filter(tenant=tenant, is_default=True).first()

    @staticmethod
    def _default_cost_book(tenant, provider, currency):
        return CostBook.objects.filter(
            tenant=tenant, provider_key=provider or "",
            currency=currency, is_default=True).first()

    @staticmethod
    def _selected_pricing_books(tenant, customer, the_customers_own=True):
        """WHICH PRICING BOOKS A CUSTOMER'S PRICE MAY BE RESOLVED FROM.

        Selection and resolution are two steps and this is the first (#147
        §5.3). A Pricing Book becomes readable for one event in exactly three
        ways: it holds the customer's own rules, the customer's PLAN prices
        from it (#362), or it is the tenant's default. Anything else — a book
        nobody is on, another customer's book — is unreachable, and no rule
        inside it can be the answer however well it matches.

        ⚠ **THERE WERE FOUR WAYS AND NOW THERE ARE THREE (#368).** The fourth
        was a record assigning a book to a customer, and it is deleted: every
        customer on a plan already reaches a book through `_the_plans_book`,
        and #362's required reference is what makes "on a plan" the ordinary
        state rather than a lucky one.

        ⚠ **`the_customers_own=False` ANSWERS A DIFFERENT QUESTION AND ONLY ONE
        CALLER ASKS IT (#361):** *what would this customer be charged if they
        had no override* — the inherited rule, which a console offers as the
        starting point for writing one. It is a READ and it prices nothing:
        every path that decides what a customer is actually charged takes the
        default, so an override cannot be skipped by a caller who forgot an
        argument.

        Returns `(source, book)` pairs. `ladder_rank` is what orders the rules
        they hold — but the ORDER of this list is load-bearing all the same,
        and it is the narrowest book first: two rules a tenant made equally
        specific from the same source are separated by nothing else, and the
        stable sort over that tie keeps whichever book came back first here.

        ⚠ **EACH BOOK APPEARS EXACTLY ONCE, AND THE FIRST WAY IT WAS REACHED IS
        THE ONE THAT COUNTS.** A plan can name the very book that is also the
        tenant's default, so the same rows are reachable twice; a second entry
        for it would let the ranking read one source's rules as another's.
        """
        books, seen = [], set()
        the_customers = (PricingService._override_book(tenant, customer)
                         if the_customers_own else None)
        if the_customers is not None:
            books.append((FROM_THE_CUSTOMERS_OWN_RULES, the_customers))
            seen.add(the_customers.id)
        # THE PLAN'S BOOK, AHEAD OF THE TENANT'S DEFAULT AND AT ITS SOURCE
        # (#362). A plan's book is a catalogue the tenant chose for the
        # customers on that plan, so it is the selected book rather than one of
        # the customer's own — see `_the_plans_book` for why that rung matters
        # rather than being a label — and it goes first because it is the
        # narrower statement: a default is the tenant's answer for everybody.
        the_plans = PricingService._the_plans_book(tenant, customer)
        if the_plans is not None and the_plans.id not in seen:
            books.append((FROM_THE_SELECTED_BOOK, the_plans))
            seen.add(the_plans.id)
        default = PricingService._default_pricing_book(tenant)
        if default is not None and default.id not in seen:
            books.append((FROM_THE_SELECTED_BOOK, default))
        return books

    @staticmethod
    def _selected_cost_books(tenant, provider, currency):
        """WHICH COST BOOKS THIS EVENT'S SUPPLIER COST MAY BE RESOLVED FROM.

        A cost book is the tenant's record of what one supplier charges, so
        selection here asks about the supplier and the currency and about
        nothing else — no customer, no plan, no override. A supplier's price
        does not change because of who UBB's tenant sells to.

        **THE PROVIDER-AGNOSTIC DEFAULT IS SELECTION, NOT A THIRD TIER.** A ""
        `provider_key` book is the tenant's provider-agnostic cost book (D3's
        headline fix applied at the book layer), so it is in play alongside the
        provider's own default rather than after it. It used to be reached by
        falling through when the provider's book held no matching rule, which
        is the cross-book walk #147 §5.3 deletes; ranking both books' rules
        together answers the same events the same way for a better reason,
        because a rule pinning the provider outranks one that does not on
        SPECIFICITY.

        A LIST AND NOT A SET, because the order is load-bearing: a set's
        iteration order would decide ties between the provider's own book and
        the provider-agnostic one, differently between processes.
        """
        books, seen = [], set()
        for provider_key in ([provider, ""] if provider else [""]):
            default = PricingService._default_cost_book(
                tenant, provider_key, currency)
            if default is not None and default.id not in seen:
                books.append((FROM_THE_SELECTED_BOOK, default))
                seen.add(default.id)
        return books

    @staticmethod
    def _rank_and_take_one(books, book_column, selectors, measurement_key,
                           currency, as_of):
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

        ⚠ **ONE LADDER, TWO CALLERS, AND NO KIND WORD ANYWHERE IN IT (#368).**
        The ranking is genuinely shared — specificity before source, no
        fallthrough, the as-of instant — and it always was. What used to be
        shared and should not have been is the SELECTION: one function asked
        one table twice with a different discriminator value each time. Its two
        halves are now `_selected_pricing_books` and `_selected_cost_books`,
        which read different tables, and this takes whichever they chose.
        """
        candidates = PricingService._matching_rules_across(
            books, book_column, selectors, measurement_key, currency, as_of)
        if not candidates:
            return None
        candidates.sort(key=lambda pair: ladder_rank(*pair), reverse=True)
        return candidates[0][0]

    @staticmethod
    def resolve_the_price_rule(tenant, customer, selectors, measurement_key,
                               currency, as_of, books=None):
        """The rule that says what this quantity SELLS FOR, or `None`.

        ``books`` lets a caller resolving MANY quantities for one event select
        them once instead of once per quantity — which is what
        :func:`resolve_price` does, and the reason selection and ranking are two
        steps rather than one. It is configuration and not a clock, so
        re-reading it when a caller has not supplied it is a default rather than
        an override.
        """
        if books is None:
            books = PricingService._selected_pricing_books(tenant, customer)
        return PricingService._rank_and_take_one(
            books, PricingBook.REFERENCE_COLUMN, selectors, measurement_key,
            currency, as_of)

    @staticmethod
    def resolve_the_agreed_price(tenant, customer, task_type, kind, as_of,
                                 books=None):
        """The line that says what one delivered unit of work of this kind
        SELLS FOR, or `None` (#415, #139 §2.4).

        The whole-work twin of `resolve_the_price_rule` above, and deliberately
        a twin rather than a parameter on it: the two answer different
        questions about different tables, and a matched work-level line
        switches the event-level ladder OFF for that unit of work rather than
        competing with it inside one ranking.

        `kind` is the ALTITUDE the start is at, and it is a lookup key rather
        than a ranking one: a line names the declaration it prices, and a
        declaration's identity is `(kind, key)`. Asking for the altitude is what
        lets #139 §3.3's refusal fire on the row it actually names — a line
        written against a declaration meant for contained work — instead of on
        any line for that word, which would stop a priced kind of work ever
        running as a step of itself. See `TaskPrice.kind`.

        **THE RANKING HAS ONE KEY WHERE THE RATE SIDE HAS THREE, AND THE TWO
        THAT ARE MISSING ARE MISSING FOR A REASON.** `ladder_rank` ranks a rate
        on how specifically it names the event, then on where it came from,
        then on when it opened. A work-level line pins exactly one thing — the
        declaration it prices — so every candidate is equally specific and
        there is nothing for the major key to say; #139 §2.4 states it directly
        as *the work ladder is one step, not three.* What is left is SOURCE: the
        customer's own book beats a book merely selected for them, which is
        what makes a negotiated price a negotiated price. `valid_from` stays as
        the last key for the same reason it is the rate side's last key — two
        lines a tenant made from one source, one still open and one opening
        later, are separated by which decision was the later one.

        ⚠ **THE ORDER IS IMPOSED, NOT INHERITED FROM THE QUERY PLAN.** One
        `__in` over every book in play means the database decides what order
        the rows come back in, and the sort below is STABLE — so a tie it
        cannot break would silently be settled by the plan, differently on
        different days. Ordering the candidates by the book they came from
        first restores the one answer a tenant can predict, because the
        selection function puts the narrowest book first. #356 paid for this on
        the rate side.

        **`as_of` IS THE INSTANT THE UNIT OF WORK STARTS, AND IT IS THE ONLY
        TIME THIS QUESTION IS ASKED.** The answer is pinned onto the unit of
        work in the same transaction, so a later reprice cannot move it. Why
        that differs from the cost side, which resolves at each posting's own
        timestamp, is argued at `work.Task.agreed_price_micros`.

        Returns the LINE and not the amount, so the caller can record which
        line answered and out of which book — which is what a Charge carries
        (#416), and what makes a resolved price reproducible from the record
        rather than by re-resolving today's configuration.
        """
        if books is None:
            books = PricingService._selected_pricing_books(tenant, customer)
        if not books:
            return None
        source_of = {book.id: source for source, book in books}
        position_of = {book.id: index for index, (_, book) in enumerate(books)}
        candidates = sorted(
            TaskPrice.objects.filter(
                tenant=tenant, kind=kind, task_type=task_type,
                valid_from__lte=as_of, pricing_book__in=list(source_of),
            ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=as_of)),
            key=lambda line: position_of[line.pricing_book_id])
        if not candidates:
            return None
        candidates.sort(
            key=lambda line: (source_of[line.pricing_book_id], line.valid_from),
            reverse=True)
        return candidates[0]

    @staticmethod
    def resolve_the_cost_rule(tenant, selectors, measurement_key, currency,
                              as_of, books=None):
        """The rule that says what this quantity COST, or `None`.

        No customer parameter, and its absence is the statement: a cost book is
        selected by supplier and currency, so who the tenant sells to cannot
        reach this answer. The old shared resolver took a customer and threw it
        away on the cost side, one `if` at a time.
        """
        if books is None:
            books = PricingService._selected_cost_books(
                tenant, selectors.get("provider") or "", currency)
        return PricingService._rank_and_take_one(
            books, CostBook.REFERENCE_COLUMN, selectors, measurement_key,
            currency, as_of)

    @staticmethod
    def the_rule_a_customer_inherits(*, tenant, customer, selectors,
                                     measurement_key, currency, as_of):
        """THE RULE THIS CUSTOMER WOULD GET IF THEY HAD NO OVERRIDE (#361).

        What a client needs to offer *create an override from the inherited
        rule*: the rule as it stands for this customer with their own book
        taken out of the selection, so a console can show the method and the
        current value it is about to replace.

        **THE SAME LADDER, ONE RUNG SHORTER.** It is `resolve_the_price_rule`
        over the books `_selected_pricing_books` returns without the customer's
        own, rather than a second resolution written beside the first — so specificity before
        source, the absence of fallthrough between books and the as-of instant
        are all the ones that decide the real price, and the answer a tenant is
        shown cannot drift from the answer they are overriding.

        Answers `None` where nothing is inherited, which is a real state and
        not an error: a quantity no book in play prices falls to the markup
        rung, and a client creating an override there is starting from nothing
        rather than from a rule.
        """
        return PricingService.resolve_the_price_rule(
            tenant, customer, selectors, measurement_key, currency, as_of,
            books=PricingService._selected_pricing_books(
                tenant, customer, the_customers_own=False))

    @staticmethod
    def _compute(*, subject, currency, effective_at, measurements,
                 caller_provider_cost,
                 resolve_declaration, resolve_the_cost_rule,
                 resolve_the_price_rule, resolve_markup):
        """The ONE compute spine (#112): cost → status → price → markup rung,
        returning the receipt. ``resolve_price`` is this spine under its four
        parameters — ``resolve_the_cost_rule(measurement_key)``,
        ``resolve_the_price_rule(measurement_key)``, ``resolve_declaration()``
        and ``resolve_markup()`` — and it is the only rider left since #239
        deleted the accept-time estimate that was the second. The
        parameterisation stays: it is what kept the two in agreement by
        construction, and what a future second rider would use rather than
        forking a pricing body.

        ⚠ **ONE RULE RESOLVER BECAME TWO, AND THAT IS THE SPLIT ARRIVING HERE
        (#368).** The single ``resolve_card`` took the kind word as its first
        parameter and carried it into the spine's own signature, so the two
        branches below — which are *cost* and *price*, not two values of one
        thing — read as one call made twice. They are two calls now, to two
        resolvers over two tables, and the string is gone.

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
        configuration-dependent arrives through the two rule resolvers and
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
                card = resolve_the_cost_rule(measurement_key)
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
        # THE BASIS A MARGIN WOULD BE TAKEN OVER, NAMED ONCE. The rung that
        # computes the amount and the terms that record it read the same local,
        # so a receipt cannot come to say the margin was taken over a figure the
        # arithmetic did not use.
        #
        # ⚠ AND THE SHORT-CIRCUIT ABOVE THE LADDER IS GONE (#365). A
        # caller-stated price was never a rung — #147 §5.1 ratified a ladder
        # that arrives CLOSED, with no caller rung on it — it was a branch above
        # the whole thing, `if caller_billed is not None`, that answered before
        # any rule was consulted. So a figure worked out somewhere else and
        # pasted onto one call outranked every rule the tenant had written, and
        # went stale the moment the supplier moved. It is deleted with the
        # request field it came from, and `PricingSubject` no longer carries
        # one, so *a price comes from configuration* is a property of what this
        # function can be handed rather than of which branch it happens to take.
        resolved_markup, markup_basis = None, None
        price_total, matched = 0, []
        for measurement_key, units_val in sorted(measurements.items()):
            card = resolve_the_price_rule(measurement_key)
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
            resolved_markup, markup_basis = resolve_markup(), computed_micros
            billed, pricing_method, pricing_status = _priced_by_markup(
                resolved_markup, markup_basis, costing_status)

        # WHAT THE MARKUP RUNG PUT ON THE RECORD, AND THE TWO PLACES IT GOES
        # (#357). The percentage and the basis are TERMS and ride in the price
        # section's detail by value; the rung and the record are a
        # CROSS-REFERENCE and ride in `provenance`, which carries ids and
        # nothing a reader could take a figure from.
        #
        # ⚠ THEY ARE NOT WRITTEN ON THE SAME CONDITION, AND THAT IS THE
        # RECEIPT'S OWN RULE RATHER THAN A CHOICE MADE HERE. The terms are how
        # an amount was arrived at, so they are present exactly when a method
        # is — the same condition the boundary already enforces for the method
        # and the amount. The provenance is which records resolution READ, so
        # it names the rung wherever the rung was consulted, including where
        # the charge was waived over a cost nobody learned: a receipt that
        # named nothing there would say the tenant had configured nothing,
        # which is the same mistake the price rules' `price_rate_ids` avoids by
        # keeping a rule that matched and could not compute.
        price_detail, markup_provenance = {}, {}
        if resolved_markup is not None:
            markup_provenance = {
                MARKUP_TERMS_KEY: resolved_markup.as_provenance()}
            if pricing_method is not None:
                price_detail = {
                    MARKUP_TERMS_KEY: _markup_terms(resolved_markup,
                                                    markup_basis)}

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
                    # ⚠ THE COLUMN HAS LANDED AND THIS LINE STILL DOES NOT
                    # READ IT (#415), WHICH IS A NARROWER CLAIM THAN THE ONE
                    # THAT USED TO BE HERE. This comment said there was "no
                    # column anywhere to read it from" and that this was the
                    # line that would read it when one arrived; `Task
                    # .pricing_mode` now exists and a unit of work really can
                    # be sold at one agreed price.
                    #
                    # What is written here is still ACCURATE, because it
                    # records what the engine DID rather than what the unit of
                    # work is: metered revenue is not yet replaced for a
                    # fixed-price unit of work, so every event this function
                    # prices really was priced event by event. The ticket that
                    # makes those postings `not_applicable` is the one that
                    # changes both — and it needs the unit of work threaded
                    # into `PricingSubject`, which does not carry it, so this
                    # is a wiring change rather than a one-line read. Same
                    # shape as `usage/measurements.py` and the posting kind it
                    # is waiting on.
                    "pricing_mode": PRICING_MODE_EVENT_PRICED,
                    **price_detail}),
            provenance={"cost_rate_ids": cost_rate_ids,
                        "price_rate_ids": price_rate_ids,
                        **markup_provenance})
        return pricing_receipt

    @staticmethod
    def price(*, subject, tenant, customer, selectors, measurements, currency,
              caller_provider_cost, as_of=None):
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
                caller_provider_cost=caller_provider_cost),
            as_of or timezone.now()))


#: WHY A START AGAINST A KIND OF WORK SOLD AT ONE AGREED PRICE IS REFUSED
#: (#415, #151 §17, #139 §3.3).
#:
#: Named here rather than spelled at the composition layer for the reason
#: `risk_service.CONCURRENCY_LIMIT` and `reasons.TASK_LIMIT` are named where
#: they are produced: a test comparing against its own copy of a string passes
#: whatever this module decides to answer, while one importing the symbol goes
#: red the day the answer moves. The words are the problem codes the tenant
#: contract publishes, which is why they are the two spellings and not a pair
#: of internal synonyms.
AGREED_PRICE_UNRESOLVED = "fixed_task_price_unresolved"
AGREED_PRICE_ON_CONTAINED_WORK = "fixed_task_price_on_contained_work"


class AgreedPriceRefused(ValueError):
    """A start refused by the price its kind of work is sold at.

    A `ValueError` subclass and not a `Problem`, on the split #414 was graded
    on: this module is a PRODUCT and the error dialect belongs to the
    composition layer (ADR-001, `docs/conventions/django-patterns.md` §API).
    What is decided here is the rule; `api/v1/task_endpoints.py` renders it.
    """

    def __init__(self, reason, detail):
        self.reason = reason
        super().__init__(detail)


def determine_the_agreed_price(*, tenant, customer, task_type, contained,
                               as_of, tenant_bills_through_ubb):
    """THE LINE A UNIT OF WORK PINS AT START, or `None`, or a refusal (#415).

    Called only where the declared kind of work is sold at one agreed price;
    a per-event kind of work has no question to ask here.

    ⚠ **IT ANSWERS WITH THE LINE AND NOT THE AMOUNT**, so the caller pins both
    the number and WHICH line produced it. #139 §2.3 requires a charge to name
    the matched line so the amount is *"reproducible from the record rather
    than by re-resolving today's config"*, and re-resolving is not available
    later on any terms: which books are even in play depends on the customer's
    plan, which moves. The identity has to be captured at the one instant both
    it and the number are known, which is this one.

    ⚠ **MARKUP NEVER APPLIES, AND THE PROOF IS THAT NOTHING BELOW CALLS IT**
    (#139 §2.5). The markup rung resolves to a `ResolvedMarkup`, whose
    `applied_to(provider_cost_micros)` is a function of provider cost ALONE —
    so applying it to an agreed price would yield *the price, plus a percentage
    of this unit's COGS*, a number that moves with cost and destroys the
    premise the tenant sold on. All four rungs are bypassed: the customer's
    own, their plan's, the tenant default, and none. A customer on a plan with
    markup therefore runs two regimes at once, deliberately — their loose
    metered events get the plan's markup and their agreed-price work gets the
    flat number.

    ⚠ **AND NO PRICING METHOD IS RECORDED, BECAUSE THE PRICE WAS AGREED AND NOT
    DERIVED** (spec §9). `Rate.pricing_method` is nullable with exactly two
    values and a fixed price is not a third: null already means *this price was
    not derived*, which is exactly what an agreed number is. Adding a third
    value would put the same fact in two places and let them disagree.

    **WHOLE UNITS OF WORK ONLY** (#139 §3.3). Contained work never pins a price
    of any kind: the containing unit is already the whole-work altitude, its
    rollup is unconditional, and a parent's close cascades over its children
    with no outcome declared per child — so a priced step would fire a fan of
    charges nobody asserted. A line written against a contained kind of work is
    refused LOUDLY rather than ignored, because the alternative leaves a tenant
    with configuration that silently does nothing and springs to life the day
    somebody removes the parent's own price.

    ⚠ **THE POSTURE DECIDES WHETHER THE *UNRESOLVED* REFUSAL IS LIVE, AND ONLY
    THAT ONE** (#151 §18, spec §9). For a tenant that does not bill through
    UBB, `fixed` and `event_priced` are behaviourally identical at this gate:
    the declaration is recorded and inert, and refusing their work for a
    pricing gap would refuse it over revenue nobody is collecting. It becomes
    live the day they enable billing, which is a start-gate refusal in disguise
    and why the console owes them that sentence beside the control before that
    day. A price that DOES resolve is still pinned for them, because their
    margin reporting is what the declaration was recorded for.

    The contained-work refusal is NOT posture-conditioned: a line written
    against contained work is a mistake in the tenant's own book whatever they
    bill, and #139 §3.3's whole objection to ignoring it is that the tenant
    ends up with configuration that does nothing.

    Returns the `TaskPrice`, or `None` where nothing is pinned.
    """
    kind = TASK_TYPE_KIND_SUBTASK if contained else TASK_TYPE_KIND_TASK
    line = PricingService.resolve_the_agreed_price(
        tenant, customer, task_type, kind, as_of)
    if contained:
        if line is not None:
            raise AgreedPriceRefused(
                AGREED_PRICE_ON_CONTAINED_WORK,
                f"this customer's book prices {task_type!r} as CONTAINED work, "
                f"and one agreed price buys a whole unit of work; withdraw "
                f"that line and price the kind of work that contains this one "
                f"instead")
        return None
    if line is None:
        if tenant_bills_through_ubb:
            raise AgreedPriceRefused(
                AGREED_PRICE_UNRESOLVED,
                f"{task_type!r} is sold at one agreed price and this "
                f"customer's book has no line for it, so there is no price to "
                f"pin; add one before starting work of this kind")
        return None
    return line


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
    # ⚠ THERE IS NO CUSTOMER PRICE ON THIS VALUE, AND THAT IS THE INVARIANT
    # RATHER THAN AN OMISSION (#365). #147 §5.1's ladder arrives closed, with no
    # caller rung on it; the field that used to sit here was not a rung but an
    # answer given ABOVE the ladder, before any of it was consulted. The request
    # field it arrived on is deleted and this field went with it, exactly as the
    # sentence that stood here said it would. What an event is priced at is now
    # decided from this subject and the configuration in force at its instant —
    # so the price is UBB's answer, and there is nothing a caller can put in
    # this value to make it theirs.
    #
    # Do not reintroduce one "for convenience", under this name or a softer one.
    # #151 §9.2 records why the sentence is written down: it is small, it looks
    # helpful, and the argument against it lives three documents away.


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
    # costs a handful of queries — at least one per way a book can be reached,
    # and the plan's costs two (the read contract, then the book) — while a
    # call prices every quantity the event measured, so asking again per
    # quantity would multiply them by the bag's size on the hottest write path
    # in the system. Nothing about the answer changes: which
    # books are in play is decided by the tenant, the customer, the event's
    # provider and the currency, and a single resolution holds all four fixed.
    # Two cells rather than one keyed store, because a key is a kind word and
    # a kind word in this module is what the slice spent itself deleting. They
    # start as `None` and not as `[]`: a selection that legitimately finds no
    # book is a result worth keeping, and a falsy test would re-run it once per
    # quantity — which is the whole cost this memo exists to avoid.
    selected_cost_books = None
    selected_pricing_books = None

    def resolve_the_cost_rule(measurement_key):
        nonlocal selected_cost_books
        if selected_cost_books is None:
            selected_cost_books = PricingService._selected_cost_books(
                tenant, selectors.get("provider") or "", currency)
        return PricingService.resolve_the_cost_rule(
            tenant, selectors, measurement_key, currency, as_of,
            books=selected_cost_books)

    def resolve_the_price_rule(measurement_key):
        nonlocal selected_pricing_books
        if selected_pricing_books is None:
            selected_pricing_books = PricingService._selected_pricing_books(
                tenant, customer)
        return PricingService.resolve_the_price_rule(
            tenant, customer, selectors, measurement_key, currency, as_of,
            books=selected_pricing_books)

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
        return MarkupService.resolve(tenant)

    return PricingService._compute(
        subject=subject.receipt_subject, currency=currency,
        effective_at=as_of.isoformat(),
        measurements=subject.measurements,
        caller_provider_cost=subject.caller_provider_cost,
        resolve_declaration=resolve_declaration,
        resolve_the_cost_rule=resolve_the_cost_rule,
        resolve_the_price_rule=resolve_the_price_rule,
        resolve_markup=resolve_markup)


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
