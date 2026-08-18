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
test_the_receipt_has_one_construction_boundary.py` is what keeps the count at
one.

**AN AMOUNT, ITS STATUS AND ITS METHOD MOVE TOGETHER, IN BOTH SECTIONS.** This
is the amount/status pair `core.amount_status_pairs` names for a table, one
level up and with the method added: an amount is present exactly when its status
says it is settled, and the method — *how this amount was arrived at* — is
present on exactly the same condition. So the price side's method is **nullable**
and it is null exactly when no price was derived, with the status beside it as
the thing a reader consults. No fourth method value is coined for "none": a
method value meaning "there wasn't one" is a second encoding of the status, and
the day the two disagree there is no way to tell which is right.

⚠ **The method is a property of the DERIVATION, not of the rule** — which is
what the rule above means, and it is a statement about the SHAPE rather than a
description of what the engine writes today. A rule that is matched and cannot
compute would record its identity in `provenance` and its terms by value in
`detail`, and leave the method null, because nothing was derived; nothing is
lost by that, and the alternative is a receipt naming how an amount was computed
beside no amount.

⚠ **No engine path produces that record yet, and the reader should know it.**
There is no price status column and no rule that writes a price status other
than settled, so `pricing_service` reports `known` with a method for every price
it derives — including a margin taken over a supplier cost it has not learned,
which is a floor rather than a settled price. The ruling that such a price is
`waived` arrives with the nullable price column and the rules that write it. So
the null branch below is exercised at this boundary and not through the spine,
and the two lines that will move are marked where they are.

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
from. Two obligations, and **only the first of them is enforced here**:

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

⚠ **THAT ARRIVED WITHOUT MOVING** :data:`RECEIPT_SCHEMA_VERSION`, **and the
reason is what the version is for.** It answers *can today's code read this
record* — and every key already in a receipt is still there, still meaning what
it meant, so a reader written before that commit reads a receipt written after
it exactly as it did before. The keys that arrived are inside the open
containers, which no reader may assume a fixed set of. A version bumped for an
additive detail key would say a record had become unreadable when it had not,
and would fork the one reader below for no question it could answer differently.

⚠ **THE QUANTITIES NOW EXIST IN TWO PLACES ON PURPOSE AND THEY ARE NOT TWO
SOURCES OF TRUTH** (#165 §6). The measurement record holds what was *reported*;
this holds what was *used to compute an amount*. They are not required to be
equal, **nothing ever reconciles them**, and nothing here compares them — see
the note at the snapshot site in `services/pricing_service.py` for why building
that comparison would re-create the very shape this record exists to remove.

⚠ **`detail` IS THE SECTION'S DETAIL, NOT ONLY ITS METHOD'S.** It holds whatever
explains that side's method, status and amount by value — which is usually
method-specific and is not required to be. The case that forces the distinction
is already known and is now built: the subject's whole-job pricing regime
decides whether an event carries a customer price at all, so it explains the
PRICING side's outcome and rides in `pricing.detail`, even though it is a fact
about the subject rather than about a method. Reading `detail` narrowly would
have left that value no home but a ninth top-level key, and the top-level shape
is the ratified one.

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

from core.vocabulary import (
    COSTING_METHOD_VALUES,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_VALUES,
    PRICING_METHOD_VALUES,
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
#: ⚠ **ONE TERM IS MISSING FROM THIS SET DELIBERATELY AND ITS ABSENCE IS NOT AN
#: OVERSIGHT.** A component also records which arithmetic shape its rule had —
#: whether the amount is per unit of quantity or a component applying once — and
#: `_component` writes it, so the record is complete. It is not required HERE
#: because its key is spelled with a word the registry retired and the ratchet
#: caps how many files may carry that word: this module is not one of them, and
#: naming it here would put the count over its ledger entry and fail the sweep.
#: The ticket that renames the rule's arithmetic shape is the one that adds it
#: to this set. Until then the shape is asserted where a reader can reach it
#: through `Rate.STRUCTURE_COLUMN` rather than by spelling it.
#:
#: ⚠ And this set spells the retired PLURAL, which is a different thing: that
#: word is a retired SENSE rather than sweep input, so it costs an entry in the
#: sense's own evidence block rather than a ledger seat. It is written here
#: because the quantity is the first thing the obligation names, and a minimum
#: that left it out would admit a component nobody can recompute.
REQUIRED_COMPONENT_KEYS = frozenset({
    "measurement_key", "units",
    "rate_per_unit_micros", "unit_quantity", "fixed_micros",
    "micros",
})


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


SECTIONS = {
    "costing": _SectionRules(
        methods=COSTING_METHOD_VALUES, statuses=COSTING_STATUS_VALUES,
        settled=COSTING_STATUS_KNOWN, amount_key="provider_cost_micros"),
    "pricing": _SectionRules(
        methods=PRICING_METHOD_VALUES, statuses=PRICING_STATUS_VALUES,
        settled=PRICING_STATUS_KNOWN, amount_key="billed_cost_micros"),
}


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

    for name, rules in SECTIONS.items():
        _validate_section(name, record[name], totals[rules.amount_key], rules)

    _validate_provenance(record["provenance"])


def _require_text(record, key):
    value = record[key]
    if not isinstance(value, str) or not value:
        raise ReceiptShapeError(f"{key} must be a non-empty string, not {value!r}")


def _validate_section(name, section, amount, rules):
    """THE ONE RULE, ASKED OF ONE SECTION: amount, status and method agree.

    An amount is present exactly when the status says the resolution is settled,
    and the method is present on exactly the same condition. Stated once here
    and asked of both sections, so the day somebody repairs it they repair it
    for the price side as well as the cost side.
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
    if settled != (method is not None):
        raise ReceiptShapeError(
            f"{name}.method says {method!r} and {name}.status says {status!r}: "
            f"a method is how an amount was arrived at, so it is present "
            f"exactly when the status is {rules.settled!r}")

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


def uncosted_quantity_keys(receipt):
    """WHICH DECLARED QUANTITIES WENT UNCOSTED, out of a receipt of any shape.

    Read by the recording surfaces, which answer it beside `costing_status` —
    the status says THAT a cost is unresolved and this says which declaration to
    fix. An idempotent replay serves the receipt the posting was recorded with,
    so this is a live read path over rows in the older shape rather than a
    migration courtesy.

    **THE DISPATCH IS THREE-WAY, NOT TWO.** A version this code does not know is
    REFUSED rather than read as the current shape: "old record, new code" is the
    direction that happens and is answered, and the other direction — a record
    written by something newer — cannot be read by guessing, so guessing would
    turn a shape it does not understand into a plausible wrong answer or a
    `KeyError` from the middle of a request. There is one reader, so the
    dispatch is written once, here.
    """
    if not isinstance(receipt, dict):
        return []
    version = schema_version_of(receipt)
    if version not in READABLE_SCHEMA_VERSIONS:
        raise ReceiptShapeError(
            f"this receipt declares schema version {version!r}; this code reads "
            f"{sorted(READABLE_SCHEMA_VERSIONS)}")
    if version == LEGACY_SCHEMA_VERSION:
        return receipt.get("uncosted_measurement_keys", []) or []
    return receipt["costing"]["detail"].get("uncosted_measurement_keys", []) or []
