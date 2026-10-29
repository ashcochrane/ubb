from functools import cache
from uuid import uuid4

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.metering.pricing.models import (
    CHANGE_REPRICE, LINE_RATE, CostBook, PricingBook, Rate,
    TaskPrice, TenantDefaultMarkup)
from apps.metering.pricing.receipts import (
    ReceiptSubject, Resolution, build_receipt)
from apps.metering.pricing.services.book_service import BookService
from apps.metering.pricing.services.pricing_service import (
    PRICING_ENGINE_VERSION, PricingSubject, resolve_price)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import Measurement
from apps.platform.event_types.tests._helpers import (
    declares_a_caller_supplied_cost, declares_a_quantity,
    publishes_what_it_names)
from apps.platform.plans.services import PlanService
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
    PRICING_STATUS_KNOWN,
)

#: The registry concept whose retired spellings name the container's old kind
#: and its old noun (`domain-vocabulary/concepts/retired.yaml`).
_THE_BOOKS_OWN_NAME = "pricing_book_name"


def _retired_aliases(concept_file, concept):
    """The registry's retired spellings of ``concept``, through the platform
    suite's one reader of them (`api/v1/tests/_helpers.retired_aliases`).

    Imported here rather than at the top because that module imports this one:
    the call is what needs it, and only the cases that ask pay for it."""
    from api.v1.tests._helpers import retired_aliases
    return retired_aliases(concept_file, concept)


@cache
def retired_kind_column():
    """The kind word the split deleted — DERIVED, never spelled (#374).

    Three modules assert that this column reaches neither entity, neither
    rule and neither the wire, and a `not in` assertion has to name its subject
    somehow. Writing the token would put it back over a ledger entry that
    reached ZERO, so it is read off the document that RETIRED it — technique 1
    of `docs/conventions/coding-standards.md`'s three.

    **READ OFF THE REGISTRY SINCE THE CUTOVER (#190).** It was read off the
    migration that deleted it until the squash deleted that migration; the
    registry is where the word is still legitimately written, and the
    platform suite reads retired spellings there and nowhere else (the
    `retired_aliases` reader beside the composition layer's tests).

    **HOW IT IS PICKED OUT, AND WHY BY MEANING RATHER THAN BY POSITION.** The
    Pricing Book's name retired four spellings. Three are names the container
    itself went by — a book of costs, of prices, of rates. The fourth named its
    KIND, and a kind column is spelled `<noun>_type` throughout this tree
    (`event_type`, `task_type`, `subject_type`). So it is the one retired
    spelling ending that way, and the one-element unpack is what fails loudly
    if that ever stops picking out exactly one.

    ⚠ **A FUNCTION AND NOT A MODULE CONSTANT.** Every pricing test imports this
    file, so computing the answer at import time would put a registry read on
    the collection path of the entire app's suite. Deferred and cached, the
    blast radius is the assertions that actually ask.
    """
    (kind,) = [alias for alias in _retired_aliases("retired",
                                                   _THE_BOOKS_OWN_NAME)
               if alias.endswith("_type")]
    return kind


@cache
def retired_container_noun():
    """The noun the container went by before the split — DERIVED (#374).

    Two claims need it and neither may spell it: the audit acts that ceased
    with the container are refused, and the rate no longer sits on the table
    named for the container (G9). Read off the registry, which holds it twice,
    and that is how it is picked out by meaning rather than by position: it is
    the one retired spelling of the Pricing Book's name that the registry ALSO
    retired audit actions under. The other spellings of the book's name were
    never an audit noun, and the other retired audit nouns were never a name of
    the book — the one-element unpack fails loudly if either side moves.
    """
    nouns = {action.partition(".")[0]
             for action in _retired_aliases("governance", "audit_action")}
    (noun,) = nouns & set(_retired_aliases("retired", _THE_BOOKS_OWN_NAME))
    return noun

#: WHICH QUANTITY A RATE PRICES WHEN THE FIXTURE NEVER SAID (#326).
#:
#: Most callers here name one; the ones that do not are asking for "a rate" and
#: are about something else entirely — an effective moment, a book, a slot. They
#: used to get the empty string, which is not a name any event carries, so their
#: rate matched nothing and that was invisible and harmless. It is no longer
#: writable: a rate names a DECLARED quantity and "" is not one. This is the
#: same nothing, said out loud — a real declaration, under a name no event in
#: this repository measures, so those fixtures keep resolving exactly as they
#: did rather than quietly starting to match a posting.
UNMEASURED_QUANTITY = "a_quantity_no_event_measures"


def _the_quantity_it_prices(tenant, fields, *, event_type=None, provider=None):
    """The declared quantity a rule prices, put in `fields`, and the Event
    Type it pins published with it.

    **A CALLER STILL SAYS `measurement_key=` AND STILL NEVER SEES A COLUMN
    (#326).** The rate holds the declared record, so the name is resolved to
    the declaration here — and declared, once, if the tenant has not declared
    it already. A test that wants a rate NOT backed by a declaration wants the
    refusal, and asks for it explicitly.

    **AND A RULE PINNED TO AN EVENT TYPE PRICES CALLS OF ONE THE TENANT
    PUBLISHED (#568).** A call naming an Event Type with no production
    declaration is held — no cost, no price — so a rule pinned to one nobody
    published would price nothing, and the fixture writing it means the one a
    tenant writing it would have published (`publishes_what_it_names`) —
    naming the supplier the rule pins, if it pins one (#572), because a
    published Event Type's supplier decides whose calls it prices.

    Five fixtures below write a rule, and each used to spell the first half
    itself; one place now, so the second half cannot reach some of them. The
    Event Type and the supplier default to the rule's own pins in `fields`; a
    fixture that takes either as a parameter of its own passes it.
    """
    if event_type is None:
        event_type = fields.get("event_type", "")
    if provider is None:
        provider = fields.get("provider", "")
    if "measurement" not in fields:
        fields["measurement"] = declares_a_quantity(
            tenant, fields.pop("measurement_key", UNMEASURED_QUANTITY))
    if event_type:
        publishes_what_it_names(tenant, event_type,
                                fields["measurement"].code,
                                provider=provider)


def _rule_in(book, *, provider, event_type, task_type, subtask_type,
             customer, fields):
    """The row itself, once the book has been chosen — the quantity it prices
    resolved by :func:`_the_quantity_it_prices`, which is what keeps every
    fixture in the tree saying what it means rather than transcribing the
    declarations behind a rule.

    The slots ride in `fields` rather than being named one by one. Ten of them
    spelled out as keyword defaults was already the longest line in this file
    at six, and every one of them would have been ``slot=slot`` — the model's
    own "" default says the same thing without the transcription.

    WHICH COLUMN POINTS AT THE BOOK IS THE BOOK'S OWN ANSWER (#368). There is
    no kind word anywhere on this path any more: the two doors below pick a
    table, and the entity says which reference belongs to it.
    """
    _the_quantity_it_prices(book.tenant, fields, event_type=event_type,
                            provider=provider)
    return Rate.objects.create(
        tenant=book.tenant, provider=provider, event_type=event_type,
        task_type=task_type, subtask_type=subtask_type, customer=customer,
        book_version_from=book.version,
        **{book.REFERENCE_COLUMN: book}, **_a_selling_rule_states_its_method(
            book, fields))


def _a_selling_rule_states_its_method(book, fields):
    """A rule in a Pricing Book STATES its method (R10-W4, ruling 4;
    `ck_rate_a_selling_rule_states_its_method`), so a fixture that names none
    gets what a publish writes for a body that names none:
    `direct_event_price`. A cost book's rate names none, and this adds none.
    A test of the invariant itself writes the row directly, not through here."""
    if isinstance(book, PricingBook) and "pricing_method" not in fields:
        return {**fields, "pricing_method": PRICING_METHOD_DIRECT_EVENT_PRICE}
    return fields


def rate_in_default_book(tenant, *, provider="", event_type="",
                         task_type="", subtask_type="",
                         customer=None, **fields):
    """A PRICE rule, in the tenant's default Pricing Book.

    If `customer` is given it goes in that customer's own override book
    instead, which is the only way a rule is written for one customer — the
    record that used to ASSIGN a book to a customer is deleted (#368), and
    what replaces it for the shared case is the customer's Plan
    (`rate_in_a_plans_book`).

    ⚠ **THERE IS ONE DEFAULT PRICING BOOK PER TENANT, NOT ONE PER PROVIDER.**
    A Pricing Book is pinned to no supplier, so two calls naming different
    providers land in the SAME book and are told apart by the rule's own
    `provider` selector — which is where that distinction belongs. On the cost
    side the per-provider default is real, and `cost_rate_in_default_book`
    keeps it.
    """
    if customer is None:
        book, _ = PricingBook.objects.get_or_create(
            tenant=tenant, is_default=True, defaults={"key": "default"})
    else:
        book, _ = PricingBook.objects.get_or_create(
            tenant=tenant, customer=customer,
            defaults={"key": f"cust-{customer.id}"[:64]})
    return _rule_in(book, provider=provider, event_type=event_type,
                    task_type=task_type, subtask_type=subtask_type,
                    customer=customer, fields=fields)


def an_override_rule(tenant, customer, **fields):
    """One of a customer's OWN rules — a whole rule, at its own rung (#361).

    Every field is the override's: it inherits nothing from the rule it
    replaces, which is the whole of the ruling this fixture exists to let a
    test assert. A caller states the method it wants the same way it states a
    price, because an override that could not change the method would be an
    amendment wearing a replacement's name (#151 §6.2).
    """
    # THE PRODUCTION DOOR, NOT A COPY OF IT. A fixture that built the same book
    # itself would be a second writer of that construction and would keep
    # passing the day the real one changed (#354).
    book = BookService.the_customers_own_book(tenant, customer)
    _the_quantity_it_prices(tenant, fields)
    return Rate.objects.create(
        tenant=tenant, customer=customer, pricing_book=book,
        book_version_from=book.version,
        **_a_selling_rule_states_its_method(book, fields))


def rate_in_a_plans_book(tenant, customer, *, plan_key="std", **fields):
    """A price rule in the book the customer's PLAN prices them from (#362).

    **THE CUSTOMER'S ONLY ROUTE TO THIS BOOK IS THE PLAN**, which is the state
    the required reference makes ordinary: no override book and nothing the
    tenant declared as a default. Both halves come from production doors —
    `a_plan` creates the book and then the plan, `PlanService.assign` puts the
    customer on it — so what a test exercises is the route a tenant actually
    has (#354).

    ⚠ **AND IT IS THE ONLY WAY A BOOK IS SELECTED FOR A CUSTOMER AT ALL NOW
    (#368).** This docstring used to say "no assignment" as one absence among
    three; the record that assigned a book to a customer is deleted, so there
    is no such thing to be absent.
    """
    plan = a_plan(tenant=tenant, key=plan_key)
    PlanService.assign(tenant, customer, plan)
    book = plan.pricing_book
    _the_quantity_it_prices(tenant, fields)
    return Rate.objects.create(
        tenant=tenant, pricing_book=book,
        book_version_from=book.version,
        **_a_selling_rule_states_its_method(book, fields))


def a_price_for_whole_work(tenant, *, task_type, agreed_price_micros,
                           customer=None, plan_key=None, **fields):
    """A WORK-LEVEL LINE — what one whole delivered unit of work of this kind
    sells for (#415), in whichever of the three books a caller means.

    The rate side's three fixtures above are one here, because the axis a
    caller varies is the same in all three cases and only the BOOK differs:
    `customer=` puts the line in that customer's own override book, `plan_key=`
    puts it in the book their plan prices from, and neither puts it in the
    tenant's default. Three near-identical functions would have said the same
    thing three times over a table with five columns.

    ⚠ **THE ALTITUDE IS THE COLUMN'S OWN DEFAULT AND A CALLER SAYS NOTHING**,
    because a line for a WHOLE unit of work is what almost every caller means
    and spelling it each time would bury the one case that is interesting. A
    test whose subject is #139 §3.3's refusal passes `kind=` explicitly, which
    is what makes that call site read as the deliberate misconfiguration it is
    describing.

    ⚠ **THE PLAN'S BOOK COMES FROM THE PRODUCTION DOORS**, exactly as
    `rate_in_a_plans_book` takes it: `a_plan` creates the book and the plan and
    `PlanService.assign` puts the customer on it, so what a test exercises is
    the route a tenant actually has rather than a second construction of it.
    """
    if plan_key is not None:
        plan = a_plan(tenant=tenant, key=plan_key)
        PlanService.assign(tenant, customer, plan)
        book = plan.pricing_book
    elif customer is not None:
        book = BookService.the_customers_own_book(tenant, customer)
    else:
        book, _ = PricingBook.objects.get_or_create(
            tenant=tenant, is_default=True, defaults={"key": "default"})
    return TaskPrice.objects.create(
        tenant=tenant, pricing_book=book, task_type=task_type,
        agreed_price_micros=agreed_price_micros, **fields)


def cost_book(tenant, *, key="default", provider="", currency="usd"):
    """A cost book with no rules in it, for a test that adds its own.

    It is `is_default=True` because that is what resolution selects: a cost
    book nothing selects prices nothing, so a fixture handing back one would
    be handing back a book whose rules can never be reached.
    """
    return CostBook.objects.create(
        tenant=tenant, key=key, provider_key=provider,
        currency=currency, is_default=True)


def the_book_holding(rule):
    """The book a rule lives in, whichever kind it is.

    A one-line reader over `Rate.book`, kept because it reads as the question a
    test is asking — *the book holding this rule* — where the property reads as
    a column access. It answers `None` for a rule in no book, which is a state
    this table has always had.
    """
    return rule.book


def cost_rate_in_default_book(tenant, *, provider="", event_type="",
                              task_type="", subtask_type="", **fields):
    """A COST rule, in the tenant's default cost book for its supplier.

    ⚠ **THE PER-PROVIDER DEFAULT IS REAL ON THIS SIDE AND ONLY ON THIS SIDE**
    (#368). A cost book is pinned to a supplier, so two calls naming different
    providers get two books; `""` is the provider-agnostic bucket, which
    resolution reads alongside the provider's own. There is no customer
    parameter, because a supplier's price does not change because of who UBB's
    tenant sells to and a cost book has no column to say otherwise.
    """
    currency = fields.get("currency", tenant.default_currency or "usd")
    book, _ = CostBook.objects.get_or_create(
        tenant=tenant, provider_key=provider, currency=currency,
        is_default=True, defaults={"key": f"cost-{provider or 'default'}"[:64]})
    return _rule_in(book, provider=provider, event_type=event_type,
                    task_type=task_type, subtask_type=subtask_type,
                    customer=None, fields=fields)


#: THE DOOR FOR A FIXTURE THAT NEEDS AN EVENT TO BILL A PARTICULAR AMOUNT
#: (#365). Before that commit a caller stated the customer price in the request
#: body, so any test wanting an event that billed a chosen figure said so in one
#: keyword. The price is now UBB's to resolve, and the only ways in are a rule
#: and the markup rung — so a test that used to state an amount has to CONFIGURE
#: one. Sixteen modules import this door, across metering, billing,
#: subscriptions and the composition layer.
#:
#: This is that configuration, said once. `a_rule_that_prices_what_it_measures`
#: puts a per-unit price rule in the tenant's own book; `priced_at(micros)`
#: answers the quantities bag that rule charges exactly `micros` for. A caller
#: still says one number and still never learns how the engine got there — the
#: `cost_rate_in_default_book` pattern, on the other side of the ledger.
#:
#: ⚠ THE RATE IS NOT ONE MICRO A UNIT, DELIBERATELY. At a rate of one the price
#: would EQUAL the quantity, and every assertion about a billed amount would be
#: satisfiable by an engine that echoed the bag it was handed back — the
#: identity-fixture hazard #364 paid for with a zero markup rung. A rate of a
#: thousand keeps the two numbers different, so an echo is visibly wrong.
PRICED_QUANTITY = "priced_calls"
WHAT_A_UNIT_COSTS_THE_CUSTOMER = 1_000


def a_rule_that_prices_what_it_measures(tenant, **fields):
    """A price rule over `PRICED_QUANTITY`, and a cost rule of NOTHING beside it.

    WHAT THE SECOND RULE IS FOR: fidelity, not coverage. A body that stated a
    price carried NO quantities, so the cost side saw an empty bag and settled
    at a KNOWN zero. Handing those same events a quantity with nothing costing
    it puts the cost at `unresolved` / `cost_rate_missing` instead — a different
    economic state for events whose migration was supposed to change only where
    the PRICE comes from. Declaring the quantity costable at nothing keeps them
    in the state they were already in.

    ⚠ AND NO TEST WOULD CATCH ITS ABSENCE, WHICH IS MEASURED RATHER THAN
    GUESSED. Deleting these three lines and running every module that imports
    this door gives **440 passed, 0 failed** — because almost every one of those
    fixtures also states `provider_cost_micros`, and the caller's own figure
    wins on the cost side without ever consulting a rule. So this is INSURANCE
    against a fixture drifting into a state its own commit never chose, said out
    loud here rather than dressed up as a guard: an earlier draft of this
    docstring claimed leaving it out "changes what half the fixtures assert",
    and the measurement says that was false.

    A fixture that wants a real supplier cost states it as it always did, and
    the caller's figure wins over this rule without consulting it.
    """
    priced = rate_in_default_book(
        tenant, measurement_key=PRICED_QUANTITY,
        rate_per_unit_micros=WHAT_A_UNIT_COSTS_THE_CUSTOMER,
        unit_quantity=1, **fields)
    cost_rate_in_default_book(
        tenant, measurement_key=PRICED_QUANTITY,
        rate_per_unit_micros=0, unit_quantity=1, **fields)
    return priced


def priced_at(micros):
    """The quantities the rule above charges exactly `micros` for.

    Refuses an amount the rate cannot reach rather than rounding to one it can:
    a fixture silently billing 999,000 where it asked for 999,500 would be a
    test asserting a number nothing in it chose.
    """
    quantity, remainder = divmod(micros, WHAT_A_UNIT_COSTS_THE_CUSTOMER)
    if remainder:
        # ⚠ The message says "measured" rather than naming the plural a caller
        # would reach for: that plural is a RETIRED SENSE with a counted
        # numerator, and this file is not one of the files that carries it.
        raise AssertionError(
            f"{micros} is not a whole number of anything this rule can charge "
            f"for: it prices each one measured at "
            f"{WHAT_A_UNIT_COSTS_THE_CUSTOMER} micros")
    # As TEXT (#603): the bag crosses the wire as exact decimal strings, and
    # one fixture spelling serves a body and a service-level call alike.
    return {PRICED_QUANTITY: str(quantity)}


def what_it_bills(extra):
    """Translate a caller's `bills=N` into the body keys that bill exactly N.

    THE THREE RECORDING-ROUTE TEST MODULES BUILD THEIR BODY THE SAME WAY — a
    `_record(**extra)` helper over a dict — and each used to pass the deleted
    price field straight through. This is the one translation they now share, in
    `tests/_helpers.py` where `docs/conventions/testing.md` puts shared setup:
    three copies of it would be three places to fix the day the fixture rule
    changes, and #352 paid for exactly that duplication once already.

    Answers the keys to merge, so a caller that says nothing about billing gets
    nothing merged and its body is untouched. Pops, so `bills` never reaches the
    request as a key of its own.
    """
    if "bills" not in extra:
        return {}
    return {"measurements": priced_at(extra.pop("bills"))}


#: What every posting in a recovery fixture measures, and the denominator its
#: rules divide by — so a rule's per-unit figure IS the amount, and an assertion
#: says one number rather than an arithmetic.
RECOVERABLE_QUANTITY = "prompt_tokens"
ONE_CALL = 1_000_000
WHAT_IT_COST = 4_000_000

#: A markup rung with a REAL percentage, and the customer price it answers over
#: `WHAT_IT_COST` (a quarter, in micro-percent: 4,000,000 + 1,000,000).
#:
#: ⚠ **A ZERO RUNG MAKES A PROJECTED PRICE EQUAL THE SUPPLIER COST, AND THAT
#: MAKES EVERY ASSERTION ABOUT THE FIGURE SATISFIABLE BY THE WRONG NUMBER**
#: (#364). A projection that merely echoed what the call cost would answer
#: correctly for a rung of nothing, which is the arithmetic-branch-by-accident
#: shape this repository keeps paying for.
#:
#: BOTH DIRECTIONS WERE RUN, and the numbers are the reason this constant is not
#: zero. Replacing the re-resolved amount with the posting's own
#: `provider_cost_micros`:
#:
#:   * with the rung at 25%, SEVEN tests go red across both modules;
#:   * with the rung at zero, FIVE of the projection class's six cases stay
#:     GREEN — including *the figure is what a run then actually completes* —
#:     and the only one that notices is
#:     `test_the_figure_is_a_price_and_not_the_cost_it_was_derived_from`, which
#:     fails on its own premise (`4000000 == 4000000`) rather than on the
#:     projection. That case exists to be exactly that tripwire.
#:
#: Any case whose subject is the AMOUNT takes this rung; a case whose subject is
#: a COUNT may keep a zero rung, and says so.
A_REAL_MARKUP = 25_000_000
WHAT_IT_WOULD_BILL = 5_000_000


def a_tenant_with_unresolved_postings(name="Recovery"):
    """A tenant whose costs come from a Cost Rate and whose prices come from
    nothing at all (#363).

    The state most postings in this repository are recorded in, and the one a
    Resolution Run exists for: a cost UBB can work out, and a price no rule and
    no markup rung ever gave them. Returns `(tenant, customer)`.

    It is here rather than in either test module because BOTH of #363's modules
    need it — the service-level one and the one at the HTTP surface — and
    `docs/conventions/testing.md` puts shared setup in a `_helpers` module for
    the reason that applies: a second copy is a second thing to edit the day the
    recording path's answer moves, and the day one of them is missed is the day
    a fixture asserts a state the engine no longer produces.
    """
    tenant = Tenant.objects.create(name=name,
                                   products=["metering", "billing"])
    customer = Customer.objects.create(tenant=tenant, external_id="acme")
    declares_a_quantity(tenant, RECOVERABLE_QUANTITY)
    cost_rate_in_default_book(
        tenant, measurement_key=RECOVERABLE_QUANTITY,
        rate_per_unit_micros=WHAT_IT_COST, unit_quantity=ONE_CALL)
    return tenant, customer


def an_unresolved_posting(tenant, customer, key, *, event_type="chat",
                          measures=RECOVERABLE_QUANTITY, **fields):
    """One posting, recorded through the real recording path.

    Recorded rather than constructed, because what a run reads is the receipt
    the engine wrote — the quantities by value, the section statuses, the
    provenance — and a hand-built row would be a fixture agreeing with itself.

    ⚠ **THE EVENT TYPE IT NAMES IS PUBLISHED FIRST, WITH WHAT IT MEASURES
    (#568)** — unless the test has declared one at that key itself, which is
    then the test's to have meant. An Event Type with no production
    declaration is held, with no cost and no price, until the tenant says what
    it was; this seed is the state a RUN repairs — a cost UBB worked out and a
    price nothing gave — and a held event is a different state with a
    different remedy.
    """
    from apps.metering.usage.services.usage_service import UsageService

    if event_type:
        publishes_what_it_names(tenant, event_type, measures)
    result = UsageService.record_usage(
        tenant, customer, key, event_type=event_type,
        measurements={measures: ONE_CALL}, **fields)
    return Posting.objects.get(id=result["event_id"])


#: A second quantity, and the one the tenant declared with a typo — so a Cost
#: Rate written against the declaration prices a name no event ever measures,
#: and every posting measuring the real one goes uncosted. Correcting the
#: declaration is the recovery: it carries no effective moment, and the rate it
#: repoints has been in force since before the posting.
SECOND_QUANTITY = "completion_tokens"
THE_TYPO = "completion_tokns"

CALCULATED_CALL = "chat"
#: The Event Type whose supplier reports its own figure. Recorded with none, it
#: is unresolved for a cause no re-costing can answer — and its record keeps no
#: quantities, which is what the guard against a silent zero exists for.
REPORTED_CALL = "reported.call"
#: The Event Type a price rule pins, so that some postings are priced and some
#: are not without either state being a fixture accident.
PRICED_CALL = "priced.call"

WHAT_THE_RULE_CHARGES = 9_000_000


class ATenantWithUnresolvedPostingsMixin:
    """A tenant whose costs come from Cost Rates and whose prices come from
    nothing at all — which is the state most postings in this repository are
    recorded in, and the one a run exists for.

    ⚠ **IT LIVES HERE BECAUSE THREE MODULES NEED IT** — the run's own service
    and surface tests (#363) and the three read surfaces projected from it
    (#364). `docs/conventions/testing.md:22` puts shared setup in a `_helpers`
    module for the reason that bites here: every one of these seeds encodes an
    answer the recording path gives today, and a second copy is a second thing
    to edit the day that answer moves — with the day one of them is missed
    being the day a fixture asserts a state the engine no longer produces.
    """

    def setUp(self):
        self.tenant, self.customer = a_tenant_with_unresolved_postings()

    # --- seeds ---------------------------------------------------------------

    def a_posting(self, key, **fields):
        return an_unresolved_posting(self.tenant, self.customer, key, **fields)

    def a_rate_priced_against_a_typo(self):
        """The Cost Rate the tenant meant to write, against the name they
        mistyped when they declared it."""
        declares_a_quantity(self.tenant, THE_TYPO)
        return cost_rate_in_default_book(
            self.tenant, measurement_key=THE_TYPO,
            rate_per_unit_micros=WHAT_IT_COST, unit_quantity=ONE_CALL)

    def the_tenant_corrects_the_declaration(self):
        """The recovery, and the reason it is not backdating.

        A declared quantity's code carries no effective moment — correcting one
        is a statement about the tenant's catalogue, not about a price at a
        date — and the Cost Rate it repoints has been in force since before the
        posting was recorded. A *rule* written today could not reach that
        posting at all, which is the difference this whole mechanism turns on.
        """
        Measurement.objects.filter(
            event_type__tenant=self.tenant, code=THE_TYPO).update(
            code=SECOND_QUANTITY)

    def declares_a_reported_cost(self):
        """An Event Type whose supplier reports its own figure."""
        return declares_a_caller_supplied_cost(
            self.tenant, REPORTED_CALL,
            currency=self.tenant.default_currency or "usd")

    def a_price_rule(self):
        return rate_in_default_book(
            self.tenant, event_type=PRICED_CALL,
            measurement_key=RECOVERABLE_QUANTITY,
            rate_per_unit_micros=WHAT_THE_RULE_CHARGES, unit_quantity=ONE_CALL)

    # --- reading -------------------------------------------------------------

    @staticmethod
    def state_of(posting):
        posting.refresh_from_db()
        return (posting.costing_status, posting.provider_cost_micros,
                posting.pricing_status, posting.billed_cost_micros)

    @staticmethod
    def receipt_of(posting):
        posting.refresh_from_db()
        return getattr(posting, Posting.RECEIPT_COLUMN)

    def a_run(self, **selector):
        from apps.metering.pricing.services.resolution_run import (
            RunSelector, execute)

        with transaction.atomic():
            return execute(tenant=self.tenant, selector=RunSelector(**selector))


def the_cost_rate_is_repriced(tenant, *, to_micros, **fields):
    """Close the cost rule in force and open its replacement (#363).

    The shape a publish writes — one boundary closing and the next opening —
    done directly because what a caller here needs is the state afterwards
    rather than the route that reaches it.

    It lives beside `cost_rate_in_default_book` for that helper's own reason:
    selecting the rules to close asks which books hold them.

    ⚠ **AND THAT IS NOW A COLUMN RATHER THAN A JOIN THROUGH A WORD (#368).**
    "The cost rules" used to mean *the rules in books whose kind column says
    cost*; it means *the rules pointing at a cost book*, which is the same set
    said by the schema instead of by a value. There is no word left to be
    wrong about.
    """
    Rate.objects.filter(tenant=tenant, cost_book__isnull=False,
                        valid_to__isnull=True).update(valid_to=timezone.now())
    return cost_rate_in_default_book(tenant, rate_per_unit_micros=to_micros,
                                     **fields)


def cost_rule_in_the_providers_book(tenant, provider, **fields):
    """A COST rule in the default book FOR ONE SUPPLIER, pinning nothing.

    `cost_rate_in_default_book` takes one `provider` and uses it twice — it
    selects the book AND pins the rule's own selector — which is what almost
    every fixture here wants. This separates the two, and there is exactly one
    question that needs them separated: whether two rules in two DIFFERENT
    default books can be made equally specific. They can only be if neither
    pins the provider, which the other door cannot express.

    ⚠ **IT IS A COST FIXTURE BECAUSE TWO DEFAULT BOOKS IS NOW A COST-SIDE
    FACT (#368).** It used to build two default PRICE books, one per provider.
    A Pricing Book is pinned to no supplier and a tenant has exactly one
    default, so that shape is unbuildable on the price side — not relaxed,
    unstatable. The claim it exists for (an unbreakable tie falls to the
    narrower book) is alive on the cost side, where a supplier's own default
    book and the provider-agnostic one are both selected, in that order.
    """
    book, _ = CostBook.objects.get_or_create(
        tenant=tenant, provider_key=provider,
        currency=fields.get("currency", tenant.default_currency or "usd"),
        is_default=True, defaults={"key": f"cost-{provider}"[:64]})
    _the_quantity_it_prices(tenant, fields)
    return Rate.objects.create(
        tenant=tenant, cost_book=book,
        book_version_from=book.version, **fields)


def declares_a_markup(tenant, *, percentage_micros=0):
    """The markup rung a tenant has to declare before a price can settle (#356).

    **THE DEFAULT IS ZERO, AND ZERO IS A DECISION.** A tenant with a rung of
    nothing is saying *charge my customer what the call cost*, which settles at
    the supplier's figure and is what the fixtures using this helper always
    meant. What they used to rely on was the absence of a rung producing the
    same number, and that stopped being true when a price nobody stated became
    `unknown` rather than the cost. The distinction is the whole point: an
    absent rung is not a zero rung.

    Named for the act rather than the record — a tenant declares a markup, and
    which row carries it is this module's business, not its callers'. **That is
    what let the record change underneath every caller in #357**: the rung moved
    off the customer-override table's `customer IS NULL` row and onto a record
    of its own, and no fixture in the tree had to say so.

    ⚠ **THE TENANT DEFAULT ONLY, WHICH IT ALWAYS WAS.** It used to take a
    `customer=` and no caller ever passed one; the rung it now writes is the
    tenant's by construction, so the argument is gone rather than accepting a
    value it would have to ignore. A customer-level override is a different rung
    and a test that wants one asks for it by name.
    """
    return TenantDefaultMarkup.objects.create(
        tenant=tenant, markup_micro_percent=percentage_micros)


def markup_terms(basis_micros, *, micro_percent=0):
    """The terms a `margin_over_cost` price must carry on its receipt (#357).

    `build_receipt` refuses a margin that arrives without them, so every fixture
    building a settled `margin_over_cost` resolution by hand needs a set — and
    two modules in two apps do, which is why this is here rather than copied
    into each. `docs/conventions/testing.md` puts shared setup in a `_helpers`
    module for exactly the reason that applies: a second copy is a second thing
    to edit the day `REQUIRED_MARKUP_KEYS` moves, and the day one of them is
    missed is the day a fixture asserts a shape the boundary no longer accepts.

    **THE DEFAULT MAKES THE ARITHMETIC TRUE, WHICH IS THE POINT OF A DEFAULT
    HERE.** A rung of zero over a basis of `basis_micros` IS `basis_micros`, so
    a caller who names only the basis gets terms that reproduce their own
    amount rather than numbers that merely sit beside it. A caller taking a real
    percentage says so and states the amount it produces itself.

    ⚠ **THE FLAT ADDEND LEFT THE SET IN #369**, with the two records that could
    supply one. That is the day `REQUIRED_MARKUP_KEYS` moved, and this helper is
    why it was one edit.
    """
    return {"micro_percent": micro_percent, "basis_micros": basis_micros}


def rate_in_a_book_nothing_selects(tenant, *, key="unselected", provider="",
                                   currency="usd", **fields):
    """A price rule in a book resolution never reads (#356).

    A book becomes readable in exactly three ways — it holds the customer's
    own rules, their PLAN prices from it (#362), or it is the tenant's default
    — and this is none of them. It exists so that "there is no fallthrough
    between books" can be asserted by a rule that WOULD match the event on
    every selector and is still not the answer, rather than by the absence of a
    rule, which proves nothing about reachability.

    ⚠ **THERE WERE FOUR WAYS AND NOW THERE ARE THREE (#368).** A customer used
    to reach a book by being ASSIGNED to it; that record is deleted, and the
    Plan is what replaces it.
    """
    book = PricingBook.objects.create(
        tenant=tenant, key=key, is_default=False)
    _the_quantity_it_prices(tenant, fields, provider=provider)
    return Rate.objects.create(
        tenant=tenant, provider=provider, currency=currency,
        pricing_book=book, book_version_from=book.version,
        **_a_selling_rule_states_its_method(book, fields))


def a_usage_event_subject(subject_id=None):
    """A receipt subject for a test whose question is resolution, not identity.

    `PricingService.price` requires its subject and gives it no default (#349):
    a receipt explains one named thing, and a default would hand one subject's
    answer to every caller who left the argument out. The tests that resolve a
    price are almost all about WHAT was resolved rather than about which row it
    was resolved for, so they say that here once instead of each inventing an
    id. A test that IS about the identity passes its own.
    """
    return ReceiptSubject(
        subject_type=PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
        subject_id=str(subject_id or uuid4()))


def a_receipt_agreeing_with(*, provider_cost_micros, billed_cost_micros,
                            costing_status=COSTING_STATUS_KNOWN,
                            pricing_status=PRICING_STATUS_KNOWN):
    """A version-2 receipt for a posting a test ASSEMBLES (R10-W4, #558).

    Every public read publishes the receipt typed, version 2 only, and every
    recording path writes one — so a posting built with `objects.create` and
    read through a route needs one too: the column's `{}` default is not a
    receipt, and no production path leaves it. Built through `build_receipt`,
    the one construction boundary, with each section's method stated exactly
    when its status is settled (the boundary's own rule), so a combination
    the boundary would refuse is refused here rather than seeded.

    The defaults are the posting's own: both statuses `known`.
    """
    costing = Resolution(
        method=(COSTING_METHOD_CALCULATED
                if costing_status == COSTING_STATUS_KNOWN else None),
        status=costing_status, amount_micros=provider_cost_micros, detail={})
    pricing = Resolution(
        method=(PRICING_METHOD_DIRECT_EVENT_PRICE
                if pricing_status == PRICING_STATUS_KNOWN else None),
        status=pricing_status, amount_micros=billed_cost_micros, detail={})
    return build_receipt(
        subject=a_usage_event_subject(),
        effective_at=timezone.now().isoformat(), currency="usd",
        pricing_engine_version=PRICING_ENGINE_VERSION,
        costing=costing, pricing=pricing)


def receipt_without_its_per_event_facts(body):
    """A recording result whose receipt can be compared with another's (#349).

    Two parity tests ask whether two recordings produced the SAME body — the
    batch endpoint against the single one, and a recording with a declared
    grouping against one without. The Pricing Receipt names the row it explains
    and the instant it resolved as of, and both are per-event by construction,
    exactly as the event id beside them always was. Masking them is the only way
    those questions stay askable.

    **Everything else in the record is left alone deliberately**, because it is
    where the parity actually bites: both methods, both statuses, the components
    and the totals must still match byte for byte.

    Lives here rather than in either caller because it was written twice before
    it was written once, and the second copy is what put the receipt column's
    retired spelling over its ceiling — a helper is also the answer to that,
    since it addresses the column through the model's own constant in one place.
    """
    return {**body, Posting.RECEIPT_COLUMN: {
        **body[Posting.RECEIPT_COLUMN],
        "subject_id": "SUBJECT", "effective_at": "AS_OF"}}


# --- The three doors ADR-0007 §2 names, over one record ----------------------
#
# A guard only one door respects is the defect a database rule exists to catch,
# so every prohibited write against this app's tables is driven through all
# three. `usage/tests/_helpers.py` has the same three over a posting, and the
# two sets are not one set: they write different columns on different tables
# through different model APIs, and the only lines they would share are the two
# the ORM dictates. What IS copied is the structure, which is what "copy the
# prior art" means.
#
# THE RECORD DECIDES ITS OWN MODEL, WHICH IS WHY THESE THREE TAKE NO MODEL
# ARGUMENT AND NAME NONE (#358). A second rule landed on a second table in this
# app — a publish record, whose whole-record rule needs the same three doors as
# the rule table's column rules — and a copy of these functions differing only
# in a class name would be the duplication `docs/conventions/testing.md` puts a
# `_helpers` module here to prevent.

def through_the_queryset(record, **columns):
    type(record).objects.filter(pk=record.pk).update(**columns)


def through_raw_sql(record, **columns):
    """Raw SQL, with each value prepared the way its own column takes it.

    The door is *raw SQL*, not *raw Python objects*: `get_db_prep_value` is the
    model field's own answer to what the driver should be handed, so this door
    writes exactly what the ORM writes and differs from the other two only in
    going around them — which is the whole point of it.
    """
    model = type(record)
    assignments = ", ".join(f"{name} = %s" for name in columns)
    values = [model._meta.get_field(name).get_db_prep_value(value, connection)
              for name, value in columns.items()]
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {model._meta.db_table} SET {assignments} WHERE id = %s",
            [*values, str(record.pk)])


def through_save(record, **columns):
    """`save()` — the door a shell session, a data migration or a fixture uses."""
    for name, value in columns.items():
        setattr(record, name, value)
    record.save()


DOORS = (("QuerySet.update()", through_the_queryset),
         ("raw SQL", through_raw_sql),
         ("save()", through_save))


class RefusalThroughEveryDoorMixin:
    """Every prohibited write against a record, driven through all three doors.

    ⚠ `REFUSAL_NAME` has no default on purpose. Several mechanisms on these
    tables answer `IntegrityError` and two of them refuse writes to the same
    column, so a subclass that forgot to say which one it is about would assert
    against whatever the base class happened to carry — the shape that let a
    rule refusing the wrong thing pass its own check one slice ago.
    """

    #: The constraint a subclass's refusals must name. Set per class.
    REFUSAL_NAME = None

    def assert_every_door_refuses(self, record, refusal=None, **columns):
        """``refusal`` overrides `REFUSAL_NAME` for one call (#416).

        A rule whose message names the CONSTRAINT is the same message every
        time, which is what a per-class name expresses. A rule holding many
        columns at once names the COLUMN THAT MOVED instead — so the
        discriminating assertion differs per call, and a per-class name would
        be satisfied by the rule refusing some other column of the same record.
        That is #352's defect exactly, at the granularity below the one this
        mixin was written for.
        """
        expected = refusal or self.REFUSAL_NAME
        self.assertIsNotNone(
            expected,
            "this class has not said which mechanism its refusals belong to")
        for name, door in DOORS:
            with self.subTest(door=name):
                with self.assertRaisesRegex(IntegrityError, expected):
                    with transaction.atomic():
                        door(record, **columns)
                record.refresh_from_db()


# --- A book holding one rule that can be repriced at an instant --------------

#: The quantity the fixture below prices and the two selectors it pins. Named
#: here rather than in each caller because two modules now ask one book the
#: same question — *what does this cost at that moment* — and a second
#: transcription of the setup is what `docs/conventions/testing.md` puts this
#: module here to prevent.
SCHEDULING_QUANTITY = "prompt_tokens"
SCHEDULING_PROVIDER = "openai"
SCHEDULING_EVENT_TYPE = "chat"

#: One whole denominator of the quantity, so a resolved amount IS the rule's
#: per-unit term rather than a multiple of it that has to be divided back out.
ONE_DENOMINATOR = 1_000_000

#: Distinct powers of ten, so an assertion reading the wrong version of a rule
#: names it in its own failure message rather than reporting a bare mismatch.
FIRST = 1_000_000
SECOND = 2_000_000
THIRD = 3_000_000
FOURTH = 4_000_000

#: The one term these fixtures move. A publish cannot change a rule's
#: arithmetic shape, so the per-unit amount is the whole of what a reprice
#: states here.
THE_TERM = "rate_per_unit_micros"


class AForwardDatingBookMixin:
    """A tenant, a customer, and a book holding one rule that can be repriced.

    Two acts and two reads, which between them are every question a scheduling
    test asks: declare or publish a new amount at an instant, and resolve the
    price at an instant. Every one of them takes the moment as an argument,
    because a test about *when* a price changes cannot have a fixture that
    reads a clock on its behalf.

    Lives here rather than in either module because #359's forward-dating
    tests and #360's reversal tests need exactly this book, and copying the
    scaffolding is the violation `docs/conventions/testing.md:22` names — the
    structure is what "copy the prior art" means, never the code.
    """

    def setUp(self):
        super().setUp()
        self.tenant = Tenant.objects.create(name="T", default_currency="usd")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.rule = rate_in_default_book(
            self.tenant, provider=SCHEDULING_PROVIDER,
            event_type=SCHEDULING_EVENT_TYPE,
            measurement_key=SCHEDULING_QUANTITY, rate_per_unit_micros=FIRST)
        self.book = the_book_holding(self.rule)

    def a_change(self, **terms):
        return {"line": LINE_RATE, "kind": CHANGE_REPRICE,
                "measurement_key": SCHEDULING_QUANTITY,
                "provider": SCHEDULING_PROVIDER,
                "event_type": SCHEDULING_EVENT_TYPE, **terms}

    def declare_at(self, effective_at, amount):
        """Declare a reprice dated at `effective_at`. Writes no rule."""
        return BookService.declare(
            self.book, [self.a_change(**{THE_TERM: amount})],
            effective_at=effective_at)

    def publish_at(self, effective_at, amount):
        """Declare a reprice and publish it, dated at `effective_at`."""
        return BookService.publish_declared(
            self.declare_at(effective_at, amount))

    def resolved(self, as_of):
        return resolve_price(
            PricingSubject(
                receipt_subject=a_usage_event_subject(),
                tenant=self.tenant, customer=self.customer,
                selectors=self._selectors(),
                measurements={SCHEDULING_QUANTITY: ONE_DENOMINATOR},
                currency="usd"),
            as_of)

    def amount_at(self, as_of):
        receipt = self.resolved(as_of)
        # The method is asserted beside the amount deliberately: a fallthrough
        # to markup returns a plausible number and raises nothing, so "an
        # amount came back" is not evidence that a rule produced it.
        self.assertEqual(receipt["pricing"]["method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        return receipt["totals"]["billed_cost_micros"]

    def _selectors(self, **overrides):
        base = {name: "" for name in Rate.SELECTORS}
        base.update(provider=SCHEDULING_PROVIDER,
                    event_type=SCHEDULING_EVENT_TYPE)
        base.update(overrides)
        return base


def database_rules_guarding(table):
    """What the catalogue holds about the triggers on `table`, now.

    `(name, type_bits, function_body)` per non-internal trigger — every fact a
    caller asking whether a rule is installed needs, and no more. A migration
    that ran is evidence that a file executed, not that a rule is on the table.

    **SHARED RATHER THAN COPIED, WHICH `docs/conventions/testing.md:22`
    REQUIRES.** Several modules ask this question of the tables in this app —
    the rate's, the charge's, the agreed price's — and two copies of one
    catalogue query are two things that can drift apart while agreeing with
    each other. It takes the table as an argument because a caller asking
    about the table a rule is named for should say which table that is,
    rather than inherit whatever the model happens to point at.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgname, t.tgtype, p.prosrc "
            "FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_proc p ON p.oid = t.tgfoid "
            "WHERE c.relname = %s AND NOT t.tgisinternal", [table])
        return cursor.fetchall()


def rules_snapshot(book):
    """Every column of every rule in a book, in a stable order.

    `updated_at` rides along deliberately: a write that touched a row and
    changed nothing else would still move it, and "nothing was written" has to
    mean the rows were not written to at all.
    """
    columns = [field.attname for field in Rate._meta.concrete_fields]
    return [
        {column: getattr(rule, column) for column in columns}
        for rule in book.rates.order_by("id")
    ]
