"""The Pricing Receipt — the record that explains why an amount is what it is.

**THE RECEIPT IS THE AUTHORITY, AND THAT IS THE WHOLE POINT (#349, #148 §3).**
Before this module the stored record explained a price by pointing at the
configuration that produced it. That is the failure the pricing-versions
decision exists to prevent: a rule can be edited, and re-resolving a historical
event against today's configuration answers a different number from the one the
tenant was charged. So the receipt **holds values**. Pointers ride along in
:data:`provenance` and nothing reads them to reconstruct an amount.

**A PRICING RECEIPT IS THE RECORD OF AN ECONOMIC RESOLUTION. IT IS NOT A
GUARANTEE THAT CUSTOMER REVENUE EXISTS AND IT IS NOT EVIDENCE A CUSTOMER WAS
CHARGED.** A metering-only tenant has receipts for every event it records and is
never billing anybody through UBB. That sentence travels with the name
everywhere the name appears — here, on the concept in the registry, on the
published schema, and later in the console's own words — because without it a
metering-only tenant reads "pricing receipt" as "UBB charged my customer".

The shape::

    receipt_schema_version    the shape of this record
    pricing_engine_version    the code that computed it
    subject_type · subject_id what this receipt explains
    effective_at · currency
    costing      method + status + method-specific detail, by value
    pricing      method + status + method-specific detail, by value
    totals       the denominated outcomes
    provenance   cross-reference ids only

**TWO VERSIONS, BECAUSE THEY ANSWER TWO QUESTIONS** (#148 §4.3): *can today's
code read this record*, and *which engine produced this number*. A single
version conflates a shape change with a behaviour change, and the two have to
move independently — a reshuffled key is not a repriced event. The reader
functions at the foot of this module therefore dispatch on the version **the
record declares**, never on :data:`RECEIPT_SCHEMA_VERSION`, which is what makes a
receipt written today still readable when the code has moved on.

**⚠ FOR A UNIT OF WORK SOLD AT ONE AGREED PRICE, ITS REVENUE AND ITS COGS
RESOLVE AGAINST DIFFERENT INSTANTS, AND THAT IS THE DESIGN RATHER THAN A BUG
(#415, #139 §2.3).** The agreed price is determined ONCE, at the moment the work
starts, and pinned to it — so a unit of work spanning a reprice keeps the number
it was quoted. Its supplier costs are not pinned at all: each one resolves at
its own posting's timestamp, exactly as it does under every other regime. **The
price was promised; the cost is observed.** A reader holding one receipt from
such a unit of work sees a cost resolved against a rule that was not in force
when the work began, and without this sentence that reads like a defect. The
same sentence is at `apps/platform/work/models.py`, on the column that holds the
pinned number.

**THE SUBJECT IS TYPED.** A receipt explains either one usage row or one Charge,
and which one it is is a declared value rather than an inference from whichever
foreign key happens to be populated. The two values are the registry's
(`pricing_receipt_subject_type`), held by reference from `core.vocabulary`.

**ONE CONSTRUCTION BOUNDARY, AND IT IS THE PLACE THAT VALIDATES.**
:func:`build_receipt` is the only place a receipt is built, and it validates the
assembled record before anybody can persist it — not a validator called from
three call sites, one construction function no caller can bypass. A receipt that
reached the database unvalidated is a record that explains nothing and cannot be
told from one that does. `apps/metering/usage/tests/
test_the_receipt_has_one_construction_boundary.py` is what keeps every caller of
it declared — the FUNCTION is one, and since #418 two modules call it: the
compute spine, and the projection of a Charge, whose amounts were agreed and
definitional so there is no resolution for the spine to run.

**AN AMOUNT, ITS STATUS AND ITS METHOD MOVE TOGETHER, IN BOTH SECTIONS.** This
is the amount/status pair `core.amount_status_pairs` names for a table, one
level up and with the method added: an amount is present exactly when its status
says it is settled, and the method — *how this amount was arrived at* — is
present at most on the same condition. So the price side's method is **nullable**
and it is null exactly when no price was derived, with the status beside it as
the thing a reader consults. No fourth method value is coined for "none": a
method value meaning "there wasn't one" is a second encoding of the status, and
the day the two disagree there is no way to tell which is right.

⚠ **"AT MOST" IS THE WEAKER HALF, AND WHICH HALF APPLIES IS THE SUBJECT'S
ANSWER (#418).** *A method beside an unsettled status* is refused for every
subject there is — it is a claim about how a number was reached with no number
beside it. *A settled amount naming no method* is refused only where the
subject's amounts were arrived at at all, which is
:data:`DERIVES_ITS_AMOUNTS`. A Charge's are not: its price was **agreed**
before the work ran and pinned to it, and its supplier cost is zero because
there is no supplier behind a Charge. The relaxation is not free — a receipt
whose subject is a Charge must carry the regime that makes it true, by value,
under :data:`PRICING_REGIME_KEY` — so a reader meeting a settled price with no
method can tell *agreed* from *somebody forgot to record the derivation*.

⚠ **The method is a property of the DERIVATION, not of the rule** — which is
what the rule above means, and it is a statement about the SHAPE rather than a
description of what the engine writes today. A rule that is matched and cannot
compute would record its identity in `provenance` and its terms by value in
`detail`, and leave the method null, because nothing was derived; nothing is
lost by that, and the alternative is a receipt naming how an amount was computed
beside no amount.

⚠ **A PRICING RULE NOW DECLARES A METHOD OF ITS OWN (#355), AND THAT IS NOT THE
SAME FIELD SAID TWICE.** The rule's column says which method it *would* derive
by; this section says which method *did* produce the amount beside it. They
coincide for every price the engine resolves and they are not required to: the
matched-but-uncomputable case above is exactly where a rule naming a method
yields a receipt naming none. The rule is configuration and can be edited; the
receipt is the record and cannot, which is the whole reason values live here and
pointers ride along in `provenance`.

⚠ **The engine writes all four price statuses now** (#356, #418). It reports
`known` with a method where a rung priced the event, `waived` where a margin was
taken over a supplier cost UBB never learned — a charge nobody will ever collect
is a decided loss rather than a queued one — `unknown` where no rung answered at
all, and, since #418, `not_applicable` for every event under a piece of work
sold at ONE AGREED PRICE. That fourth one is still not a fact about resolution:
the ladder is not consulted for such an event at all, because the customer
revenue is the whole piece of work's and none of it is this event's.
`pricing/applicability.py` holds the rule that decides WHICH of its two reasons,
and the regime that produced it rides in the price section's detail under
:data:`PRICING_REGIME_KEY`. So the null branch below is reached through the
spine as well as at this boundary.

**WHAT IS FIXED AND WHAT IS OPEN.** The top-level keys and the three keys of each
section are exact — a key that is not in the shape above is refused, so a field
arriving in the record is a decision rather than a drift. The two `detail`
containers and `provenance` are the open parts, and that is deliberate: it is
where the content obligation (#153 §12.4 — the quantities, rates, denominators
and components a receipt must outlive its measurements to keep) is written,
without the record being reshaped a second time to receive it.

**THE CONTENT OBLIGATION IS WRITTEN THERE NOW (#350).** The measured detail
behind a posting is a child record with a retention horizon of its own; this
record is kept for six years, so a receipt holding a total and a pointer would
leave a tenant nothing to show a customer and a recovery run nothing to work
from. Three obligations, and **the middle one is the only one not enforced
here**:

- **A calculated amount's components each explain themselves** — the quantity,
  the rule's terms and the denominator, by value. That is a claim about every
  component that exists, so it is :data:`REQUIRED_COMPONENT_KEYS`, refused at
  this boundary like everything else in this module.
- **An unresolved cost carries the quantities a recovery will need.** Written by
  the spine and **not refused here**, because this boundary cannot express the
  rule correctly: `unresolved` has two causes and the record does not carry
  which. A cost whose quantities matched no rule has quantities to keep; a cost
  the supplier has simply not reported yet has none to keep and never will, and
  a rule demanding them of both would refuse a legitimate receipt. A refusal
  that is wrong for half its subject is worse than no refusal, because the
  half it is wrong about is the half nobody tests.
- **A price derived as a margin over cost carries the percentage and the basis**
  (#357). :data:`REQUIRED_MARKUP_KEYS`, refused here, and the obligation binds
  the METHOD rather than the rung — a markup and a rule declaring
  `margin_over_cost` are one method at two rungs, so a record that explained one
  of them and not the other would be the second shape this ruling refuses. Which
  rung supplied it is `provenance`'s answer, and it is a pointer rather than a
  term precisely because the record it names can be edited or withdrawn.

⚠ **THAT ARRIVED WITHOUT MOVING** :data:`RECEIPT_SCHEMA_VERSION`, **and the
reason is what the version is for.** It answers *can today's code read this
record* — and every key already in a receipt is still there, still meaning what
it meant, so a reader written before that commit reads a receipt written after
it exactly as it did before. The keys that arrived are inside the open
containers, which no reader may assume a fixed set of. A version bumped for an
additive detail key would say a record had become unreadable when it had not,
and would fork the one reader below for no question it could answer differently.

⚠⚠ **AND A COMPONENT'S ARITHMETIC-SHAPE KEY WAS *RENAMED* WITHOUT MOVING IT
EITHER (#366), WHICH IS A HARDER CASE AND IS DECIDED RATHER THAN INHERITED.** A
key arriving is additive; a key changing its spelling is not, and this module's
own rule for the version says to bump it "when a key moves, arrives or leaves".
The rule it serves is narrower than its wording, and the wording is what would
mislead here: the version answers *can today's code read this record*, and a
bump is a claim that some reader's ANSWER changes. **Nothing reads this key.**
`uncosted_quantity_keys` and `recorded_quantities` are the module's two readers
and neither touches a component's shape; the only thing that has ever read it is
a test, over a receipt it wrote itself moments earlier. So a receipt written
last year and one written today are equally readable by every reader that
exists, and a bumped version would have refused nothing, unlocked nothing, and
added a shape to :data:`READABLE_SCHEMA_VERSIONS` that no branch below could
tell apart from the one beside it.

**Old receipts keep the old spelling and are NOT rewritten**, which is #148
§4.6's rule and the whole point of the record: back-dating one to a shape that
did not exist on its day makes it a worse record, not a better one. ⚠ **The day
a real reader of this key appears, it must know BOTH spellings** — that is what
a version would have bought and what this note is instead, and the reader that
adds it is the one that should add the version with it.

⚠ **THE QUANTITIES NOW EXIST IN TWO PLACES ON PURPOSE AND THEY ARE NOT TWO
SOURCES OF TRUTH** (#165 §6). The measurement record holds what was *reported*;
this holds what was *used to compute an amount*. They are not required to be
equal, **nothing ever reconciles them**, and nothing here compares them — see
the note at the snapshot site in `services/pricing_service.py` for why building
that comparison would re-create the very shape this record exists to remove.

⚠ **`detail` IS THE SECTION'S DETAIL, NOT ONLY ITS METHOD'S.** It holds whatever
explains that side's method, status and amount by value — which is usually
method-specific and is not required to be. The case that forces the distinction
is already known and is now built: the subject's whole-work pricing regime
decides whether an event carries a customer price at all, so it explains the
PRICING side's outcome and rides in `pricing.detail`, even though it is a fact
about the subject rather than about a method. Reading `detail` narrowly would
have left that value no home but a ninth top-level key, and the top-level shape
is the ratified one. Since #418 that value is load-bearing in three directions
rather than descriptive in one: it is what a recovery run re-resolves against,
what a `not_applicable` price section is explained by, and what licenses a
Charge's receipt to settle an amount naming no method.

**WHY HERE AND NOT IN `core/`.** The engine that resolves an amount is the thing
that can explain it, and `pricing_engine_version` is the engine's own — passed in
rather than imported, because this module may not import the service that would
import it back. A second product resolving a subject of its own is the commit
that finds out what the two have in common, and is where this moves to the
kernel; today there is one, exactly as `core.amount_status_pairs` had one table
until #348.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.vocabulary import (
    COSTING_METHOD_VALUES,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_VALUES,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_METHOD_VALUES,
    PRICING_MODE_FIXED,
    PRICING_RECEIPT_SUBJECT_TYPE_CHARGE,
    PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
    PRICING_RECEIPT_SUBJECT_TYPE_VALUES,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_VALUES,
)

#: A receipt written before the record was versioned at all. Read, never
#: rewritten (#148 §4.6): a receipt records what the engine did on a day, and
#: back-dating one to a shape that did not exist then would make it a worse
#: record rather than a better one. What eventually removes these is the cutover
#: squash, not any migration in this slice.
LEGACY_SCHEMA_VERSION = 0

#: The shape with two versions, a typed subject and three sections — this one.
#: Named separately from the constant below because they answer different
#: questions and will stop being equal: this identifies a SHAPE, permanently,
#: and is what a reader dispatches on.
SECTIONED_SCHEMA_VERSION = 1

#: THE SHAPE A RECEIPT BUILT TODAY DECLARES, AND ONLY THAT. Bump this when a key
#: moves, arrives or leaves — never because an amount would come out
#: differently, which is what `pricing_engine_version` is for.
RECEIPT_SCHEMA_VERSION = SECTIONED_SCHEMA_VERSION

#: EVERY SHAPE THIS CODE CAN READ, which is deliberately not the one shape it
#: WRITES. A writer declares a version; a reader knows a set of them, and the
#: day the two are confused is the day a receipt written last year stops being
#: readable because the code moved on — the exact failure the pair of versions
#: exists to prevent. Adding a shape means adding a branch AND a member here.
READABLE_SCHEMA_VERSIONS = frozenset({LEGACY_SCHEMA_VERSION,
                                      SECTIONED_SCHEMA_VERSION})

TOP_LEVEL_KEYS = frozenset({
    "receipt_schema_version", "pricing_engine_version",
    "subject_type", "subject_id", "effective_at", "currency",
    "costing", "pricing", "totals", "provenance",
})

SECTION_KEYS = frozenset({"method", "status", "detail"})

TOTALS_KEYS = frozenset({"provider_cost_micros", "billed_cost_micros"})

#: WHAT A PER-QUANTITY COMPONENT MUST CARRY FOR THE RECORD TO OUTLIVE THE
#: MEASUREMENTS IT EXPLAINS (#350, #153 §12.4).
#:
#: The measured detail is a child record with a retention horizon of its own and
#: this record is kept for six years, so a component that named a quantity and a
#: total would explain nothing the day that detail expires. Each one therefore
#: carries the quantity, the rule's per-unit rate, **the denominator it is
#: divided by** and the flat addend, all by value, beside the amount they
#: produced — enough for a reader holding only this record to redo the sum, and
#: enough for a recovery to re-price the line.
#:
#: **A MINIMUM AND NOT AN EXACT SET, WHICH IS THE OPPOSITE OF THE TWO ABOVE.**
#: The top-level and section key sets are exact because a field arriving in the
#: record's *shape* should be a decision rather than a drift. `detail` is the
#: open part by design — it holds whatever explains a section's outcome, which
#: is usually method-specific — so what is asked of a component is that it
#: explains its amount, never that it explains nothing else.
#:
#: ⚠ **THE ARITHMETIC SHAPE JOINS THE SET HERE, AND ITS ABSENCE WAS A LEDGER
#: CEILING RATHER THAN A JUDGEMENT (#366).** A component records which shape its
#: rule had — whether the amount is per unit of quantity or a component applying
#: once — and `_component` has always written it, so the record was complete;
#: what could not happen was requiring it, because the key was spelled with a
#: word the registry had retired and the ratchet caps how many files may carry
#: one. This module was not among them, so naming it would have put the count
#: over its ledger entry and failed the sweep. The commit that renames the
#: column is the one that clears that, which is this one.
#:
#: **AND IT IS NOT DECORATION.** `Rate.compute` BRANCHES on this value: a
#: fixed-component rule is its fixed term and nothing else, while a per-unit
#: rule divides. A component missing it cannot be recomputed at all — and worse,
#: a reader assuming the per-unit formula answers CORRECTLY for a fixed rule
#: whose per-unit term happens to be zero, which is the accident that reads as
#: coverage. Requiring it is what makes "enough to redo the sum" true rather
#: than nearly true.
#:
#: ⚠ And this set spells the retired PLURAL, which is a different thing: that
#: word is a retired SENSE rather than sweep input, so it costs an entry in the
#: sense's own evidence block rather than a ledger seat. It is written here
#: because the quantity is the first thing the obligation names, and a minimum
#: that left it out would admit a component nobody can recompute.
REQUIRED_COMPONENT_KEYS = frozenset({
    "measurement_key", "units",
    "rate_per_unit_micros", "unit_quantity", "fixed_micros",
    "rate_structure",
    "micros",
})

#: WHAT A PRICE DERIVED AS A MARGIN OVER COST MUST CARRY, BY VALUE (#357).
#:
#: The content obligation above, asked of the rung that produces most of this
#: system's prices. A record saying only *it was a margin* explains nothing: a
#: tenant asked why a line is what it is needs the percentage that was applied
#: and the basis it was applied to, and neither can be recovered afterwards,
#: because the record the percentage came from can be edited or withdrawn. With
#: these three a reader holding only the receipt can redo the sum.
#:
#: **THE BASIS IS NOT A DUPLICATE OF `totals.provider_cost_micros`.** That
#: column is null wherever the cost is not settled, and a cost the tenant
#: declares does not exist is exactly such a case AND a genuine zero to take a
#: margin over — so the totals cannot always supply the number the arithmetic
#: used.
#:
#: **EXACT, NOT A MINIMUM, WHICH IS THE OPPOSITE OF THE SET ABOVE.** A component
#: is one of many and explains its own line, so what is asked of it is that it
#: explains its amount and never that it explains nothing else. These are the
#: WHOLE terms of one derivation, so a fourth arriving in them is a term nobody
#: declared, and a margin quietly acquiring one is the composition #147 §2
#: refuses.
#:
#: ⚠ **THE FLAT ADDEND LEFT THIS SET WITH THE RECORDS THAT COULD SUPPLY ONE
#: (#369).** It was here because two rungs carried a per-event uplift column —
#: the customer-override record and the plan catalog — and a receipt omitting a
#: term its own amount depended on explains nothing. Both records are deleted
#: and the rung that remains never had such a column, so the term would now be a
#: zero nobody declared, which is the composition #147 §2 refuses wearing the
#: clothes of completeness.
#:
#: ⚠ **A RECEIPT WRITTEN WITH THREE TERMS IS REFUSED BY THIS BOUNDARY, AND
#: THAT REACHES ONE PATH BEYOND CONSTRUCTION.** Reading a stored receipt does
#: not come through here — the readers below take what the record declares —
#: but :func:`completed_receipt` re-validates the whole assembled record, so
#: completing the COST side of a posting whose price was already settled by
#: markup would put the older price section through this set and fail. It is
#: stated rather than handled: **this tree is deployed nowhere and holds no
#: stored receipt**, and #155 §11 squashes at cutover. A tolerant set would be a
#: boundary that accepts the term forever, which is the debt this deletes.
REQUIRED_MARKUP_KEYS = frozenset({
    "micro_percent", "basis_micros",
})

#: WHAT THE MARKUP RUNG'S OWN ENTRY IS CALLED, IN BOTH SECTIONS THAT HOLD ONE.
#:
#: The terms above sit under this key in the price section's `detail`, and the
#: rung and the record they came from sit under the SAME key in `provenance`.
#: That is deliberate rather than a coincidence to be tidied apart: they are two
#: halves of one answer — what the margin was, and where the percentage came
#: from — and one name in both places is what lets a reader find the second half
#: once they have found the first. What separates them is the section they are
#: in, which is the receipt's own distinction: `detail` holds values and
#: `provenance` holds ids, and the boundary below refuses a figure in the
#: second.
#:
#: Named rather than spelled, because two modules address it — this boundary and
#: the writer in `services/pricing_service.py` — and a literal at each is how two
#: modules come to disagree about one key.
MARKUP_TERMS_KEY = "markup"

#: WHAT THE SUBJECT'S WHOLE-WORK PRICING REGIME IS CALLED IN THE PRICE
#: SECTION'S DETAIL (#418, #151 §8.4).
#:
#: Whether a whole piece of work is priced event by event or sold for ONE
#: AGREED PRICE decides whether an event carries a customer price at all, so it
#: explains the pricing section's outcome and rides there BY VALUE — never
#: looked up live against configuration that can have moved since the day the
#: record was written.
#:
#: Named rather than spelled, for `MARKUP_TERMS_KEY`'s reason: three modules
#: address it now — this boundary, the compute spine that writes it, and the
#: recovery run that re-resolves from it — and a literal at each is how three
#: modules come to disagree about one key.
PRICING_REGIME_KEY = "pricing_mode"

#: WHOSE AMOUNTS THIS ENGINE DERIVED, AND WHOSE IT DID NOT (#418).
#:
#: The method is *how an amount was arrived at*, so it is present exactly when
#: an amount was ARRIVED AT — and only one of the two subjects a receipt may
#: explain has amounts of that kind. Resolution derives a usage row's price and
#: its cost from configuration in force at an instant; a Charge's price was
#: **agreed** before the work ran and pinned to it, and its supplier cost is
#: zero because there is no supplier behind a Charge at all. Neither number was
#: reached by a method, and coining one that meant *there wasn't a method* would
#: be the second encoding of the status this module already refuses.
#:
#: **WHAT THIS RELAXES IS ONE DIRECTION AND NOT THE RULE.** *A method with no
#: amount to explain* stays refused for every subject; what a Charge's receipt
#: may do is settle an amount and name no method. And the licence is not free:
#: :data:`PRICING_REGIME_KEY` is compulsory on such a record, so *the price was
#: agreed* is a statement the record MAKES rather than one a reader infers from
#: a null.
#:
#: A SET AND NOT A `!=` AGAINST THE CHARGE, because the question is which
#: subjects derive rather than which one does not — a third subject arriving
#: would otherwise be silently admitted into the relaxation by the shape of the
#: comparison rather than by anybody's decision.
DERIVES_ITS_AMOUNTS = frozenset({PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT})


class ReceiptShapeError(ValueError):
    """A record that does not explain an amount, refused before persistence."""


@dataclass(frozen=True)
class ReceiptSubject:
    """WHAT THIS RECEIPT EXPLAINS — a declared value, not an inference.

    Frozen and carried rather than assembled at the construction boundary,
    because the subject is an INPUT to resolution: the resolver is asked to
    price a subject as of an instant, and a receipt whose subject was decided
    afterwards would be a record about whatever the caller had to hand.
    """

    subject_type: str
    subject_id: str


@dataclass(frozen=True)
class Resolution:
    """One side of the receipt — how an amount was arrived at, and whether it is.

    Four facts that must agree, named rather than ordered, and checked together
    at the boundary below: the method, the status, the amount, and the detail
    that explains the amount by value.
    """

    #: HOW THE AMOUNT WAS ARRIVED AT, or `None` when none was. Never a value
    #: meaning "there wasn't one" — see the module docstring.
    method: Optional[str]
    #: The section's own status vocabulary. This is what a reader consults.
    status: str
    #: The denominated outcome, `None` wherever the status is not settled.
    amount_micros: Optional[int]
    #: What explains this side's outcome, by value. Open on purpose — the
    #: content obligation lives in here, and its minimum for a priced quantity
    #: is :data:`REQUIRED_COMPONENT_KEYS`.
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _SectionRules:
    """What one section's three fields are allowed to say.

    One rule, two declarations, for the same reason `core.cost_totals` takes a
    pair rather than holding a column name: the price side's settled status is
    not even spelled the same as the cost side's would be if they were assumed
    equal, and a rule that assumed it is a rule with one section's answer baked
    in.
    """

    methods: frozenset
    statuses: frozenset
    settled: str
    amount_key: str
    #: THE ONE STATUS A SECTION MAY BE COMPLETED FROM (#363).
    #:
    #: ⚠ **A WHITELIST, AND IT HAS TO BE ONE.** Every unsettled status leaves a
    #: section's method and amount null — `unresolved` and `unknown`, which say
    #: UBB does not have the information, and `waived` and `not_applicable`,
    #: which say somebody made a decision — so *not settled* and *completable*
    #: are indistinguishable in the SHAPE and are different facts. Naming the
    #: settled status and admitting everything else would make a waived charge
    #: completable into a charged amount, which is exactly what ruling 12c
    #: refuses.
    completable: str


#: Each section's rules, with its amount key and its completable status taken
#: from the pair that already declares them (`core.amount_status_pairs`) rather
#: than spelled again here. Two copies of one column name is how a rule about
#: the receipt and a rule about the columns beside it come to disagree, and the
#: database rule that seals a receipt makes the same join.
SECTIONS = {
    "costing": _SectionRules(
        methods=COSTING_METHOD_VALUES, statuses=COSTING_STATUS_VALUES,
        settled=COSTING_STATUS_KNOWN,
        amount_key=SUPPLIER_COST.amount_column,
        completable=SUPPLIER_COST.unresolved_status),
    "pricing": _SectionRules(
        methods=PRICING_METHOD_VALUES, statuses=PRICING_STATUS_VALUES,
        settled=PRICING_STATUS_KNOWN,
        amount_key=CUSTOMER_PRICE.amount_column,
        completable=CUSTOMER_PRICE.unresolved_status),
}

#: WHICH RUN COMPLETED A SECTION, in `provenance` where the cross-references
#: live. The receipt's shape has always said provenance carries the ids of the
#: matched rule, the publish, the cost rates *and where applicable the run that
#: completed it*; this is that key, named once so the writer and every reader
#: spell it the same way.
RESOLUTION_RUN_KEY = "resolution_run_id"


def build_receipt(*, subject, effective_at, currency, pricing_engine_version,
                  costing, pricing, provenance=None):
    """THE ONE PLACE A RECEIPT IS BUILT, AND THE PLACE THAT VALIDATES IT.

    Assembles the record and refuses it if it does not explain an amount —
    before anything can persist it, and by raising rather than by returning a
    verdict a caller can ignore.

    :param subject: a :class:`ReceiptSubject`
    :param effective_at: the instant this resolution was made as of
    :param currency: the denomination every amount below is in
    :param pricing_engine_version: the engine's own version, passed in
    :param costing: a :class:`Resolution` for the supplier side
    :param pricing: a :class:`Resolution` for the customer side
    :param provenance: cross-reference ids, and nothing else
    :raises ReceiptShapeError: if the assembled record is not a valid receipt
    """
    record = {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "pricing_engine_version": pricing_engine_version,
        "subject_type": subject.subject_type,
        "subject_id": subject.subject_id,
        "effective_at": effective_at,
        "currency": currency,
        "costing": {"method": costing.method, "status": costing.status,
                    "detail": _copied(costing.detail)},
        "pricing": {"method": pricing.method, "status": pricing.status,
                    "detail": _copied(pricing.detail)},
        "totals": {"provider_cost_micros": costing.amount_micros,
                   "billed_cost_micros": pricing.amount_micros},
        "provenance": _copied(provenance or {}),
    }
    validate_receipt(record)
    return record


def written_in_the_current_shape(record):
    """Can this record be completed, and can it be made to name what completed it?

    One question with one answer, asked BEFORE a completion is assembled and
    again inside :func:`completed_receipt`, so a caller deciding whether a
    posting is recoverable and the boundary refusing a bad record cannot come to
    disagree about which records those are.

    A record in an older shape is `False` here rather than upgraded: the
    receipt's own ruling is that such a record is *read, never rewritten*. So is
    the empty default, which explains nothing and has nothing to complete. That
    is a fact about the posting rather than an error to route around — and it is
    what makes *a completed field can always be explained by the act that
    completed it* true rather than nearly true, because a record this answers
    `False` for is one no completion may touch at all.
    """
    return (isinstance(record, dict)
            and record.get("receipt_schema_version") == RECEIPT_SCHEMA_VERSION)


def completed_receipt(record, *, sections, provenance=None):
    """A STORED RECEIPT WITH ITS UNRESOLVED SECTIONS COMPLETED (#363).

    The one place a receipt is *changed* rather than built, and it may make
    exactly the change the database admits: a section recorded as unresolved
    moves to settled — status, method and amount in one statement — the
    provenance gains a cross-reference, and **nothing else moves at all**.
    `usage/migrations/0040` refuses everything else at the table, through every
    door; this refuses the same things one layer up, where the caller can be
    told which section and why, and so that a wrong record never reaches a
    statement in the first place.

    :param record: the receipt as stored, which is where the completion starts
        from. It is NOT rebuilt from a fresh resolution: everything outside the
        completed sections — the instant, the currency, the engine version, the
        other section — is what the engine recorded on the day, and a rebuild
        would quietly restate today's answer to a question asked then.
    :param sections: ``{section name: Resolution}``, the freshly resolved side
        for each section being completed. A section absent here is untouched.
    :param provenance: cross-references to ADD. Existing keys are kept; a key
        that would change a recorded value is refused.
    :raises ReceiptShapeError: if the record is not a receipt this code writes,
        if a named section is not completable, or if the result would not be a
        valid receipt.

    **A RECORD IN AN OLDER SHAPE IS REFUSED HERE, NOT UPGRADED.** The receipt's
    own ruling is that such a record is *read, never rewritten* — so a caller
    holding one has a posting whose price cannot be completed, which is a fact
    about that posting rather than an error to route around.
    """
    if not isinstance(record, dict):
        raise ReceiptShapeError(f"a receipt is a record, not {type(record)!r}")
    if not written_in_the_current_shape(record):
        raise ReceiptShapeError(
            f"a completion writes the shape this code writes "
            f"({RECEIPT_SCHEMA_VERSION}); this record declares "
            f"{record.get('receipt_schema_version')!r}, and a receipt in an "
            f"older shape is read, never rewritten")

    completing = dict(record)
    completing["totals"] = dict(record["totals"])

    for name, resolution in sections.items():
        rules = SECTIONS[name]
        was = record[name]
        # THE WHITELIST, ASKED BEFORE ANYTHING IS ASSEMBLED. `waived` and
        # `not_applicable` leave a section looking exactly like `unknown` and
        # `unresolved` do — no method, no amount — so the question is which
        # status it says, never whether it has an amount.
        if was["status"] != rules.completable:
            raise ReceiptShapeError(
                f"the {name} section says {was['status']!r} and only a section "
                f"recorded as {rules.completable!r} may be completed: a "
                f"decision somebody made is not information UBB is missing")
        if (resolution.status != rules.settled
                or resolution.method is None
                or resolution.amount_micros is None):
            raise ReceiptShapeError(
                f"completing the {name} section means settling it — status "
                f"{rules.settled!r} carrying a method and an amount; got "
                f"status {resolution.status!r}, method {resolution.method!r}, "
                f"amount {resolution.amount_micros!r}")
        completing[name] = {"method": resolution.method,
                            "status": resolution.status,
                            "detail": _copied(resolution.detail)}
        completing["totals"][rules.amount_key] = resolution.amount_micros

    # ADDITIVE ONLY, AND REFUSED RATHER THAN RESOLVED. The database asks
    # containment, which a changed value fails silently from the caller's point
    # of view — it sees `IntegrityError` and no key name. Refusing here names
    # the key, and refusing rather than preferring one of the two values is the
    # point: two writers disagreeing about a cross-reference is not something
    # this function may pick a winner for.
    recorded = record["provenance"]
    for key, value in (provenance or {}).items():
        if key in recorded and recorded[key] != value:
            raise ReceiptShapeError(
                f"provenance.{key} already records {recorded[key]!r}; a "
                f"completion may add a cross-reference and may not change one")
    completing["provenance"] = {**recorded, **(provenance or {})}

    validate_receipt(completing)
    return completing


def _copied(container):
    """A caller's container, copied so the record is the record.

    Copied rather than coerced: `dict(something_that_is_not_a_mapping)` raises
    its own error before the record is assembled, and a caller who handed a list
    where a record belongs would be told about a dictionary update sequence
    rather than about the receipt. Whatever it is arrives at the validator
    below, which says what is wrong with it in the receipt's own words.
    """
    return dict(container) if isinstance(container, dict) else container


def validate_receipt(record):
    """Does this record explain an amount? Raises if not.

    Public because the claim worth asserting is about what is IN THE COLUMN, not
    about what a constructor returned — a test that records through the route
    and validates the stored receipt is the check that stays true when somebody
    adds a second writer. It is not a second construction boundary: nothing
    calls it to bless a record it built itself, and the gate over the tree is
    what says so.
    """
    if not isinstance(record, dict):
        raise ReceiptShapeError(f"a receipt is a record, not {type(record)!r}")

    declared = record.get("receipt_schema_version")
    if declared != RECEIPT_SCHEMA_VERSION:
        raise ReceiptShapeError(
            f"receipt_schema_version must be {RECEIPT_SCHEMA_VERSION}, "
            f"not {declared!r}")

    if set(record) != TOP_LEVEL_KEYS:
        raise ReceiptShapeError(
            f"a receipt carries exactly {sorted(TOP_LEVEL_KEYS)}; "
            f"found {sorted(record)}")

    _require_text(record, "pricing_engine_version")
    _require_text(record, "subject_id")
    _require_text(record, "effective_at")
    _require_text(record, "currency")

    subject_type = record["subject_type"]
    if subject_type not in PRICING_RECEIPT_SUBJECT_TYPE_VALUES:
        raise ReceiptShapeError(
            f"subject_type must be one of "
            f"{sorted(PRICING_RECEIPT_SUBJECT_TYPE_VALUES)}, "
            f"not {subject_type!r}")

    totals = record["totals"]
    if not isinstance(totals, dict) or set(totals) != TOTALS_KEYS:
        raise ReceiptShapeError(
            f"totals carries exactly {sorted(TOTALS_KEYS)}; found {totals!r}")

    derived = subject_type in DERIVES_ITS_AMOUNTS
    for name, rules in SECTIONS.items():
        _validate_section(name, record[name], totals[rules.amount_key], rules,
                          derived=derived)

    if subject_type == PRICING_RECEIPT_SUBJECT_TYPE_CHARGE:
        _validate_the_agreed_regime(record["pricing"]["detail"])

    _validate_provenance(record["provenance"])


def _validate_the_agreed_regime(detail):
    """A CHARGE'S RECEIPT SAYS THE PRICE WAS AGREED, IN THE RECORD ITSELF.

    :data:`DERIVES_ITS_AMOUNTS` lets this subject settle an amount without
    naming a method; this is what stops that being a hole. A reader meeting a
    settled price with no method has to be able to tell *the price was agreed
    before the work ran* from *somebody forgot to record how it was derived*,
    and a null cannot say which — so the regime that makes the first one true
    is carried by value and refused when it is missing.

    ⚠ **IT IS THE FIXED REGIME SPECIFICALLY, NOT MERELY THE KEY.** A Charge
    exists because a whole piece of work was sold at one agreed price:
    `charge_for_delivered_work` writes one only where a price was pinned, and
    `ck_task_agreed_price_only_on_a_whole_fixed_unit` admits a pinned price
    only on such a piece of work. A record claiming the other regime
    contradicts the only thing that could have produced it, and a ticket that
    ever makes a Charge out of something else meets this refusal rather than
    slipping past a presence check.
    """
    if detail.get(PRICING_REGIME_KEY) != PRICING_MODE_FIXED:
        raise ReceiptShapeError(
            f"a receipt whose subject is a Charge carries "
            f"pricing.detail.{PRICING_REGIME_KEY} = {PRICING_MODE_FIXED!r}; "
            f"found {detail.get(PRICING_REGIME_KEY)!r}. The price was agreed "
            f"before the work ran rather than derived, which is why the "
            f"section names no method, and the record has to say so")


def _require_text(record, key):
    value = record[key]
    if not isinstance(value, str) or not value:
        raise ReceiptShapeError(f"{key} must be a non-empty string, not {value!r}")


def _validate_section(name, section, amount, rules, *, derived):
    """THE ONE RULE, ASKED OF ONE SECTION: amount, status and method agree.

    An amount is present exactly when the status says the resolution is settled.
    The method is *how that amount was arrived at*, so it is present at most on
    the same condition — and exactly on it where the subject's amounts were
    arrived at at all. Stated once here and asked of both sections, so the day
    somebody repairs it they repair it for the price side as well as the cost
    side.

    ``derived`` is :data:`DERIVES_ITS_AMOUNTS`, decided once for the whole
    record by the subject it explains. It is a parameter rather than a second
    read of the record because the subject is a fact about the RECEIPT and this
    function's whole scope is one section: a section reading the top-level
    subject for itself would be the second copy of that question.
    """
    if not isinstance(section, dict) or set(section) != SECTION_KEYS:
        raise ReceiptShapeError(
            f"the {name} section carries exactly {sorted(SECTION_KEYS)}; "
            f"found {section!r}")
    if not isinstance(section["detail"], dict):
        raise ReceiptShapeError(
            f"{name}.detail is a record of values, not {section['detail']!r}")

    status = section["status"]
    if status not in rules.statuses:
        raise ReceiptShapeError(
            f"{name}.status must be one of {sorted(rules.statuses)}, "
            f"not {status!r}")

    method, settled = section["method"], status == rules.settled
    if method is not None and method not in rules.methods:
        raise ReceiptShapeError(
            f"{name}.method must be null or one of {sorted(rules.methods)}, "
            f"not {method!r}")
    # THE DIRECTION THAT NEVER RELAXES: a method beside an unsettled status is
    # a claim about how a number was reached with no number beside it, and no
    # subject has a reason to make one.
    if method is not None and not settled:
        raise ReceiptShapeError(
            f"{name}.method says {method!r} and {name}.status says {status!r}: "
            f"a method is how an amount was arrived at, so there is none to "
            f"name unless the status is {rules.settled!r}")
    # AND THE DIRECTION THE SUBJECT DECIDES. A usage row's amounts are what
    # resolution derived, so a settled one owes the method that derived it; a
    # Charge's were agreed and definitional, and the regime the record carries
    # by value is what says so (`_validate_the_agreed_regime`).
    if derived and settled and method is None:
        raise ReceiptShapeError(
            f"{name}.method is null and {name}.status says {status!r}: this "
            f"receipt's subject is one of {sorted(DERIVES_ITS_AMOUNTS)}, whose "
            f"amounts resolution DERIVED, so a settled one says how. A subject "
            f"whose amounts are not derived is the one left out of that set")

    if isinstance(amount, bool) or not isinstance(amount, (int, type(None))):
        raise ReceiptShapeError(
            f"totals.{rules.amount_key} is a whole number of micros or null, "
            f"not {amount!r}")
    if settled != (amount is not None):
        raise ReceiptShapeError(
            f"totals.{rules.amount_key} is {amount!r} and {name}.status is "
            f"{status!r}: an amount is present exactly when the status is "
            f"{rules.settled!r}")

    # ASKED ONLY WHERE THE KEY IS THERE, AND NEVER COERCED. A section that
    # priced no quantity has no components and that is not a fault; a section
    # whose `components` is a record, a zero or a `False` is a fault, and
    # `x or []` would have turned every one of those into "no components" on
    # its way past the refusal below.
    if "components" in section["detail"]:
        _validate_components(name, section["detail"]["components"])

    # ASKED OF EVERY SECTION, AND ONLY ONE SECTION'S VOCABULARY HAS THIS
    # METHOD — which is why the rule is written as a question about the method
    # rather than as a rule about the price side. The cost side's two methods
    # say how UBB came by a SUPPLIER's figure; taking a margin is not one of
    # them and cannot become one without this branch being reconsidered.
    if method == PRICING_METHOD_MARGIN_OVER_COST:
        _validate_markup_terms(name, section["detail"].get(MARKUP_TERMS_KEY))


def _validate_components(name, components):
    """THE CONTENT OBLIGATION, REFUSED AT THE BOUNDARY RATHER THAN ASSERTED.

    A component that does not carry its terms is a line nobody can explain once
    the measurement detail behind it is gone — and the whole reason this
    function is reached from the one construction site is that a record which
    explains nothing must not be able to reach the column at all. Asked of both
    sections from the rule above, so the day somebody repairs it they repair it
    for the price side as well as the cost side.

    A section with no components is not a fault: a cost the caller supplied, a
    declaration that says there is no cost, and a price derived as a margin over
    one all arrive at an amount without pricing a single quantity. What is
    refused is a component that claims to explain one and does not.
    """
    if not isinstance(components, list):
        raise ReceiptShapeError(
            f"{name}.detail.components is a list of priced quantities, not "
            f"{components!r}")
    for component in components:
        if not isinstance(component, dict):
            raise ReceiptShapeError(
                f"a {name} component is a record of values, not {component!r}")
        missing = REQUIRED_COMPONENT_KEYS - set(component)
        if missing:
            raise ReceiptShapeError(
                f"a {name} component is missing {sorted(missing)}: a component "
                f"carries the quantity, the rule's terms and the denominator "
                f"by value, because the measurement detail behind it expires "
                f"and this record does not")


def _validate_markup_terms(name, terms):
    """A MARGIN THAT DOES NOT SAY WHAT PERCENTAGE, OVER WHAT, EXPLAINS NOTHING.

    Markup is the default pricing path — it runs wherever no rule matched — so
    this is the obligation on the record that most prices in the system carry.
    Before it, the receipt said only that a margin had been taken, and the
    percentage was recoverable solely by re-reading configuration that may have
    moved: the exact failure the receipt exists to prevent, on the path that
    produces the most receipts.

    Refused HERE rather than asserted in the resolver's tests, for the reason
    the component rule gives: a record that explains nothing must not be able to
    reach the column at all, and a rule enforced at the one construction
    boundary holds for a writer nobody has written yet.

    **THE SET IS EXACT, AND WHAT IT REFUSES IN THE OTHER DIRECTION IS
    COMPOSITION.** A fourth term appearing beside these three is a floor, a cap
    or a second addend nobody declared — the chain whose middle terms are on no
    record, which is what non-composition exists to prevent.

    ⚠ **IT ASKS NOTHING ABOUT THE RUNG.** Which rung supplied the percentage is
    `provenance`'s answer, and it is deliberately not required here: a markup
    and a rule declaring `margin_over_cost` are the SAME METHOD AT TWO RUNGS,
    and a boundary that demanded a rung name would be a boundary that had picked
    one of them.
    """
    if not isinstance(terms, dict):
        raise ReceiptShapeError(
            f"{name}.method is {PRICING_METHOD_MARGIN_OVER_COST!r} and "
            f"{name}.detail.{MARKUP_TERMS_KEY} is {terms!r}: a margin over cost "
            f"records the percentage applied and the basis it was taken over, "
            f"by value, because the record that held the percentage can be "
            f"edited and this one cannot")
    if set(terms) != REQUIRED_MARKUP_KEYS:
        raise ReceiptShapeError(
            f"{name}.detail.{MARKUP_TERMS_KEY} carries exactly "
            f"{sorted(REQUIRED_MARKUP_KEYS)}; found {sorted(terms)}")
    for term, value in terms.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ReceiptShapeError(
                f"{name}.detail.{MARKUP_TERMS_KEY}.{term} is a whole number, "
                f"not {value!r}: every term of the arithmetic is written down "
                f"so a reader holding only this record can redo it")


def _validate_provenance(provenance):
    """CROSS-REFERENCE IDS, AND NOTHING ELSE.

    A number in here is refused rather than tolerated, because the section's
    whole job is to be the part of the record nobody can reconstruct an amount
    from. Enforcing "no amount can be in there in the first place" is a stronger
    statement than a convention, and it is the half a test cannot make: the
    other half — that no read path goes to a referenced record for a figure — is
    asserted by mutating one and showing the totals do not move.
    """
    if not isinstance(provenance, dict):
        raise ReceiptShapeError(
            f"provenance is a record of ids, not {provenance!r}")
    for key, value in provenance.items():
        for leaf in _leaves(value):
            if not isinstance(leaf, str):
                raise ReceiptShapeError(
                    f"provenance.{key} carries {leaf!r}: this section carries "
                    f"cross-reference ids only, and a value that is not one is "
                    f"a figure somebody would read back")


def _leaves(value):
    if isinstance(value, dict):
        for inner in value.values():
            yield from _leaves(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            yield from _leaves(inner)
    else:
        yield value


def schema_version_of(receipt):
    """Which shape this record is in, asked of the RECORD.

    A receipt with no version is one written before the record carried one, and
    it reads as :data:`LEGACY_SCHEMA_VERSION` rather than as a fault: the read
    path tolerates both shapes and nothing rewrites the older one.
    """
    if not isinstance(receipt, dict):
        return LEGACY_SCHEMA_VERSION
    return receipt.get("receipt_schema_version", LEGACY_SCHEMA_VERSION)


def _readable_version_of(receipt):
    """The version a reader may act on, or a refusal — the guard both readers
    below share.

    **THE DISPATCH IS THREE-WAY, NOT TWO.** A version this code does not know is
    REFUSED rather than read as the current shape: "old record, new code" is the
    direction that happens and is answered, and the other direction — a record
    written by something newer — cannot be read by guessing, so guessing would
    turn a shape it does not understand into a plausible wrong answer or a
    `KeyError` from the middle of a request.

    Extracted rather than written twice (#355). It takes no path and reads no
    section, so each reader below still says in its own body what it reads and
    from where; what is shared is only the question *may this record be read at
    all*, which has one answer for the whole module.
    """
    if not isinstance(receipt, dict):
        return None
    version = schema_version_of(receipt)
    if version not in READABLE_SCHEMA_VERSIONS:
        raise ReceiptShapeError(
            f"this receipt declares schema version {version!r}; this code reads "
            f"{sorted(READABLE_SCHEMA_VERSIONS)}")
    return version


def uncosted_quantity_keys(receipt):
    """WHICH DECLARED QUANTITIES WENT UNCOSTED, out of a receipt of any shape.

    Read by the recording surfaces, which answer it beside `costing_status` —
    the status says THAT a cost is unresolved and this says which declaration to
    fix. An idempotent replay serves the receipt the posting was recorded with,
    so this is a live read path over rows in the older shape rather than a
    migration courtesy.

    The three-way dispatch this rests on is :func:`_readable_version_of`, which
    both readers share; what is written here is only where THIS answer lives in
    each shape.
    """
    version = _readable_version_of(receipt)
    if version is None:
        return []
    if version == LEGACY_SCHEMA_VERSION:
        return receipt.get("uncosted_measurement_keys", []) or []
    return receipt["costing"]["detail"].get("uncosted_measurement_keys", []) or []


def recorded_quantities(receipt):
    """WHAT THE ENGINE PRICED, BY VALUE — the bag a recovery re-resolves from.

    `{declared quantity name: quantity}`, assembled out of the record rather
    than out of the measurement rows beside it, and that is the whole point of
    the content obligation (#350, #153 §12.4): the measured detail is a child
    record with a retention horizon of its own and this record is kept for six
    years, so a recovery that read the child rows would stop working silently on
    exactly the postings that most need fixing. A snapshot is a fact that is
    either there or not.

    THREE PLACES HOLD IT AND THEY ARE VIEWS OF ONE BAG. A quantity that had a
    cost rate is a costing component; one that had none is in the costing
    section's uncosted mapping; and one on a posting whose cost was stated by
    the caller, or declared not to exist, appears only as a PRICE component,
    because the cost side of such a receipt records no components at all. Taking
    the union is what makes this the bag the engine saw, rather than whichever
    part of it the reader happened to look at.

    ⚠ A RECEIPT IN AN OLDER SHAPE ANSWERS EMPTY, which is what it is: that shape
    recorded no per-quantity terms, so there is nothing in it to re-resolve from
    and a caller must not be handed a partial bag that looks like a whole one.
    """
    if _readable_version_of(receipt) != SECTIONED_SCHEMA_VERSION:
        return {}
    quantities = {}
    for name in SECTIONS:
        # `.get` WITHOUT A FALLBACK COERCION, WHICH IS THE DIFFERENCE THAT
        # MATTERS. A section that priced no quantity legitimately has no
        # `components` key, and that is the default here; a section whose
        # `components` is a record, a zero or a `False` is a corrupt record, and
        # `x or []` would turn every one of those into "no components" on the
        # way past — the same coercion the validator beside this refuses to
        # make, for the same reason.
        for component in receipt[name]["detail"].get("components", []):
            quantities.setdefault(component["measurement_key"],
                                  component["units"])
    uncosted = receipt["costing"]["detail"]
    if "uncosted_quantities" in uncosted:
        quantities.update(uncosted["uncosted_quantities"])
    return quantities


def pricing_method_of(receipt):
    """HOW THIS RECEIPT'S CUSTOMER PRICE WAS DERIVED, or `None` (#355).

    `None` means the price was **not derived** — it was agreed, or there is
    none — and which of those it was is read off the price status beside it.
    That rule is argued in full where the rule's own column is declared
    (`apps/metering/pricing/models.py`); what matters here is that the two are
    answered together and neither answers the other's question.

    Read by the recording surfaces and by the audit lookup, which is the surface
    a dispute is settled on. The three-way dispatch is
    :func:`_readable_version_of`, shared with the reader above.

    ⚠ **A RECEIPT IN THE OLDER SHAPE NAMES NO METHOD, AND THIS DOES NOT INVENT
    ONE.** What that shape recorded beside its price is the SOURCE that supplied
    it — the rung — and that is a different question from how the amount was
    derived: a markup and a rule declaring a margin are one method at two
    sources. Translating the older field into a method would therefore put a
    value on the published contract that no writer ever recorded, under a
    mapping nobody ratified. So an older receipt answers `None` — *this record
    does not say* — which is what it is.
    """
    version = _readable_version_of(receipt)
    if version is None or version == LEGACY_SCHEMA_VERSION:
        return None
    return receipt["pricing"]["method"]


def pricing_mode_of(receipt):
    """THE SUBJECT'S WHOLE-WORK PRICING REGIME, out of the record, or `None`.

    Whether the piece of work this belonged to was priced event by event or
    sold for one agreed price — by value, as it was on the day, which is the
    whole reason it is on the record. A recovery run re-resolving a posting
    reads it from here rather than from the piece of work's own row, for
    `_subject_of`'s stated reason and for #363's: what a recovery may re-derive
    is what the record can support, never what configuration says today.

    ⚠ **A RECEIPT IN THE OLDER SHAPE NAMES NO REGIME, AND THIS DOES NOT INVENT
    ONE.** That shape predates the field, so there is nothing in the record to
    read; answering *this record does not say* is what it is, and it is what
    the two readers above give a record written before their question existed.

    The three-way dispatch is :func:`_readable_version_of`, shared with them.
    """
    version = _readable_version_of(receipt)
    if version is None or version == LEGACY_SCHEMA_VERSION:
        return None
    return receipt["pricing"]["detail"].get(PRICING_REGIME_KEY)


def subject_type_of(receipt):
    """WHAT THIS RECEIPT EXPLAINS — one usage row, one Charge, or `None` (#370).

    The registry's `pricing_receipt_subject_type`, read out of the record. It is
    a stored value rather than an inference, and that is the whole of the typed
    subject: deriving it from whichever foreign key happens to be populated
    would be a SECOND authority on what a receipt is about, able to disagree
    with the one the record states. #148 §3.2 refuses a pair that must agree.

    The three-way dispatch is :func:`_readable_version_of`, shared with the two
    readers above.

    ⚠ **A RECEIPT IN THE OLDER SHAPE NAMES NO SUBJECT, AND THIS DOES NOT INVENT
    ONE.** That shape predates the typed subject, so there is nothing in the
    record to read; answering *this record does not say* is what it is. The
    alternative — reading the subject off the row the receipt is stored on — is
    the inference this function exists to refuse, and it would be published on
    the contract as a value some writer had recorded.
    """
    version = _readable_version_of(receipt)
    if version is None or version == LEGACY_SCHEMA_VERSION:
        return None
    return receipt["subject_type"]
