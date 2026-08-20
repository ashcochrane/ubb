"""What the reported supplier cost must never become (#266).

Three rules, and all three are about the same thing seen from three sides: the
conversion from what a supplier reports to what UBB stores happens **once, in
generated code, before the wire**. Every way of getting that wrong looks
reasonable at the moment it is written, and each one puts a float or an
undeclared multiplier back on the money path the declaration exists to have
taken it off.

==============================  ===============================================
``amounts-arrive-in-micros``    The recording surface takes an integer number
                                of micros and a canonical currency code. No
                                decimal, no float, no supplier's raw number.
``one-declared-representation`` What a number represents is declared ONCE, on
                                the Event Type's mapping. A representation on
                                the wire would make two events of one Event
                                Type mean two different things, which is the
                                hand-written multiplier arriving by the front
                                door.
``no-server-side-conversion``   No module that decides money — nor the layer
                                the request arrives at — imports the
                                conversion. UBB never repeats it: the amount it
                                receives has already been converted, and a
                                second conversion is a second answer.
==============================  ===============================================

**Why the wire is the subject and not the model.** The mapping's own shape —
that it holds no amount, that it is a sibling of the declared quantities — is a
property of the model registry and is classified next door in
``test_event_type_declaration_invariants.py``, where ``no-cost-amount`` gained
its money-naming allowance for exactly this record. What is here is the half
that model cannot see: the request schema a tenant posts to, which is a
different tree with different types.

**Nothing here is new behaviour.** The wire already carried an integer micros
amount and a lowercase currency code before this ticket, and that is the point
— the rule is that it stays that way once a declaration starts describing where
the number came from. An absence gate written the day the absence is
established is one that never has to be reconstructed later from a defect.

**The obligations** (``tests/contracts/README.md``): every rule has a negative
control pushed through the real classifier, and every walk has a vacuity guard,
because a check over an absence that silently read nothing is worse than no
check at all.
"""
import ast
from decimal import Decimal
from pathlib import Path
from typing import Optional

from api.v1.schemas import RecordUsageRequest, UsageBatchRequest
from apps.platform.event_types.models import (
    REPORTED_COST_KIND_REFUSALS,
    REPORTED_COST_SOURCE_KINDS,
    ReportedCostMapping,
    V1_LIMITATION,
)
# One definition of "a field named for money" and one of "where money is
# decided", shared with the gates next door rather than copied: two encodings of
# either would drift, and the one that drifted would be the one nobody looked at.
from apps.platform.tests.test_event_type_satellite_invariants import (
    BEHAVIOURAL_SURFACES,
    MONETARY_FIELD_WORDS,
    _iter_production_sources,
)
from core.vocabulary import (
    SOURCE_KIND_CONSTANT,
    SOURCE_KIND_DERIVED,
    SOURCE_KIND_VALUES,
)

# apps/platform/tests/test_reported_cost_invariants.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

TICKET = "#266"

RULE_MICROS = "amounts-arrive-in-micros"
RULE_REPRESENTATION = "one-declared-representation"
RULE_CONVERSION = "no-server-side-conversion"

#: The schemas a tenant posts a usage event through. Both, because the batch
#: route is the one an integration under load actually uses and a rule stated
#: only about the single-event shape would be a rule about the quieter half.
RECORDING_SCHEMAS = (RecordUsageRequest, UsageBatchRequest)

#: The suffix that makes an integer an amount of money (ADR-0006 §1). A money
#: field that does not carry it is either not an amount or is an amount whose
#: unit a reader has to guess, and both are things this rule is about.
MICROS_SUFFIX = "_micros"

#: The one money word that names a denomination rather than an amount, so the
#: one that is a string on the wire rather than an integer.
CURRENCY_WORD = "currency"

#: Types that carry a fractional amount. ``Decimal`` is here beside ``float``
#: even though it is exact: the rule is not "no rounding error", it is that UBB
#: receives micros — a Decimal on the wire is the supplier's raw number arriving
#: for UBB to convert, which is the conversion that is supposed to have happened
#: already and in one place.
FRACTIONAL_TYPES = (float, Decimal)

#: What names a representation. The word alone, because the concept's own token
#: is ``amount_representation`` and any wire field carrying the idea would be
#: spelled some variation of it.
REPRESENTATION_WORD = "representation"

#: The module that owns the conversion, as a dotted path and as a leaf. Both
#: spellings, because ``from apps.platform.event_types import reported_cost``
#: and ``from .reported_cost import to_micros`` are the same reach written two
#: ways, and only one of them contains the full path.
CONVERSION_MODULE = "apps.platform.event_types.reported_cost"
CONVERSION_LEAF = "reported_cost"
CONVERSION_FUNCTIONS = ("to_micros", "pin_currency")

#: Where a server-side conversion would actually be written. The modules that
#: decide money, shared with the gate next door — plus **the composition
#: layer**, which that gate deliberately leaves out and this one cannot.
#:
#: ``BEHAVIOURAL_SURFACES`` answers "who may READ the catalogue", and `api/v1`
#: legitimately may: it is the layer ADR-001 allows to import any product. But
#: the request arrives THERE, so it is the first place a raw supplier number
#: could be converted on the way in, and a rule about repeating the conversion
#: that could not see the request handler would be a rule about everywhere the
#: number has already passed through.
CONVERTING_SURFACES = (*BEHAVIOURAL_SURFACES, "api")


def field_words(name):
    return set(name.lower().split("_"))


def _annotation_types(annotation):
    """Every concrete type inside an annotation, ``Optional`` and all.

    Flattened rather than matched, because ``Optional[int]`` and ``int`` are the
    same statement about what may arrive and a rule that only understood the
    second would be silent on most of a request schema.
    """
    found = set()
    stack = [annotation]
    while stack:
        current = stack.pop()
        if isinstance(current, type):
            found.add(current)
        stack.extend(getattr(current, "__args__", ()))
    return found


def site_of(schema, name=None):
    site = f"ubb-platform/api/v1/schemas.py::{schema.__name__}"
    return f"{site}.{name}" if name else site


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------

def classify_wire_amount(schema, name, annotation):
    """``amounts-arrive-in-micros`` — an amount is an integer of micros.

    Three failures in one rule because they are one mistake with three faces: a
    fractional type anywhere on a recording request, a money-named field that
    is not an integer, and a money-named integer that does not say it is in
    micros. Each of them is the supplier's raw number reaching UBB.
    """
    types = _annotation_types(annotation)
    words = field_words(name)
    # The code is the one money word that names a denomination and not an
    # amount, so it leaves here — but only where it is the ONLY money word
    # present. `cost_currency` is a code; `total_currency_amount` is an amount
    # that happens to mention one, and a blanket exit would have let the second
    # in behind the first.
    amount_words = words & (MONETARY_FIELD_WORDS - {CURRENCY_WORD})
    fractional = sorted(t.__name__ for t in types if t in FRACTIONAL_TYPES)
    if fractional:
        why = f"is a {', '.join(fractional)}"
    elif not amount_words:
        return None
    elif int not in types:
        why = f"is named for money and is not an integer ({annotation})"
    elif not name.endswith(MICROS_SUFFIX):
        why = "is a money integer that does not say it is in micros"
    else:
        return None
    return (
        RULE_MICROS, site_of(schema, name),
        f"{site_of(schema, name)} {why}. UBB receives an integer amount in "
        f"micros and a canonical currency code, and never the supplier's raw "
        f"decimal ({TICKET}): the conversion is emitted once, in decimal "
        f"arithmetic, by the builder — and a number that arrives unconverted "
        f"is one UBB has to convert, which is a second implementation of the "
        f"multiplier this whole declaration exists to have deleted",
    )


def classify_wire_representation(schema, name, _annotation):
    """``one-declared-representation`` — it is a declaration, not a payload.

    A per-event representation reads as flexibility and is the opposite. Two
    events of one Event Type could then mean two different things by the same
    number, nothing generated could be trusted to have converted either, and the
    declaration would be describing a shape the caller is free to contradict.
    """
    if REPRESENTATION_WORD not in field_words(name):
        return None
    return (
        RULE_REPRESENTATION, site_of(schema, name),
        f"{site_of(schema, name)} puts an amount representation on the wire. "
        f"What a supplier's number represents is declared ONCE, on the Event "
        f"Type's reported-cost mapping ({TICKET}), so that the conversion is "
        f"generated once and exactly. A per-event one lets two events of one "
        f"Event Type mean two different things by the same number, and hands "
        f"the multiplier back to the caller",
    )


def _walk_wire():
    hits, fields_seen = [], []
    for schema in RECORDING_SCHEMAS:
        for name, field in schema.model_fields.items():
            fields_seen.append(f"{schema.__name__}.{name}")
            hits.extend(filter(None, [
                classify_wire_amount(schema, name, field.annotation),
                classify_wire_representation(schema, name, field.annotation),
            ]))
    return hits, fields_seen


# ---------------------------------------------------------------------------
# The source: nothing behavioural converts
# ---------------------------------------------------------------------------

def classify_conversion_reach(label, tree):
    """``no-server-side-conversion`` — the arithmetic runs before the wire.

    Over the parsed tree and matched on whole name segments, for the reason the
    walker next door gives: a raw-text scan fails a module for saying the words
    in a comment, which is the shape of gate that gets deleted rather than
    obeyed.

    Both spellings of the reach, because ``from ... import reported_cost`` and
    ``from .reported_cost import to_micros`` are one act written two ways, and
    the function names as well — an ``importlib`` or an ``apps.get_model``-style
    indirection names no module at all, and the function it is fetching is the
    only thing left to recognise it by.
    """
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            segments = set(node.module.split("."))
            if CONVERSION_LEAF in segments or node.module == CONVERSION_MODULE:
                found.add(node.module)
            found |= {alias.name for alias in node.names
                      if alias.name in (CONVERSION_LEAF, *CONVERSION_FUNCTIONS)}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names
                      if CONVERSION_LEAF in alias.name.split(".")}
        elif isinstance(node, (ast.Name, ast.Attribute)):
            # Whole segments of the dotted name, not the dotted name itself: a
            # module fetched by name and then called reads as
            # `converter.to_micros`, and matching the full spelling would see
            # only the case where the function was imported bare — which is the
            # case the import scan above already has.
            found |= set(_dotted_name(node).split(".")) & set(CONVERSION_FUNCTIONS)
    if not found:
        return None
    return (
        RULE_CONVERSION, label,
        f"ubb-platform/{label} reaches the reported-cost conversion "
        f"({sorted(found)}). UBB never repeats it server-side ({TICKET}): the "
        f"amount it receives is already an exact number of micros, and a "
        f"second conversion is a second answer to what the supplier charged — "
        f"one of which is right and neither of which is marked. The module is "
        f"the executable definition of what the BUILDER emits, and its only "
        f"callers are the tests that hold it to that",
    )


def _dotted_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _walk_sources():
    """Every module this rule is stated about, PARSED — and only those.

    ``read`` counts the trees actually parsed rather than the paths considered,
    which is the difference between a vacuity guard and a comforting number: a
    walk whose two label sets had drifted apart would still have "considered"
    every file in the tree while classifying none of it.
    """
    hits, read = [], []
    for path, label in _iter_production_sources(CONVERTING_SURFACES):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        read.append(label)
        hits.extend(filter(None, [classify_conversion_reach(label, tree)]))
    return hits, read


_WIRE_HITS, _WIRE_FIELDS = _walk_wire()
_SOURCE_HITS, _READ = _walk_sources()


def _failures(rule):
    return "\n".join(message for name, _, message in
                     (*_WIRE_HITS, *_SOURCE_HITS) if name == rule)


# ---------------------------------------------------------------------------
# The vacuity guards
# ---------------------------------------------------------------------------

def test_the_wire_walk_actually_read_the_recording_request():
    """Two of the three rules are absences over this schema.

    The supplier-cost field by name, because it is the subject: a walk that
    lost it would report a clean sweep of absences over a request it never
    read. The currency beside it, because the rule is about the PAIR — micros
    plus a canonical code — and a walk that could see one and not the other
    could not tell a normalised wire from half of one.

    ⚠ THE FOURTH NAME USED TO BE THE CUSTOMER PRICE, AND #365 DELETED IT from
    this request: a price is resolved and held by UBB, never stated on a call.
    It is REPLACED rather than dropped, by the caller's own claimed cost — the
    other money field this request still carries, and the one whose absence
    would leave the guard blind to exactly half the amounts it exists to watch.
    Relaxing to three names instead would have made the guard weaker on the day
    a field left, which is the day it is most worth having.
    """
    assert len(_WIRE_FIELDS) > 12, f"only read {len(_WIRE_FIELDS)} fields"
    for expected in ("RecordUsageRequest.provider_cost_micros",
                     "RecordUsageRequest.claimed_provider_cost_micros",
                     "RecordUsageRequest.currency",
                     "UsageBatchRequest.events"):
        assert expected in _WIRE_FIELDS, f"the walk did not read {expected}"


def test_the_source_walk_actually_parsed_the_converting_surfaces():
    """The third rule is an absence over every module that could convert.

    ``_READ`` is what was PARSED, not what was considered — a guard over the
    second would stay green on a walk that classified nothing. The composition
    layer is named among them because it is the addition this rule makes to the
    set next door, and a silently-dropped root would leave the rule true of
    everywhere except the place the request actually arrives.
    """
    assert len(_READ) > 100, f"only parsed {len(_READ)} modules"
    for expected in ("apps/metering/queries.py",
                     "apps/metering/usage/models.py",
                     "apps/billing/tenant_billing/services.py",
                     "core/money.py",
                     "api/v1/schemas.py"):
        assert expected in _READ, (
            f"{expected} was not parsed, so the rule said nothing about the "
            f"module it is about")


def test_the_conversion_module_is_where_it_says_it_is():
    """The rule above is stated about a path, and a path that moved would make
    it silently true. Asked of the real module rather than of the constant."""
    module = PLATFORM_ROOT / CONVERSION_MODULE.replace(".", "/")
    assert module.with_suffix(".py").is_file(), f"{CONVERSION_MODULE} is gone"


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

def test_the_wire_carries_micros_and_a_currency_code():
    failures = _failures(RULE_MICROS)
    assert not failures, "\n" + failures


def test_the_representation_stays_a_declaration():
    failures = _failures(RULE_REPRESENTATION)
    assert not failures, "\n" + failures


def test_nothing_behavioural_converts_a_reported_cost():
    failures = _failures(RULE_CONVERSION)
    assert not failures, "\n" + failures


def test_the_narrowed_vocabulary_accounts_for_every_source_kind():
    """A fifth kind UBB learns arrives at this boundary unruled.

    The mapping admits two of the four and refuses the other two for two
    stated reasons. A value added to the concept would fall through both — the
    validator's catch-all would call it "not a source kind", which is untrue
    and unhelpful, and nobody would have decided whether a reported cost may be
    declared with it. This is what makes that decision a red test rather than a
    discovery.
    """
    ruled = REPORTED_COST_SOURCE_KINDS | set(REPORTED_COST_KIND_REFUSALS)

    assert ruled == SOURCE_KIND_VALUES, (
        f"the reported-cost mapping has no ruling for "
        f"{sorted(SOURCE_KIND_VALUES - ruled)}: admit it beside the two live "
        f"kinds, or refuse it with its own reason")
    assert not (REPORTED_COST_SOURCE_KINDS & set(REPORTED_COST_KIND_REFUSALS))


def test_the_two_refusals_are_two_different_refusals():
    """One is permanent and on the merits; the other is a limitation.

    A tenant who cannot tell them apart cannot tell "ask again next year" from
    "this was never going to work", and a single shared message is how two
    rulings become one shrug. Asserted on the FLAG rather than on the prose,
    because the flag is the half a later ticket can find: the one that lifts
    the limitation is looking for a refusal that says it is liftable, and
    reading each reason for a caveat is not a search anybody runs.
    """
    permanence = {kind: refusal.permanent
                  for kind, refusal in REPORTED_COST_KIND_REFUSALS.items()}

    assert permanence == {SOURCE_KIND_CONSTANT: True,
                          SOURCE_KIND_DERIVED: False}
    reasons = {refusal.reason for refusal in REPORTED_COST_KIND_REFUSALS.values()}
    assert len(reasons) == len(REPORTED_COST_KIND_REFUSALS)


def test_exactly_the_liftable_refusal_says_it_is_liftable():
    """The composed message, from the real validator.

    The flag above is what a later ticket searches for; this is what a tenant
    reads, and the two are one act — the notice is generated from the flag, so
    a refusal cannot be permanent in the data and temporary in the sentence.
    """
    said = {kind: ReportedCostMapping(source_kind=kind)._source_kind_error()
            for kind in REPORTED_COST_KIND_REFUSALS}

    assert V1_LIMITATION not in said[SOURCE_KIND_CONSTANT]
    assert V1_LIMITATION in said[SOURCE_KIND_DERIVED]


# ---------------------------------------------------------------------------
# Negative controls — every rule above, shown to fail, through the real
# classifiers the walks use.
# ---------------------------------------------------------------------------

class _Schema:
    """A stand-in for a request schema. Not the thing under test — the
    classifiers are, and they are called for real."""


def test_negative_control_a_decimal_amount_on_the_wire_is_flagged():
    hit = classify_wire_amount(_Schema, "provider_cost", Decimal)
    assert hit is not None and hit[0] == RULE_MICROS
    assert "Decimal" in hit[2]


def test_negative_control_a_float_is_flagged_even_where_it_names_no_money():
    """The tidier evasion: a supplier's raw number under a neutral name."""
    hit = classify_wire_amount(_Schema, "reported", Optional[float])
    assert hit is not None and hit[0] == RULE_MICROS


def test_negative_control_a_money_integer_without_the_suffix_is_flagged():
    """An amount whose unit a reader has to guess is an amount somebody will
    guess wrong, and the guess that costs money is 'this is in cents'."""
    hit = classify_wire_amount(_Schema, "provider_cost", Optional[int])
    assert hit is not None and hit[0] == RULE_MICROS
    assert "micros" in hit[2]


def test_negative_control_a_money_string_is_flagged():
    """A decimal as text is still the supplier's raw number, and it is the
    shape a JSON API reaches for when the integer looks too large."""
    hit = classify_wire_amount(_Schema, "cost_micros", Optional[str])
    assert hit is not None and hit[0] == RULE_MICROS


def test_negative_control_an_amount_that_mentions_a_currency_is_still_an_amount():
    """The word that lets a field out is the code, not any field naming one.

    ``total_currency_amount`` is an amount. A blanket exit on the word would
    have waved it through, and the shape it waves through is precisely the
    supplier's own number arriving under a name that reads like a code.
    """
    hit = classify_wire_amount(_Schema, "total_currency_amount", Optional[int])
    assert hit is not None and hit[0] == RULE_MICROS


def test_positive_control_the_currency_code_is_a_string():
    """The control the rule would otherwise be unsatisfiable without: the wire
    carries micros AND a code, and the code is not an amount."""
    assert classify_wire_amount(_Schema, "currency", Optional[str]) is None
    assert classify_wire_amount(_Schema, "provider_cost_micros",
                                Optional[int]) is None


def test_negative_control_a_representation_on_the_wire_is_flagged():
    hit = classify_wire_representation(_Schema, "amount_representation", str)
    assert hit is not None and hit[0] == RULE_REPRESENTATION


def test_positive_control_a_declared_representation_is_not_a_wire_field():
    """The classifier is about the request schema, so the model's own column —
    which is where the representation belongs — must not be what it is
    describing. Stated as a control because the two spellings are identical and
    only the tree they are read from tells them apart."""
    assert classify_wire_representation(_Schema, "currency", str) is None


def _classify_source(source):
    return classify_conversion_reach("apps/metering/rating.py",
                                     ast.parse(source))


def test_negative_control_a_behavioural_import_of_the_conversion_is_flagged():
    hit = _classify_source(
        "from apps.platform.event_types.reported_cost import to_micros\n")
    assert hit is not None and hit[0] == RULE_CONVERSION


def test_negative_control_the_module_imported_whole_is_flagged():
    hit = _classify_source(
        "from apps.platform.event_types import reported_cost\n")
    assert hit is not None and hit[0] == RULE_CONVERSION


def test_negative_control_the_composition_layer_is_watched_too():
    """The addition this rule makes to the set next door, exercised.

    The request arrives at `api/v1`, so it is the first place a raw supplier
    number could be converted on the way in — and it is exactly the module the
    gate it borrows its surfaces from deliberately does not cover.
    """
    hit = classify_conversion_reach(
        "api/v1/metering_endpoints.py",
        ast.parse("from apps.platform.event_types.reported_cost "
                  "import to_micros\n"))
    assert hit is not None and hit[0] == RULE_CONVERSION


def test_negative_control_a_relative_import_is_flagged():
    """``from .reported_cost import to_micros`` names no app and no package,
    and it is what the reach looks like from inside a product's own tree."""
    hit = _classify_source("from .reported_cost import pin_currency\n")
    assert hit is not None and hit[0] == RULE_CONVERSION


def test_negative_control_a_call_with_no_import_in_sight_is_flagged():
    """The indirection that gets past every import check: fetch the module by
    name, then call the function. What is left to recognise it by is the
    function's own name."""
    hit = _classify_source(
        "converter = import_module(NAME)\n"
        "amount = converter.to_micros(raw, representation, currency)\n")
    assert hit is not None and hit[0] == RULE_CONVERSION


def test_positive_control_the_money_primitives_are_not_the_conversion():
    """``core.money`` is behavioural and it is not what this rule is about.
    A check that failed it would have to be weakened until it stopped, which is
    how a gate becomes decorative."""
    assert _classify_source(
        "from core.money import to_minor, MICROS_PER_UNIT\n"
        "minor, carry = to_minor(amount_micros, currency)\n") is None
