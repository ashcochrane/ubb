"""G4 — the published contract's known-value metadata (#208).

The spec starts telling API consumers which values UBB knows about **without
closing a single open enum**. ADR-0003's stance is not reversed and not
softened: an `open` concept keeps `type: string` and exposes its recognised
values as documentation metadata under `x-ubb-known-values`, never as an `enum`
array. #158 §1 measured why the spec cannot be the vocabulary oracle — an
allowed value list in 3 of 165 component schemas — and the same measurement is
why it must not be forced into becoming one, which would turn every new status
into a breaking-gate event.

    G4  no open concept has been silently converted to a closed schema enum;
        recognised values appear as `x-ubb-known-values`, never as `enum`.

**The rule that keeps this honest.** The spec advertises a value only where the
backend already serves it — asked through
:meth:`tools.consumers.Census.serves`, which is #227's predicate consumed
rather than rebuilt. Emitting the final values on a field that still returns
the retired one would put a falsehood into the published contract, and that is
worse than saying nothing because a consumer can act on it. That rule still
withholds most of the registry, and every concept it withholds is an
individually identified migration-ledger entry owed by the slice that renames
it. **That is not a sign the mechanism is wrong**; it is the debt made
countable.

BOTH KINDS NOW REACH THE COMMITTED DOCUMENT. #240 put the first marker of any
kind on it, #267 brought the first `closed` concepts of this slice — real
`enum`s — and #268 brought the first `open` ones, which is the first time the
contract has ever carried an `x-ubb-known-values` block. The accounting across
the two is pinned below, per concept, because a marker moving from one concept
to another leaves every pointer-shaped check untouched.

The gate was built when the marker-driven half had nothing in the committed
document to walk, so this module is deliberately built not to be vacuous:

- the decision document is checked against the registry and the census for all
  42 concepts, both directions;
- **every `enum` in the committed contract is accounted for**, by JSON pointer,
  which is the half that catches a *silent* conversion — a hand-written
  `Literal[...]` on a field for an open concept never comes near a marker, so a
  gate that only walked marked nodes could not see the thing it is named after;
- the committed contract is proved a **fixed point** of the real applier;
- every refusal and every emission is driven through the REAL applier and the
  REAL `decide` over a synthetic tree, including the positive control that
  makes `advertised` reachable at all. Without that last one, everything here
  would be satisfied by a mechanism that can only ever emit nothing.
"""

import ast
import json
from typing import NamedTuple

import pytest

from _helpers import CONSUMER_PATH, REPO_ROOT, concept, write_registry
from tools.consumers import serving_surfaces, take_census
from tools.gates import load_programme
from tools.known_values import (
    BACKEND,
    CONTRACT,
    ENUM,
    EXTENSIONS,
    KNOWN_VALUES,
    KNOWN_VALUES_KEY,
    MARKER,
    NOTHING,
    VALUES_KEY,
    Decision,
    KnownValuesRefused,
    apply_known_values,
    decide,
    marked_nodes,
    read,
    read_decisions,
    strip_known_values,
)
from tools.known_values import errors as codes
from tools.vocabulary import load_registry
from tools.vocabulary.generate import OPENAPI_KNOWN_VALUES

SPEC_PATH = REPO_ROOT / "openapi" / "v1.json"
DOCUMENT_PATH = REPO_ROOT / OPENAPI_KNOWN_VALUES.path
EXPORT_MODULE = REPO_ROOT / "ubb-platform" / "api" / "v1" / "openapi_export.py"

#: THE GATE'S SECOND HALF: every `enum` in the committed contract, by JSON
#: pointer, that this mechanism did **not** put there.
#:
#: An inventory, not a ledger — the same distinction
#: `tests/contracts/test_undeclared_value_sets.py` draws, and for the same
#: reason: a ledger entry names a canonical term and the slice that removes it,
#: and for these three neither exists. Two of them enumerate something the
#: registry describes no concept for at all.
#:
#: It exists because a *silent* conversion is the thing G4 is named after, and a
#: silent one never carries a marker. Somebody typing `Literal["a", "b"]` onto a
#: field for an open concept produces an `enum` in a node this gate would
#: otherwise never look at. Pinning every enum by location means a new one has
#: to come past a reviewer, whose question is the only one that matters here:
#: **is this an open concept?**
#:
#: Checked in both directions, for G7's reason — too few and one has arrived,
#: too many and the inventory is an excuse with no upper bound.
NON_VOCABULARY_ENUMS = {
    "/components/schemas/BudgetConfigIn/properties/enforce_mode":
        "`spend_pool_enforce_mode`, enumerated by hand before the registry "
        "existed. The values already agree with it; the SCHEMA does not hold "
        "them by reference, and the field's own schema is renamed by slice 6 "
        "along with the retired container name around it. Left in place "
        "deliberately: removing a published enum is a contract change, and "
        "#208 emits metadata rather than editing what earlier slices shipped.",
    "/components/schemas/PlanIn/properties/interval":
        "The Stripe billing interval. Not UBB vocabulary at all — Stripe owns "
        "the value set and ADR-0006 does not rename it, so no concept is owed.",
    "/components/schemas/ProgramCreateRequest/properties/reward_type":
        "The referral programme's reward shape. No slice in #194's table "
        "rebuilds referrals and the registry declares no concept for it, so "
        "this is an undeclared value set rather than a debt.",
}

def _decision(concept_name="synthetic_concept", representation=ENUM,
              advertised=True, values=("alpha", "beta"), kind="closed"):
    """One `Decision`, built by hand so a control states exactly the case it is
    about. `decide` itself is exercised against the real tree in section 1 and
    against a synthetic one in section 5, so nothing here is the only account
    of how a decision is reached."""
    return Decision(concept=concept_name, kind=kind,
                    representation=representation, advertised=advertised,
                    backend_serves="2 of 2 values" if advertised else
                    "0 of 2 values",
                    values=tuple(values) if advertised else None)


def _string_property(concept_name, **extra):
    """A schema node shaped the way django-ninja renders a `str` field."""
    return {"type": "string", "title": "Status", MARKER: concept_name, **extra}


def _document(node, concept_name="synthetic_concept"):
    """A minimal OpenAPI document with one marked property, at real depth.

    Nested under `components/schemas`, not passed bare, so a walker that only
    looked at the top level would fail these controls rather than pass them.
    """
    return {"openapi": "3.1.0",
            "components": {"schemas": {"Thing": {"properties": {"status": node}}}},
            "paths": {}}


def _applied(document, decisions):
    return apply_known_values(document, decisions)["components"]["schemas"][
        "Thing"]["properties"]["status"]


def _refusal(document, decisions):
    with pytest.raises(KnownValuesRefused) as raised:
        apply_known_values(document, decisions)
    return raised.value


# ---------------------------------------------------------------------------
# Fixtures — the real registry, the real tree, the committed contract
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry():
    return load_registry(REPO_ROOT / "domain-vocabulary", REPO_ROOT)


@pytest.fixture(scope="module")
def census(registry):
    return take_census(REPO_ROOT, registry)


@pytest.fixture(scope="module")
def programme():
    return load_programme(REPO_ROOT / "gates", REPO_ROOT)


@pytest.fixture(scope="module")
def spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def decisions():
    return read_decisions(DOCUMENT_PATH)


def _enums(document):
    """``{json pointer: enum}`` for every enum anywhere in a document."""
    found = {}

    def walk(node, pointer):
        if isinstance(node, dict):
            if "enum" in node:
                found[pointer] = node["enum"]
            for key, value in node.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                walk(value, f"{pointer}/{escaped}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{pointer}/{index}")

    walk(document, "")
    return found


def _extensions(document):
    """Every `x-ubb-` key the document carries, anywhere."""
    found = set()

    def walk(node):
        if isinstance(node, dict):
            found.update(key for key in node if str(key).startswith("x-ubb-"))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    return found


# ---------------------------------------------------------------------------
# 1. The decision document says what the registry and the census say
# ---------------------------------------------------------------------------

def test_every_concept_has_a_decision(registry, decisions):
    """AC: the metadata is generated from the registry — all of it.

    A concept missing here would be silently unrepresentable in the contract
    forever, and would look identical to one deliberately carrying nothing.
    """
    assert set(decisions) == set(registry.concepts)
    assert len(decisions) >= 30, "the registry has shrunk — suspect the loader"


def test_each_representation_follows_the_concepts_kind(registry, decisions):
    """AC: the representation is generated *according to the concept's kind*.

    This is the property that makes a silent conversion structurally
    impossible rather than merely unlikely: nothing downstream of this reads
    the kind again, so an `open` concept cannot acquire an `enum` by any route
    that does not first change this mapping.
    """
    for name, decision in sorted(decisions.items()):
        declared = registry.concepts[name]
        in_contract = any(c.surface == CONTRACT for c in declared.consumers)
        if not declared.declared_values or not in_contract:
            expected = NOTHING
        elif declared.known_values:
            expected = KNOWN_VALUES
        else:
            expected = ENUM
        assert decision.representation == expected, name
        assert decision.kind == declared.kind, name


def test_a_tenant_defined_concept_contributes_nothing_to_the_spec(registry,
                                                                  decisions):
    """AC, stated in full: a tenant-defined concept contributes nothing.

    Three ways at once, because "contributes nothing" has to be true of the
    document, of the values and of the applier — not merely of the row.
    """
    owned_by_tenants = [c for kind in ("tenant_defined", "free_text")
                        for c in registry.of_kind(kind)]
    assert owned_by_tenants, "no such concept in the registry — nothing proven"

    for declared in owned_by_tenants:
        decision = decisions[declared.name]
        assert decision.representation == NOTHING, declared.name
        assert decision.values is None, declared.name
        assert not decision.advertised, declared.name
        refusal = _refusal(_document(_string_property(declared.name)),
                           decisions)
        assert refusal.code == codes.CONTRIBUTES_NOTHING


def test_a_concept_is_advertised_exactly_where_the_backend_serves_it(
        registry, census, decisions):
    """AC: metadata is emitted only for concepts whose backend consumer already
    serves the registry's values — **through #227's predicate**.

    `census.serves` is called here rather than reimplemented, which is the
    acceptance criterion #227 wrote for this ticket stated as a test. Two
    implementations of one predicate is the shape that already bit #203.
    """
    checked = 0
    for name, decision in sorted(decisions.items()):
        declared = registry.concepts[name]
        if decision.representation == NOTHING:
            assert not decision.advertised, name
            continue
        served = census.serves(name, BACKEND)
        assert decision.advertised is served, name
        checked += 1
    assert checked >= 25, f"only {checked} concepts reach the contract"


def test_every_concept_the_contract_may_carry_has_a_backend_consumer(
        registry, census, decisions):
    """The one place `decide` softens the census's contract, closed by proof.

    `Census.serves` RAISES rather than answering for a concept it has no
    verdict on, and says why: *"#208 must not read 'the backend does not serve
    it' from 'nobody asked'"*. `decide` does not call it in that case — it
    reads `extent() is None` and withholds — which is the safe direction but is
    still a softening.

    So the case is required not to exist. A concept the registry says appears
    in the contract, with values UBB owns and no backend consumer to hold them,
    is an incoherent registry rather than a silent absence of metadata: it
    would say the published document may state a value set nothing in UBB is
    responsible for. If one is ever declared, this fails by name — instead of
    that concept quietly never being advertised, for a reason no gate reports.
    """
    homeless = sorted(
        name for name, decision in decisions.items()
        if decision.representation != NOTHING
        and census.extent(name, BACKEND) is None)
    assert not homeless, (
        f"{len(homeless)} concept(s) may appear in the contract but declare no "
        f"backend consumer: {homeless}. Either give each one the consumer that "
        f"will hold its values, or stop declaring an `openapi` consumer for it "
        f"in domain-vocabulary/.")

    # And the guard is not vacuous: the surface it names is one the census
    # genuinely answers for, so a typo'd surface name would fail here.
    assert BACKEND in serving_surfaces()


def test_no_unadvertised_concept_carries_its_values(decisions):
    """Absent means absent.

    A row that carried the value set anyway would put the final vocabulary in
    every reader's hand with one boolean between it and the published
    contract. The loader refuses such a row outright, so this is the shipped
    document's half of that rule.
    """
    for name, decision in sorted(decisions.items()):
        if decision.advertised:
            assert decision.values, name
        else:
            assert decision.values is None, name


def test_the_recorded_extent_is_exactly_what_the_census_finds(registry, census,
                                                              decisions):
    """`backend_serves` is checked in BOTH directions, for G7's reason.

    Too low and the consumer has regressed; too high and the number is an
    excuse nobody can falsify. It is also what the migration ledger's `found`
    records, so an unadvertised row is a measurable debt rather than a shrug.
    """
    for name, decision in sorted(decisions.items()):
        declared = registry.concepts[name]
        verdicts = [v for v in census.verdicts
                    if v.concept == name and v.surface == BACKEND]
        if not declared.declared_values or not verdicts:
            assert decision.backend_serves is None, name
            continue
        held = set.intersection(*(set(v.held) for v in verdicts))
        assert decision.backend_serves == \
            f"{len(held)} of {len(declared.declared_values)} values", name


def test_the_document_emits_no_string_that_is_not_a_registry_token(registry):
    """The rule `test_generated_vocabulary.py` applies to the three source
    artifacts, in the form a JSON document can carry it.

    That module's version reads every string literal, which here would include
    the structural keys and the banner — so it is scoped to the language
    artifacts and this is the same claim for this one: every string that could
    be mistaken for vocabulary is a registry token, a kind name or one of the
    three representation names. ADR-0008 §4: these artifacts carry tokens,
    never words.
    """
    document = json.loads(OPENAPI_KNOWN_VALUES.render(registry))
    structural = {ENUM, KNOWN_VALUES, NOTHING} | set(registry.schema.kinds)
    tokens = set(registry.concepts) | {
        value for c in registry.concepts.values() for value in c.declared_values}

    for name, row in document["concepts"].items():
        assert name in tokens
        assert row["kind"] in structural
        assert row["representation"] in structural
        for value in row.get(VALUES_KEY, ()):
            assert value in tokens, f"{name} emits {value!r}"


def test_the_concepts_are_emitted_in_a_stable_order(registry):
    """Sorted by name, so moving a concept between domain files is not also a
    diff here — the property `test_generated_vocabulary.py` asserts of the
    three source artifacts through their section rules, which JSON has none
    of."""
    document = json.loads(OPENAPI_KNOWN_VALUES.render(registry))
    names = list(document["concepts"])
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# 2. THE GATE, over the committed contract
# ---------------------------------------------------------------------------

def test_g4_no_open_concept_is_a_closed_enum_in_the_contract(spec, registry,
                                                             decisions):
    """THE GATE. An `open` concept's recognised values are documentation
    metadata and never an `enum` array.

    Walks the concept-to-schema mapping the contract itself carries — every
    node naming a concept — so nothing has to be inferred by comparing
    spellings, which is the literal scan #191 decision 3 rules out.
    """
    for pointer, node in marked_nodes(spec):
        name = node[MARKER]
        assert name in decisions, f"{pointer} names {name!r}, not a concept"
        decision = decisions[name]

        if decision.representation == KNOWN_VALUES:
            assert "enum" not in node, (
                f"{pointer} enumerates the open concept {name!r}. ADR-0003: a "
                f"value UBB has never seen is legal, so an enum here would make "
                f"UBB learning one a breaking change to the published contract")
            assert node.get("type") == "string" or "anyOf" in node or \
                "oneOf" in node, pointer
            assert node.get(KNOWN_VALUES_KEY) == \
                list(registry.concepts[name].known_values), pointer
        else:
            assert decision.representation == ENUM, pointer
            assert KNOWN_VALUES_KEY not in node, (
                f"{pointer}: {name!r} is closed, so its values are the schema's "
                f"`enum` and not documentation beside it")
            assert node.get("enum") == list(registry.concepts[name].values), \
                pointer


def test_g4_every_enum_in_the_contract_is_accounted_for(spec, decisions):
    """THE GATE'S OTHER HALF — the one that can see a *silent* conversion.

    A hand-written `Literal[...]` produces an `enum` on a node carrying no
    marker, so the walk above would never reach it. Every enum in the committed
    document is therefore pinned by JSON pointer: either it is a marked closed
    concept's, generated from the registry, or it is declared above with a
    reason.

    Both directions. A new enum fails because it is unaccounted; a stale line
    fails because an inventory that may overstate has no upper bound and would
    quietly licence whatever moved into its place.
    """
    generated = {pointer for pointer, node in marked_nodes(spec)
                 if decisions[node[MARKER]].representation == ENUM}
    found = set(_enums(spec)) - generated

    assert found == set(NON_VOCABULARY_ENUMS), (
        "the contract's enums have changed. A NEW one is either an open "
        "concept being silently closed — which G4 exists to refuse — or a "
        "value set nobody has declared the kind of (#191 story 15). Give it a "
        "registry concept and a marker, or add its pointer above with a "
        "reason.\n"
        f"  unaccounted: {sorted(found - set(NON_VOCABULARY_ENUMS))}\n"
        f"  gone:        {sorted(set(NON_VOCABULARY_ENUMS) - found)}")


def test_every_declared_enum_carries_a_real_reason():
    """An inventory entry with no reason is an excuse, and the cheapest way for
    an over-broad one to arrive is with nothing written beside it (#154 §14)."""
    for pointer, reason in NON_VOCABULARY_ENUMS.items():
        assert pointer.startswith("/components/schemas/"), pointer
        assert len(reason.split()) >= 12, f"{pointer} carries no real reason"


def test_every_marked_node_names_a_concept_the_contract_may_advertise(
        spec, decisions):
    """A marker is present exactly where metadata is, never as a bare label.

    The applier refuses to render one otherwise, so this is that refusal
    checked against the committed bytes rather than trusted — a marker that
    survived without its values would be a concept named in the published
    contract while the backend still serves the retired vocabulary.
    """
    for pointer, node in marked_nodes(spec):
        decision = decisions[node[MARKER]]
        assert decision.advertised, pointer
        assert decision.representation != NOTHING, pointer


def test_every_advertised_concept_reaches_the_contract(spec, decisions):
    """The other direction, and it is what makes a slice's work whole.

    A concept the registry gives an `openapi` consumer, whose backend consumer
    now serves it, must actually appear in the document. Converting the model
    and forgetting the schema field would otherwise leave the contract silent
    with every gate green.
    """
    marked = {node[MARKER] for _, node in marked_nodes(spec)}
    missing = sorted(name for name, decision in decisions.items()
                     if decision.advertised and name not in marked)
    assert not missing, (
        f"{len(missing)} concept(s) are served by the backend and declare an "
        f"openapi consumer, but no schema field names them: {missing}. Mark "
        f"the field with `{MARKER}` and regenerate the spec.")


def test_a_closed_concepts_marker_never_sits_on_a_nullable_union(spec,
                                                                  decisions):
    """A `closed` concept's `enum` must not be able to refuse `null` (#323).

    JSON Schema reads keywords at one node CONJUNCTIVELY. So a node shaped

        {"anyOf": [{"type": "string"}, {"type": "null"}], "enum": [...]}

    admits `null` under `anyOf` and then refuses it under `enum` — the field is
    nullable in every reader's eyes and unusable in a validator's. The honest
    shape puts the marker in the STRING MEMBER, where the generated `enum`
    constrains the strings and leaves the null member alone, which is what
    django-ninja renders for `Optional[SomeMarkedAlias]`.

    NOTHING ELSE IN THE REPOSITORY WOULD CATCH THE WRONG ONE. The wire body is
    unchanged, so no endpoint test sees it; the export is clean, because
    `apply.py` asks only whether the node is string-SHAPED
    (:func:`_is_string_shaped` accepts a union with a string member) and not
    whether writing an `enum` there would be true; and oasdiff reads an added
    property either way. It is a document that contradicts the server with a
    green board — ADR-0008 §9's failure mode landing on the contract itself.

    ASSERTED OVER EVERY ADVERTISED CONCEPT, not over the fields that prompted
    it. Three hard-coded field names would have expired the moment the next
    nullable closed column shipped, and slice 4 adds several. The `open` kind
    is deliberately out of scope: it writes `x-ubb-known-values`, which is
    documentation metadata and constrains nothing, so a union node is a
    perfectly honest home for it — which is exactly why the applier's own
    nullable test covers that kind and could not have covered this one.
    """
    offenders, examined = [], 0
    for pointer, node in marked_nodes(spec):
        if decisions[node[MARKER]].representation != ENUM:
            continue
        examined += 1
        if node.get("type") != "string":
            offenders.append(f"{pointer} ({node[MARKER]})")

    # The vacuity guard this check needs and the ones above do not: it is a
    # "for each" over a filtered walk, so a filter that matched nothing would
    # pass it silently. A count rather than a floor, because the floor is
    # already `CONCEPTS_IN_THE_CONTRACT`'s job and two copies would drift.
    assert examined, ("no advertised closed concept was examined — the walk "
                      "or the representation filter is broken, not the spec")

    assert not offenders, (
        "a closed concept's marker sits on a union rather than on its string "
        "member, so the generated `enum` refuses the `null` the union admits:"
        "\n" + "\n".join(f"  {o}" for o in offenders))


def test_the_contract_carries_no_vendor_extension_this_export_did_not_write(
        spec):
    """A hand-written `x-ubb-` key must not pass itself off as generated.

    The document is generator-owned (openapi/README.md), so an extension in
    this namespace that no target emits is either a hand edit the drift gate
    somehow admitted or a second mechanism nobody declared.
    """
    assert _extensions(spec) <= set(EXTENSIONS), (
        f"unexpected UBB vendor extensions: "
        f"{sorted(_extensions(spec) - set(EXTENSIONS))}")


def test_the_committed_contract_is_a_fixed_point_of_the_applier(spec,
                                                                decisions):
    """Re-deriving the metadata from the committed contract reproduces it.

    The strongest single statement available here: whatever the contract says
    about UBB's vocabulary is exactly what the registry and the census produce,
    checked without regenerating the spec — which needs Django, a settings
    module and the whole composed API, none of which this suite has.

    Stripped first, because the applier is deliberately not idempotent: from
    inside a node there is nothing to distinguish a generated `enum` from a
    hand-written one, so applying twice hits the refusal that exists to catch
    the second. Stripping is the inverse, and it is scoped to marked nodes — so
    a hand-written enum anywhere else, which is where a *silent* conversion
    would sit, is untouched and still accounted for above.
    """
    assert apply_known_values(strip_known_values(spec), decisions) == spec


def test_applying_twice_is_refused_rather_than_doubled(spec, decisions):
    """The other half of the fixed point, and the reason regeneration STRIPS.

    The check above proves strip-then-apply reproduces the committed bytes. It
    cannot, on its own, tell that apart from an applier that is merely
    idempotent — and the difference is the whole design. From inside a node
    there is nothing to distinguish a generated `enum` from a hand-written
    `Literal[...]`, so an applier that quietly re-applied would have to treat
    the second as the first, and the refusal that catches a silent conversion
    would be the refusal it had just given up.

    So this asserts the refusal against the REAL committed contract rather than
    a synthetic node: applying to the already-applied document raises, naming a
    real field's JSON pointer. `test_negative_control_a_hand_written_enum_under
    _a_marker_is_refused` states the same rule over a fixture; this states it
    over the bytes that ship, which is where "regeneration strips before it
    applies" is a claim about the export rather than about a unit.
    """
    with pytest.raises(KnownValuesRefused) as raised:
        apply_known_values(spec, decisions)

    assert raised.value.code == codes.ALREADY_ENUMERATED
    assert raised.value.location.startswith("/components/schemas/")


def test_applying_twice_to_an_open_node_is_refused_as_an_annotation(spec,
                                                                     decisions):
    """The same proof for the OPEN kind, and it needs its own test.

    The check above walks the whole document and stops at the FIRST already-
    applied node it meets, which is a closed concept's `enum` — so it proves
    the closed path and says nothing about this one. The two refusals are
    different code paths guarding different keys (`already-enumerated` on
    `enum`, `already-annotated` on `x-ubb-known-values`), and #268 is the first
    commit where the second has real bytes to guard at all.

    So each shipped known-value node is re-applied ON ITS OWN — the real node
    lifted out of the committed contract, not a fixture shaped like one — and
    must be refused. Without this, "a second run is proved not to double-apply"
    would be a claim about the kind that was already covered, made in the
    commit that introduced the kind that was not.
    """
    checked = 0
    for pointer, node in marked_nodes(spec):
        if decisions[node[MARKER]].representation != KNOWN_VALUES:
            continue
        checked += 1
        refusal = _refusal(_document(node), decisions)
        assert refusal.code == codes.ALREADY_ANNOTATED, pointer

    assert checked == sum(published.nodes for published
                          in CONCEPTS_IN_THE_CONTRACT.values()
                          if published.kind == KNOWN_VALUES)


#: THE ACCOUNTING AT THIS COMMIT — per concept, how many nodes name it and the
#: KIND it is published under. Checked in both directions.
#:
#: `test_g4_every_enum_in_the_contract_is_accounted_for` above pins every enum
#: by POINTER, which answers "did an unaccounted enum arrive". It cannot answer
#: the question this map is about, because a marker moving from one concept to
#: another leaves the pointer set untouched: what reaches the contract, and
#: under which kind. Nor can a pointer inventory see the OPEN half at all — a
#: known-value block puts no `enum` anywhere.
#:
#: The kind is written here rather than derived, so this map states a position
#: instead of restating whatever the registry currently says. A concept
#: changing kind is exactly the event ADR-0003 is about: `closed` becoming
#: `open` widens what the wire admits and `open` becoming `closed` is the
#: silent conversion G4 is named after. Either one moves a line here, in the
#: commit that does it.
class Published(NamedTuple):
    """One concept's row in the map below.

    Named rather than a bare pair because the two halves fail differently and
    a reader of `(3, ENUM)` has to count commas to tell which is which.
    """
    #: How many schema nodes name this concept.
    nodes: int
    #: What those nodes render — `ENUM` or `KNOWN_VALUES`.
    kind: str


CONCEPTS_IN_THE_CONTRACT = {
    # #240 (slice 1) — the first marker of any kind.
    "tenant_product": Published(2, ENUM),         # TenantOut, and the update
    # #267 — the catalogue's three closed sets.
    "costing_method": Published(3, ENUM),         # EventTypeIn/Out + the update
    "source_kind": Published(4, ENUM),            # quantity + cost, in and out
    "amount_representation": Published(2, ENUM),  # the reported cost, in+out
    # #268 — THE FIRST OPEN CONCEPTS THE CONTRACT HAS EVER CARRIED. Both render
    # `x-ubb-known-values` beside an untouched `type: string`: the values are
    # what UBB has met, never what it will accept, so UBB meeting a new one is
    # not a change to this document at all.
    "unit": Published(2, KNOWN_VALUES),           # MeasurementIn/Out
    "source_shape_id": Published(3, KNOWN_VALUES),  # EventTypeIn/Out + update
    # #271 — the first DERIVED fact the contract advertises. Its backend
    # consumer is a serialiser rather than a model, which is the whole ruling:
    # no column holds it, G10 proves so, and the census measures the module
    # that computes it exactly as it measures any other consumer.
    "measurements_status": Published(1, ENUM),    # UsageEventDetailOut
    # #317 (slice 3) — the first concept whose marker was FORCED rather than
    # scheduled. Its `openapi` consumer was declared long before the field, and
    # `g4-openapi-costing_status` excused the gap while the backend served none
    # of the values; the commit that made `usage/models.py` hold all three by
    # reference closed it, because `advertised` is derived from the backend
    # census alone and a concept advertised with no field naming it is what
    # `test_every_advertised_concept_reaches_the_contract` refuses. Three
    # nodes: every response that publishes a supplier cost says whether that
    # cost is settled, so nobody reads a zero UBB has not learned yet as money.
    #
    # #328 (slice 3) — A FOURTH NODE, AND THE FIRST MARKER OUTSIDE A RESPONSE.
    # `usage.recorded` carries the amount too, and until this commit it carried
    # it with no status: a subscriber read the same null for "no supplier cost"
    # and "one UBB has not learned", which is the ambiguity the other three
    # nodes exist to remove. Two products now count exclusions off this payload,
    # so the field is not decoration. It is marked rather than left a bare
    # `type: string` because the applier walks the `webhooks` section like any
    # other, and an unmarked node would have published a closed concept as an
    # open one — the shape this map exists to make countable.
    #
    # #364 (slice 4) — A FIFTH NODE, ON THE QUEUE OF EVERYTHING UNRESOLVED. The
    # rule is unchanged and mechanical: that row publishes a supplier cost, so
    # it publishes the status qualifying it. What is different is how loudly it
    # matters — every row in that list is there BECAUSE something is
    # unresolved, so a list that published the amount without the status would
    # be a page of blanks with nothing saying which of them are missing and
    # which do not exist.
    "costing_status": Published(5, ENUM),  # + the unresolved queue's row
    # #323 (slice 3) — the other half of the sentence above, and the first
    # nullable marker on a RESPONSE. Nullable markers are not new:
    # `EventTypeUpdateIn` has carried two since #262, and they are the
    # precedent this followed. What is new is that a server actually RETURNS
    # the null — on a request field, `null` means "leave this alone" and no
    # response body ever contains it, so a document that refused it would
    # inconvenience a caller rather than contradict the server. Here `null` is
    # the answer on every settled posting, which is nearly all of them.
    #
    # So the marker travels into the string member of the union rather than
    # sitting on the union itself: `enum` and `anyOf` at ONE node are
    # conjunctive, and the wrong placement publishes a document that refuses
    # the response the server returns a few thousand times an hour.
    # `test_a_closed_concepts_marker_never_sits_on_a_nullable_union` below
    # holds every advertised concept to it, this one included.
    #
    # Three nodes, for the same reason the status has three — a cause that does
    # not travel with the status it explains leaves the reader a shrug.
    #
    # #364 — a FOURTH node, and the one where the cause is the point rather
    # than the companion. The unresolved queue exists so a tenant can find out
    # what they have misconfigured, and the recorded cause is the whole of that
    # answer: `cost_rate_missing` says write a rate, `reported_cost_missing`
    # says you are waiting on a supplier.
    "unresolved_reason": Published(4, ENUM),  # + the unresolved queue's row
    # #351 (slice 4) — the price half of both entries above, and the same four
    # nodes for the same reasons. The customer price column went nullable with
    # a status beside it, so every response that publishes a price says whether
    # that price is settled, and the `usage.recorded` payload carries it too
    # because both products accumulating off that payload need to tell a price
    # UBB could not resolve from one that was waived or never applied.
    #
    # ⚠ THE PAYLOAD NODE IS THE ONE THIS SLICE WAS WARNED ABOUT BY NAME: a
    # closed concept can reach the wire UNMARKED with the marker gate green,
    # because a node that is not marked is not counted and the count is all the
    # gate sees. Only this map — which says WHERE each marker sits — can catch
    # it, and `apply.py` walks the `webhooks` section like any other.
    #
    # #364 — a FIFTH node, the price half of the queue row's argument: a
    # posting whose price UBB could not resolve is the other half of that list,
    # and `unknown` is what says so.
    "pricing_status": Published(5, ENUM),  # + the unresolved queue's row
    # #351 — the second nullable marker on a response, following exactly the
    # placement `unresolved_reason` above established: in the STRING MEMBER of
    # the union, never on the union node, because `enum` and `anyOf` at one node
    # are conjunctive and `null` is the answer on every priced posting.
    #
    # Three nodes rather than four: the reason does NOT ride the outbox payload.
    # That payload's two readers are accumulators counting how many prices they
    # could not include; neither asks which of the two causes produced a
    # `not_applicable`, and a field nothing reads is a field that goes stale.
    # The same ruling #328 made for `unresolved_reason` on the same payload.
    "not_applicable_reason": Published(3, ENUM),  # record + list row + detail
    # #355 (slice 4) — HOW a price was derived, beside the status that says
    # WHETHER it is settled. The third nullable marker on a response, in the
    # string member for the reason the two above give.
    #
    # TWO NODES, AND THE RULE IS A DIFFERENT ONE FROM THE FOUR ABOVE rather
    # than a smaller version of it. Those qualify an AMOUNT, so they belong on
    # every response publishing one. This one goes WHEREVER THE RECEIPT GOES,
    # and that is mechanical rather than a judgement: the method is a value
    # inside the record, which is published untyped, so on every response
    # carrying that record the method is already on the wire with no schema
    # saying what it may be. Exactly two responses carry it — the recording ack
    # and the audit lookup — and leaving either out would leave the same closed
    # concept unadvertised there.
    #
    # ⚠ NOT ON THE `usage.recorded` PAYLOAD, AND THAT WAS CHECKED RATHER THAN
    # ASSUMED — the trap this slice was warned about by name is a closed concept
    # reaching the wire unmarked, which no count can see. That payload carries
    # no receipt and no method on either side; its two readers are accumulators
    # asking whether an amount may be included, and neither asks how it was
    # derived. The same ruling #328 and #351 made for the two reasons.
    # 2 -> 6 in #361, and all four new nodes are there because the method
    # became something a tenant STATES rather than only something UBB reports.
    # TWO of them are request bodies — the change a publish carries and the one
    # that declares an override — and a closed concept a caller may SEND is
    # exactly the one that has to be advertised. The other two are the reads
    # that shadow them: the diff row a tenant checks before committing, and the
    # inherited rule a client copies a starting point from.
    "pricing_method": Published(6, ENUM),
    # WHICH ARITHMETIC A RULE RUNS (#366) — seven nodes, which is every schema
    # that carries a rule in either direction rather than a subset of them.
    # Three are the immediate rate routes: the body that opens a rule, the body
    # that reprices one, the row that reads one back. Two are the publish act
    # that replaces those three — the change it carries and the terms row a diff
    # shows before and after. Two are the customer override — the body that
    # declares one, and the inherited rule a client copies into it.
    #
    # ⚠ IT REACHED THE CONTRACT ONE SLICE LATE AND THE REASON WAS MECHANICAL.
    # #358 wanted the shape on a change body and could not have it: the column's
    # name was retired, so coining that spelling on a new schema would have
    # broken its ledger ceiling, and coining the canonical spelling would have
    # published a field whose VALUES were still the retired ones. The rename
    # cleared both at once, which is why the column, its values and all seven
    # nodes land in one commit.
    #
    # ⚠ AND THE LAST TWO WERE FOUND BY A TEST. An existing case holds the
    # override body's field set EQUAL to a change body's, minus the act, plus
    # the instant — so a concept added to one and not the other is red rather
    # than merely inconsistent. That is what an equality buys over a
    # per-property check, and it is why "a rule states a whole rule" is
    # asserted as a SET.
    "rate_structure": Published(7, ENUM),
}


def test_the_contract_advertises_exactly_these_concepts_under_these_kinds(
        spec, registry, decisions):
    """AC: the accounting across BOTH kinds, and the totals match the registry.

    Both directions, for the reason the pointer inventory gives: too few and a
    marker has been dropped or a concept has stopped being advertised; too many
    and a concept reached the published contract without anyone signing for it.

    The kind travels with the count because they fail differently. A dropped
    marker is a concept going quiet; a concept switching kind is the same
    markers rendering something else entirely — an `enum` where documentation
    metadata belongs, which is the conversion ADR-0003 forbids and which no
    count would notice.
    """
    marked = {}
    for _, node in marked_nodes(spec):
        marked[node[MARKER]] = marked.get(node[MARKER], 0) + 1

    expected = {name: published.nodes for name, published
                in CONCEPTS_IN_THE_CONTRACT.items()}
    assert marked == expected, (
        "the set of concepts the contract advertises has changed. Adding one "
        "is a deliberate act — the registry gains an `openapi` consumer and a "
        "schema field gains a marker in the same commit — so update the map "
        "above in that commit and say which ticket did it.")

    for name, published in CONCEPTS_IN_THE_CONTRACT.items():
        assert decisions[name].representation == published.kind, name
        assert registry.concepts[name].kind == (
            "closed" if published.kind == ENUM else "open"), name


def test_the_accounting_is_exactly_what_the_registry_declares(
        registry, decisions):
    """The same totals, read off the REGISTRY rather than off the document.

    The map above is a statement about the DOCUMENT — what a walk of the
    committed bytes finds. This reaches the same set from the other end, and
    the two are independent: a concept can declare a contract consumer and
    still reach no schema field, which is the half-done state
    `test_every_advertised_concept_reaches_the_contract` exists for.

    The registry's `openapi` consumers are the concepts that will EVENTUALLY be
    published; the advertised ones are those whose backend already serves them,
    which is the only set the contract may carry today. **The remainder — a
    concept that would contribute something and does not yet — is a G4 debt,
    and section 6 already pins the ledger against it in both directions.** It
    is deliberately not restated here: a third copy of that claim would either
    duplicate those two tests or, if it read `owed` back out of the same
    decisions, assert nothing at all.
    """
    declaring = {name for name, c in registry.concepts.items()
                 if any(consumer.surface == CONTRACT
                        for consumer in c.consumers)}
    advertised = {name for name, decision in decisions.items()
                  if decision.advertised}
    mapped = set(CONCEPTS_IN_THE_CONTRACT)

    assert mapped == advertised, (
        f"the map above and the decision document disagree about what the "
        f"contract advertises.\n"
        f"  advertised but unmapped: {sorted(advertised - mapped)}\n"
        f"  mapped but unadvertised: {sorted(mapped - advertised)}")

    assert mapped <= declaring, (
        f"a concept reaches the contract without the registry declaring an "
        f"`openapi` consumer for it: {sorted(mapped - declaring)}")

    kinds = {published.kind for published in CONCEPTS_IN_THE_CONTRACT.values()}
    assert kinds == {ENUM, KNOWN_VALUES}, (
        "the contract has stopped carrying one of the two kinds. Both halves "
        "of ADR-0003's stance are meant to be live here — an enum for a set "
        "UBB owns, documentation metadata for one it does not — and a gate "
        "with only one kind in front of it proves half of what it claims")

    for name in CONCEPTS_IN_THE_CONTRACT:
        assert decisions[name].advertised, name
        assert decisions[name].values == \
            tuple(registry.concepts[name].declared_values), name


def test_each_concept_is_advertised_on_the_schemas_that_carry_it(spec):
    """The concepts are on the catalogue's own schemas, not merely somewhere.

    A marker is only worth having where a value actually travels, and a count
    alone would be satisfied by six markers on one unrelated schema. This names
    the schemas, because the agreement being asserted is between a tenant's
    declaration and the vocabulary UBB serves it under.

    ⚠ **AND IT HAS TO NAME EVERY ONE OF THEM.** Three concepts reached the
    contract with a count and no placement — the tenant's product set from #240
    and the price pair from #351 — because nothing here required a line per
    concept. A placement test that quietly skips a concept has the same defect
    as the count it exists to strengthen, one level down. The check at the foot
    is what makes the omission impossible, and the names it compares are
    collected by :func:`placed` rather than restated in a list beside it, which
    would be one more copy able to drift.
    """
    where = {}
    for pointer, node in marked_nodes(spec):
        parts = pointer.split("/")
        # A marker sits on a component schema (`/components/schemas/<Name>/…`)
        # or, since #328, inside the `webhooks` section
        # (`/webhooks/<event type>/post/…`) — the applier walks the whole
        # document and does not care which. Each is named the way a reader of
        # the contract would name it, so the assertions below stay readable
        # rather than carrying a pointer fragment.
        where.setdefault(node[MARKER], set()).add(
            parts[2] if parts[1] == "webhooks" else parts[3])

    stated = set()

    def placed(concept, schemas):
        """One concept's placement, asserted and counted as stated."""
        stated.add(concept)
        assert where.get(concept) == schemas, concept

    placed("costing_method", {"EventTypeIn", "EventTypeOut",
                              "EventTypeUpdateIn"})
    placed("source_kind", {"MeasurementIn", "MeasurementOut",
                           "ReportedCostMappingIn", "ReportedCostMappingOut"})
    placed("amount_representation", {"ReportedCostMappingIn",
                                     "ReportedCostMappingOut"})
    # The unit sits on the declared quantity, in and out. It does NOT sit on
    # the reported cost mapping: that carries money with a currency, and
    # `amount_representation` above is its equivalent noun.
    placed("unit", {"MeasurementIn", "MeasurementOut"})
    # The response shape is declared ONCE at the Event Type, which is the whole
    # of #193 §C7's ruling — two quantities beneath it can never disagree about
    # which client they are mapped to. A marker on `MeasurementIn` would say
    # the opposite on the published contract.
    placed("source_shape_id", {"EventTypeIn", "EventTypeOut",
                               "EventTypeUpdateIn"})
    # OUT ONLY, and that is the ruling rather than an omission: the status is
    # derived and served, so a request schema naming it would be inviting a
    # caller to state a fact UBB computes — the second encoding ADR-0006 §4
    # refuses, arriving through the wire instead of through a column.
    placed("measurements_status", {"UsageEventDetailOut"})
    # OUT ONLY as well, and for a DIFFERENT reason worth keeping apart from the
    # one above: this status IS stored, so the objection is not that a caller
    # would state a computed fact — it is that a caller does not know it. What
    # a supplier charged is UBB's to resolve, and a request schema naming it
    # would invite the guess that `claimed_provider_cost_micros` exists to keep
    # out of COGS.
    #
    # FOUR CARRIERS BECAUSE FOUR SURFACES PUBLISH THE AMOUNT IT QUALIFIES,
    # which is the whole rule for where this marker belongs: the ack, the list
    # row, the detail receipt and — since #328 — the `usage.recorded` payload
    # each carry a supplier cost, and a cost published without its status hands
    # a reader back the ambiguity the column stopped having. A fifth surface
    # carrying the amount and not this would be the finding, and that is what
    # makes this line worth more than the count in `CONCEPTS_IN_THE_CONTRACT` —
    # a count is satisfied by four markers anywhere at all.
    #
    # The payload is the first marker outside a response, and it earns the
    # marker on exactly the stated rule rather than by extension: two products
    # count their exclusions off that field, so a subscriber switching on it
    # needs the set the document now states.
    #
    # ⚠ FIVE SINCE #364, AND THE FIFTH IS THE RULE WORKING RATHER THAN AN
    # EXCEPTION TO IT. The unresolved queue's row publishes a supplier cost, so
    # by the stated rule it publishes this status too — and on that surface the
    # status is not decoration but the reason the row is in the list at all. A
    # queue of unresolved amounts that did not say which of them were
    # unresolved would be the one place the ambiguity really bites.
    placed("costing_status", {"RecordUsageResponse", "UsageEventOut",
                              "UsageEventDetailOut", "UnresolvedQueueRow",
                              "usage.recorded"})
    # THE SAME THREE RESPONSES, AND THAT IS THE CLAIM RATHER THAN A COINCIDENCE.
    # The cause is unreadable without the status and the status is unactionable
    # without the cause, so over RESPONSES the two sets are equal by design — a
    # response carrying one and not the other is the finding, in either
    # direction. Written out rather than compared to the line above, because
    # asserting `where["unresolved_reason"] == where["costing_status"]` would go
    # on passing if both concepts vanished from the contract together.
    #
    # ⚠ THE PAYLOAD IS DELIBERATELY OUTSIDE THAT EQUALITY (#328), which is why
    # the two lines are no longer the same set. A response is read by a tenant
    # looking at ONE event, who needs to know which input would settle it; the
    # payload's readers are accumulators counting HOW MANY costs they could not
    # include, and not one of them asks why. A cause carried there would be a
    # field nothing reads, which is how a field goes stale and starts lying.
    #
    # ⚠ AND THE QUEUE ROW KEEPS THE EQUALITY OVER RESPONSES (#364). It carries
    # the cause because the cause is what the queue is FOR: a tenant working
    # through a list of unresolved costs is looking for what to configure, and
    # a column of `unresolved` with no reason is a column of shrugs. A queue
    # publishing the status and not the cause would be the finding.
    placed("unresolved_reason", {"RecordUsageResponse", "UsageEventOut",
                                 "UsageEventDetailOut", "UnresolvedQueueRow"})
    # THE PRICE HALF OF BOTH SETS ABOVE, on the same rule and the same
    # asymmetry: the status rides the payload because two products accumulate
    # off it and need to tell a price UBB could not resolve from one that was
    # waived; the cause does not, because neither reader asks which of the two
    # causes produced a `not_applicable`.
    #
    # ⚠ THESE TWO WERE COUNTED FROM #351 AND PLACED BY NOTHING UNTIL #355. The
    # count is satisfied by four markers anywhere at all, which is the whole
    # reason this test exists beside it, and the module the count lives in says
    # so in its own words. Adding a third marker to the same family while its
    # two siblings had no placement would have left the hole exactly where the
    # slice was warned to look.
    # ⚠ FIVE SINCE #364, the price half of the queue row's own argument: the
    # row publishes a customer price, and `unknown` is the other reason a
    # posting is in that list.
    placed("pricing_status", {"RecordUsageResponse", "UsageEventOut",
                              "UsageEventDetailOut", "UnresolvedQueueRow",
                              "usage.recorded"})
    placed("not_applicable_reason", {"RecordUsageResponse", "UsageEventOut",
                                     "UsageEventDetailOut"})
    # HOW a price was derived, beside the status saying WHETHER it is settled
    # (#355). The rule is "wherever the receipt goes", and it is asserted here
    # as the schemas rather than as a count precisely because those are the two
    # this claim is about: the recording ack and the audit lookup are exactly
    # the responses publishing the record the method lives inside. A third
    # response gaining that record and not this marker is the finding.
    # ⚠ SIX SINCE #361, AND FOUR OF THEM ARE REQUESTS. The rule was "wherever
    # the receipt goes" while the method was only ever reported; a customer
    # override made it something a tenant STATES, so the set is now every
    # schema that carries the method in either direction — the two responses
    # publishing the receipt, the two bodies that state a rule, the diff row
    # that shows one changing, and the inherited rule a client copies from.
    placed("pricing_method", {"RecordUsageResponse", "UsageEventDetailOut",
                              "BookChangeIn", "CustomerOverrideIn",
                              "RuleTermsOut", "InheritedPricingRule"})
    # The rate's arithmetic shape (#366), on every schema carrying a rule in
    # either direction. The three `Rate*` schemas are the immediate routes;
    # `BookChangeIn` and `RuleTermsOut` are the publish act that replaces them;
    # `CustomerOverrideIn` and `InheritedPricingRule` are the override that
    # states a whole rule and the row a client copies into it. None of the last
    # four could carry it until the column was renamed.
    placed("rate_structure", {"RateIn", "RateOut", "RateChangeIn",
                              "BookChangeIn", "RuleTermsOut",
                              "CustomerOverrideIn", "InheritedPricingRule"})
    # The first marker of any kind (#240), and the tenant's own product set is
    # written where a tenant reads and where a tenant writes.
    placed("tenant_product", {"TenantConfigIn", "TenantConfigOut"})

    # ⚠ AND THE REASON THE THREE LINES ABOVE COULD GO MISSING FOR TWO SLICES:
    # nothing held this test to naming every concept, so a marker whose
    # placement nobody stated still passed here — the count map beside it says
    # in its own words that a count is satisfied by markers anywhere at all, and
    # a placement test that skips a concept has exactly the same defect one
    # level down. Checked in both directions, so a concept leaving the contract
    # takes its line with it rather than leaving a stale one behind.
    assert stated == set(where), (
        "a concept the contract advertises has no placement stated above. A "
        "count says a marker exists; only a placement says it is on the schema "
        "whose values it describes — add the line in the commit that adds the "
        "marker, and delete it in the commit that removes one.")


def _marker_on(node):
    """The concept a property node names, wherever the marker legally sits.

    Two places, and both are correct: on the node, or — where the field is
    nullable — inside the string member of its union, which is the placement
    `test_a_closed_concepts_marker_never_sits_on_a_nullable_union` requires.
    A reader that looked only at the node would read every nullable marked
    field as unmarked.
    """
    if not isinstance(node, dict):
        return None
    if MARKER in node:
        return node[MARKER]
    for member in node.get("anyOf") or []:
        if isinstance(member, dict) and MARKER in member:
            return member[MARKER]
    return None


def _properties(document):
    """Every (pointer, name, node) property in the document, at any depth.

    From the ROOT, because `tools/known_values/apply.py` walks from the root
    too: the `webhooks` section is part of the contract, and a check that
    started at `components.schemas` would be blind to exactly the half this is
    about.
    """
    def walk(node, pointer):
        if isinstance(node, dict):
            for name, child in (node.get("properties") or {}).items():
                yield f"{pointer}/properties/{name}", name, child
            for key, child in node.items():
                yield from walk(child, f"{pointer}/{key}")
        elif isinstance(node, list):
            for index, child in enumerate(node):
                yield from walk(child, f"{pointer}/{index}")

    return walk(document, "")


def test_no_advertised_concept_reaches_the_contract_unmarked(spec, decisions):
    """⚠ **THE TRAP NO COUNT CAN SEE, AND THE WEBHOOK SECTION IS WHERE IT BITES.**

    `test_the_contract_advertises_exactly_these_concepts_under_these_kinds`
    counts MARKED nodes, and an unmarked node is not one — so a closed concept
    can reach the wire as a bare `type: string`, correct in every value it ever
    carries and advertised nowhere, with the whole board green. The placement
    test above says where each marker IS; nothing until now said where one is
    MISSING.

    The rule this asserts is the narrowest one that is actually true: **a
    property whose name IS an advertised concept carries that concept's
    marker.** Both halves of the restriction are load-bearing.

    - Advertised only. A concept the backend does not yet serve *must* stay
      unmarked — `openapi/README.md` is explicit that marking one fails the
      export — and a concept the registry gives no `openapi` consumer may not
      be marked at all. `EventTypeOut.declaration_status` is the live example
      of the second: a `closed` concept, correctly bare, and a rule keyed on
      kind alone would demand a marker the applier refuses.
    - By name only. A field carrying a concept under a different name is real
      (`TenantConfigOut.products` carries `tenant_product`) and cannot be found
      mechanically, so this makes the easy half of the claim rather than
      pretending to make both. What it buys is that the easy half stops being
      free: the natural spelling of a new field IS the concept's name, which is
      how `pricing_method` arrived in #355 and how the next one will.

    ⚠ **AND HERE IS WHAT IT CANNOT SEE, SAID PLAINLY.** It walks `properties`,
    so it is blind inside an `additionalProperties: true` payload — which has
    no properties to walk and is exactly where this repository's live instance
    of the trap lives: the Pricing Receipt publishes four closed concepts
    inside an untyped record on two responses. That is #349's recorded
    residual, and it is not fixable by a check — marking needs a TYPED node, so
    the fix is typing the payload. #355 answered it for its own concept by
    lifting the value into a typed field on both responses carrying the record,
    which is the pattern the rest will follow. This test holds the typed
    surface; nothing holds the untyped one, and pretending otherwise would be a
    green board over the half that is still open.
    """
    unmarked = [pointer for pointer, name, node in _properties(spec)
                if name in decisions and decisions[name].advertised
                and _marker_on(node) != name]

    assert not unmarked, (
        f"{len(unmarked)} propert(ies) are named for a concept the contract "
        f"advertises and carry no marker for it, so the document publishes an "
        f"agreed value set as an open string:\n"
        + "\n".join(f"  {pointer}" for pointer in unmarked))


#: JSON Schema keywords that would bound WHICH strings a field admits. Length is
#: not among them on purpose: `maxLength` bounds how long a value may be, which
#: the column behind it already does, and says nothing about which spellings UBB
#: recognises. `format` is absent for the same reason — it annotates, and the
#: values here are not of any registered format anyway.
VALUE_BOUNDING_KEYWORDS = ("enum", "const", "pattern")


def test_an_unknown_value_stays_legal_on_the_wire(spec, registry, decisions):
    """**The property the open kind exists for**, read off the shipped bytes.

    ADR-0003: a value UBB has never seen is legal. So the metadata is
    documentation and the schema constrains nothing — no `enum`, and equally no
    `const` and no `pattern`, either of which would refuse an unrecognised
    spelling just as firmly while looking like a formatting rule.

    That is what makes UBB learning a new unit a non-event for the published
    contract rather than a breaking change every client has to be re-generated
    for. The wire half of the same claim is
    `api/v1/tests/test_event_type_endpoints.py`, where a unit UBB has never met
    is POSTed and comes back unchanged.

    That the block CONTAINS the registry's known values is
    `test_g4_no_open_concept_is_a_closed_enum_in_the_contract`'s assertion and
    is not restated here. This one is about what the node does NOT carry.
    """
    checked = 0
    for pointer, node in marked_nodes(spec):
        name = node[MARKER]
        if decisions[name].representation != KNOWN_VALUES:
            continue
        checked += 1

        for keyword in VALUE_BOUNDING_KEYWORDS:
            assert keyword not in node, (
                f"{pointer} bounds the values of the open concept {name!r} "
                f"with `{keyword}`. A value UBB has never seen is legal "
                f"(ADR-0003), so this would make UBB learning one a breaking "
                f"change to the published contract")

        # The registry's own half of the same statement: the concept must
        # actually ALLOW the unknown value the schema declines to refuse.
        assert registry.concepts[name].allow_unknown, name

    assert checked == sum(published.nodes for published
                          in CONCEPTS_IN_THE_CONTRACT.values()
                          if published.kind == KNOWN_VALUES), (
        "the walk found a different number of known-value nodes than the "
        "accounting above declares — suspect the walk, not the contract")


def test_the_spec_export_applies_the_metadata(spec):
    """The wiring, read out of the export's own source.

    Everything above is about the applier and the document; none of it would
    fail if the platform simply stopped calling either. Read rather than
    imported because this suite has no Django — the same reason
    `tools/sdk_operations` parses the SDK instead of importing it.
    """
    tree = ast.parse(EXPORT_MODULE.read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module == "tools.known_values"
                for alias in node.names}
    assert {"apply_known_values", "read_decisions"} <= imported, (
        "ubb-platform/api/v1/openapi_export.py no longer imports the applier")

    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "apply_known_values" in called
    assert "read_decisions" in called

    exporter = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "generated_document_text")
    reached = {n.func.id for n in ast.walk(exporter)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert reached & {"apply_known_values", "_apply_known_values"}, (
        "the applier is imported but the rendered document never reaches it")


# ---------------------------------------------------------------------------
# 3. Vacuity guards (#191 story 20)
# ---------------------------------------------------------------------------

def test_the_gate_read_the_committed_contract(spec):
    """A path bug must not turn every walk above into a walk over `{}`."""
    assert len(spec["components"]["schemas"]) >= 150
    assert len(spec["paths"]) >= 100
    assert len(_enums(spec)) >= 3, (
        "no enum found in the contract at all — either the accounting above "
        "has nothing to account for, or the walk broke")


def test_the_registry_has_an_open_concept_for_the_gate_to_protect(registry,
                                                                  decisions):
    """G4 protects `open` concepts. A registry with none would make the gate an
    assertion about the empty set, green forever."""
    open_concepts = [name for name, d in decisions.items()
                     if d.representation == KNOWN_VALUES]
    assert open_concepts, "no open concept reaches the contract"
    assert all(registry.concepts[name].allow_unknown for name in open_concepts)


def test_the_committed_document_is_the_one_the_export_reads():
    """The two paths agree, checked rather than assumed.

    The generator writes `openapi/known-values.json` and the platform reads a
    path it computes from its own file location. Those are two independent
    spellings of one fact, and a mismatch would leave the export applying a
    document nobody regenerates.
    """
    source = EXPORT_MODULE.read_text(encoding="utf-8")
    assert '"known-values.json"' in source
    assert DOCUMENT_PATH.is_file()
    assert OPENAPI_KNOWN_VALUES.path == "openapi/known-values.json"


# ---------------------------------------------------------------------------
# 4. Negative controls — the applier is shown to emit, and to refuse
# ---------------------------------------------------------------------------

def test_an_open_concept_becomes_documentation_metadata_never_an_enum():
    """#191 story 19's positive half, and the whole of ADR-0003's stance.

    Without this control everything above would be satisfied by a mechanism
    that can only ever emit nothing — which is exactly what the committed tree
    looks like today.
    """
    node = _applied(_document(_string_property("synthetic_concept")),
                    {"synthetic_concept": _decision(
                        representation=KNOWN_VALUES, kind="open")})

    assert node[KNOWN_VALUES_KEY] == ["alpha", "beta"]
    assert "enum" not in node, "an open concept was closed into an enum"
    assert node["type"] == "string", "the field stopped being an open string"
    assert node[MARKER] == "synthetic_concept", "the mapping G4 reads was lost"


def test_a_closed_concept_becomes_a_real_enum():
    """The other kind. A `closed` concept is exactly its values, so the schema
    may say so — and must not also carry the documentation form, which would
    give one field two statements of one value set."""
    node = _applied(_document(_string_property("synthetic_concept")),
                    {"synthetic_concept": _decision(representation=ENUM)})

    assert node["enum"] == ["alpha", "beta"]
    assert KNOWN_VALUES_KEY not in node


def test_a_nullable_field_is_annotated_rather_than_refused():
    """django-ninja renders `str | None` as `anyOf`, and refusing that would
    refuse every optional vocabulary field for no defensible reason."""
    node = _applied(
        _document({"anyOf": [{"type": "string"}, {"type": "null"}],
                   MARKER: "synthetic_concept"}),
        {"synthetic_concept": _decision(representation=KNOWN_VALUES,
                                        kind="open")})

    assert node[KNOWN_VALUES_KEY] == ["alpha", "beta"]


def test_a_document_with_no_marker_is_returned_unchanged():
    """The control that gives the ones above their meaning: without it, an
    applier that rewrote every node would pass all of them."""
    document = _document({"type": "string", "title": "Status"})

    assert apply_known_values(document, {}) == document


def test_the_applier_finds_markers_at_every_depth():
    """Paths, components and webhooks are three different subtrees, and a
    walker that only descended one would silently annotate a third of the
    contract."""
    decisions = {"synthetic_concept": _decision(representation=KNOWN_VALUES,
                                                kind="open")}

    def body():
        return {"content": {"application/json": {"schema": {"properties": {
            "status": _string_property("synthetic_concept")}}}}}

    document = {
        "paths": {"/tasks/{id}": {"get": {"responses": {"200": body()}}}},
        "webhooks": {"task.completed": {"post": {"requestBody": body()}}},
        "components": {"schemas": {"Thing": {"properties": {
            "status": _string_property("synthetic_concept")}}}},
    }

    assert len(marked_nodes(document)) == 3
    applied = apply_known_values(document, decisions)
    assert len(marked_nodes(applied)) == 3
    for _, node in marked_nodes(applied):
        assert node[KNOWN_VALUES_KEY] == ["alpha", "beta"]


def test_stripping_undoes_applying_and_touches_nothing_else():
    """The inverse the fixed-point check above rests on, with both halves of
    its scope proved.

    Round-trip: strip after apply gives the document back. Scope: an `enum` on
    an UNMARKED node — which is exactly where a silent conversion sits — must
    survive stripping untouched, or the check above would launder the thing the
    enum inventory exists to find.
    """
    decisions = {"synthetic_concept": _decision(representation=ENUM)}
    original = _document(_string_property("synthetic_concept"))
    applied = apply_known_values(original, decisions)

    assert applied != original, "the applier did nothing — nothing is proven"
    assert strip_known_values(applied) == original

    hand_written = _document({"type": "string", "enum": ["a", "b"]})
    assert strip_known_values(hand_written) == hand_written


def test_negative_control_an_unserved_concept_is_refused_not_advertised():
    """**The rule this ticket exists for.** A field marked before its backend
    consumer has been converted stops the export.

    Refused rather than silently skipped: the debt is already a migration-ledger
    entry, and a marker that quietly does nothing is a check that cannot fail —
    the failure this repository has shipped three times. The order is therefore
    fixed: convert the consumer, then mark the field.
    """
    refusal = _refusal(_document(_string_property("synthetic_concept")),
                       {"synthetic_concept": _decision(advertised=False)})

    assert refusal.code == codes.NOT_ADVERTISED
    assert "0 of 2 values" in refusal.message


def test_negative_control_a_hand_written_enum_under_a_marker_is_refused():
    """The silent conversion, caught at the moment it would be published.

    A field typed `Literal[...]` *and* marked is the exact shape G4 is named
    after: for an open concept the enum closes it, and for a closed one it is a
    second copy of a value set the registry owns.
    """
    for representation, kind in ((KNOWN_VALUES, "open"), (ENUM, "closed")):
        refusal = _refusal(
            _document(_string_property("synthetic_concept",
                                       enum=["alpha", "beta"])),
            {"synthetic_concept": _decision(representation=representation,
                                            kind=kind)})
        assert refusal.code == codes.ALREADY_ENUMERATED


def test_negative_control_a_hand_written_annotation_is_refused():
    """Only this export may write `x-ubb-known-values`. A hand-written one
    would be indistinguishable from a generated one in the committed bytes."""
    refusal = _refusal(
        _document(_string_property("synthetic_concept",
                                   **{KNOWN_VALUES_KEY: ["alpha"]})),
        {"synthetic_concept": _decision(representation=KNOWN_VALUES,
                                        kind="open")})

    assert refusal.code == codes.ALREADY_ANNOTATED


def test_negative_control_an_unknown_concept_is_refused():
    """A typo in a marker must not read as "this concept is not advertised".

    Both would emit nothing; only one of them is a mistake, and telling them
    apart is the difference between a spec that is silent on purpose and one
    that is silent by accident.
    """
    refusal = _refusal(_document(_string_property("no_such_concept")), {})

    assert refusal.code == codes.UNKNOWN_CONCEPT


def test_negative_control_a_non_string_node_is_refused():
    """A value set is a set of strings. A marker on an integer field is a
    mistake, and annotating it anyway would publish a schema no client could
    satisfy."""
    refusal = _refusal(
        _document({"type": "integer", MARKER: "synthetic_concept"}),
        {"synthetic_concept": _decision()})

    assert refusal.code == codes.NOT_A_STRING


def test_negative_control_a_malformed_marker_is_refused():
    refusal = _refusal(_document({"type": "string", MARKER: 7}),
                       {"synthetic_concept": _decision()})

    assert refusal.code == codes.MALFORMED_MARKER


def test_a_refusal_names_the_field_that_caused_it():
    """A spec export that fails must say WHICH field, or the author goes
    hunting through 165 component schemas by hand."""
    refusal = _refusal(_document(_string_property("no_such_concept")), {})

    assert refusal.location == "/components/schemas/Thing/properties/status"


def test_the_loader_refuses_a_document_it_cannot_read():
    """A malformed decision document raises rather than degrading to "nothing
    is advertised", which would strip the contract's metadata in silence."""
    broken = {
        "a version this applier does not read":
            {"version": 99, "concepts": {}},
        "no concepts at all, which would advertise nothing forever":
            {"version": 1, "concepts": {}},
        "a representation that is not one of the three":
            {"version": 1, "concepts": {"x": {"representation": "maybe",
                                              "advertised": False}}},
        "`advertised` that is not a boolean":
            {"version": 1, "concepts": {"x": {"representation": ENUM,
                                              "advertised": "yes"}}},
        "an advertised row with nothing to advertise":
            {"version": 1, "concepts": {"x": {"representation": ENUM,
                                              "advertised": True}}},
        "values sitting on a row that may not publish them":
            {"version": 1, "concepts": {"x": {"representation": ENUM,
                                              "advertised": False,
                                              "values": ["a"]}}},
    }
    for description, document in broken.items():
        with pytest.raises(KnownValuesRefused, match=r"document-invalid"):
            read(document)
            pytest.fail(f"the loader accepted {description}")


# ---------------------------------------------------------------------------
# 5. `decide` over a synthetic tree — advertising is reachable
# ---------------------------------------------------------------------------

def _synthetic(tmp_path, *, source, **overrides):
    """A one-concept registry with a backend AND a contract consumer.

    The generated artifacts are rendered by the shipped generator rather than
    typed here, so the name the consumer imports is the name the artifact
    actually binds — `test_consumer_census.py`'s reasoning, and the reason
    these controls cannot pass against a fossil of an older naming rule.
    """
    from tools.consumers.census import SURFACES

    body = concept(**overrides)
    body = {key: value for key, value in body.items() if value is not None}
    body["consumers"] = [{"surface": BACKEND, "path": CONSUMER_PATH},
                         {"surface": CONTRACT, "path": "openapi/v1.json"}]
    registry_dir = write_registry(
        tmp_path, concepts={"synthetic.yaml": {"synthetic_concept": body}},
        consumer_files=(CONSUMER_PATH, "openapi/v1.json"))
    (tmp_path / CONSUMER_PATH).write_text(source, encoding="utf-8")

    registry = load_registry(registry_dir, tmp_path)
    for generated in SURFACES.values():
        path = tmp_path / generated.target.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated.target.render(registry), encoding="utf-8")

    return decide(registry.concepts["synthetic_concept"],
                  take_census(tmp_path, registry))


def test_positive_control_a_converted_consumer_makes_the_contract_advertise(
        tmp_path):
    """**The control that makes `advertised` reachable at all.**

    Everything in section 1 is satisfied today by 42 rows saying `false`. This
    is the one that proves the rule has an on-state: a backend consumer that
    imports the generated constants flips the concept to advertised, and its
    values arrive in the document.

    It is also the shape of what a later slice does — convert the model, and
    the contract follows in the same change.
    """
    decision = _synthetic(
        tmp_path,
        source="from core.vocabulary import SYNTHETIC_CONCEPT_VALUES\n")

    assert decision.advertised is True
    assert decision.values == ("alpha", "beta")
    assert decision.backend_serves == "2 of 2 values"
    assert decision.representation == ENUM


def test_negative_control_a_partly_converted_consumer_advertises_nothing(
        tmp_path):
    """Half a conversion is not half a contract.

    A consumer importing one of two constants is measured as one of two, and
    the contract stays silent — publishing a value set with a value missing
    would be a falsehood of exactly the kind #208's rule exists to refuse.
    """
    decision = _synthetic(
        tmp_path, source="from core.vocabulary import SYNTHETIC_CONCEPT_ALPHA\n")

    assert decision.advertised is False
    assert decision.values is None
    assert decision.backend_serves == "1 of 2 values"


def test_an_open_concepts_known_values_reach_the_contract_as_metadata(tmp_path):
    """The open half of the positive control, end to end: registry to census to
    decision to applied document, with no `enum` anywhere along it."""
    decision = _synthetic(
        tmp_path, kind="open", known_values=["alpha", "beta"],
        allow_unknown=True, values=None,
        source="from core.vocabulary import SYNTHETIC_CONCEPT_KNOWN_VALUES\n")

    assert decision.representation == KNOWN_VALUES
    assert decision.advertised is True

    node = _applied(_document(_string_property("synthetic_concept")),
                    {"synthetic_concept": decision})
    assert node[KNOWN_VALUES_KEY] == ["alpha", "beta"]
    assert "enum" not in node


def test_a_concept_with_no_contract_consumer_contributes_nothing(tmp_path):
    """The registry's own statement that a concept does not appear in the spec.

    `stop_behavior` is the real case — an SDK-only concept — and a generator
    that advertised it anyway would be putting a value set into a contract the
    registry never said it belonged in.
    """
    from tools.consumers.census import SURFACES

    body = concept()
    body["consumers"] = [{"surface": BACKEND, "path": CONSUMER_PATH}]
    registry_dir = write_registry(
        tmp_path, concepts={"synthetic.yaml": {"synthetic_concept": body}})
    (tmp_path / CONSUMER_PATH).write_text(
        "from core.vocabulary import SYNTHETIC_CONCEPT_VALUES\n",
        encoding="utf-8")
    registry = load_registry(registry_dir, tmp_path)
    for generated in SURFACES.values():
        path = tmp_path / generated.target.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated.target.render(registry), encoding="utf-8")

    decision = decide(registry.concepts["synthetic_concept"],
                      take_census(tmp_path, registry))

    assert decision.representation == NOTHING
    assert decision.advertised is False


# ---------------------------------------------------------------------------
# 6. The migration ledger — every concept not yet served is owed
# ---------------------------------------------------------------------------

def _entries(programme):
    return tuple(e for e in programme.entries if e.gate == "G4")


def _owed_sites(decisions):
    """The site every unadvertised concept that reaches the contract owes.

    `openapi/v1.json::<concept>` — per (document, concept), the shape G2 and G3
    use. Per value would be 130 rows churning whenever a value moves; per
    document would be one row hiding twenty-nine debts behind each other.
    """
    return {f"openapi/v1.json::{name}"
            for name, decision in decisions.items()
            if decision.representation != NOTHING and not decision.advertised}


def test_g4_every_unadvertised_concept_is_an_identified_debt(programme,
                                                             decisions):
    """AC: every concept not yet served has a migration ledger entry naming the
    slice that renames it.

    There is no third answer. A concept the contract cannot advertise is either
    advertised or owed, and an unowed one would be a silence nobody has
    scheduled to end.
    """
    unowed = sorted(_owed_sites(decisions) - {e.site for e in _entries(programme)})
    assert not unowed, (
        f"{len(unowed)} concept(s) the contract cannot advertise, with no "
        f"ledger entry naming the slice that removes the debt:\n"
        + "\n".join(f"  {site}" for site in unowed))


def test_g4_every_seeded_entry_is_still_a_real_violation(programme, decisions):
    """An entry cannot outlive the debt it records: paying it and deleting it
    are one act (#203's rule). Otherwise the ledger goes on claiming a concept
    that has already reached the contract."""
    live = _owed_sites(decisions)
    stale = sorted(e.id for e in _entries(programme) if e.site not in live)
    assert not stale, (
        f"{len(stale)} ledger entr(ies) record a debt that has been paid — "
        f"delete them in the change that advertised the concept:\n"
        + "\n".join(f"  {entry}" for entry in stale))


def test_g4_every_entrys_extent_is_exactly_what_the_document_records(
        programme, decisions):
    """`found` carries how much of the concept the backend already holds, so
    partial payment moves a number rather than nothing at all — and an entry
    cannot overstate its own debt, which the ratchet alone would never see."""
    faults = []
    for entry in _entries(programme):
        name = entry.site.rpartition("::")[2]
        recorded = decisions[name].backend_serves if name in decisions else None
        if entry.found != recorded:
            faults.append(f"{entry.id}: records {entry.found!r}; the document "
                          f"records {recorded!r}")
    assert not faults, "\n".join(f"  {fault}" for fault in faults)


def test_every_g4_entry_names_a_concept_and_agrees_with_its_site(registry,
                                                                 programme):
    """`expected` is the canonical term the site should carry, so it must be a
    live concept — and the same one the site names, or the entry is about two
    different things."""
    for entry in _entries(programme):
        assert entry.expected in registry.concepts, entry.id
        assert entry.site.rpartition("::")[2] == entry.expected, entry.id
        assert entry.site.startswith("openapi/v1.json::"), entry.id


def test_the_g4_seeding_is_the_size_the_document_says(programme, decisions):
    """A vacuity guard on the ledger half.

    The count is what a reviewer approved. If the seeding shrank to three
    entries because a walk broke, every test above would still pass — they are
    all "for each entry" — and this is what would not.

    THE FLOOR MOVES DOWN BY ONE PER CONCEPT PAID, AND ONLY THEN. It went 25 →
    24 in #317, which advertised `costing_status`, 24 → 23 in #351, which
    advertised `pricing_status` — the same concept one slice later on the other
    side of the margin, and the same single-entry step — 23 → 22 in #355, which
    advertised `pricing_method`, the second concept of that pair's own slice and
    again one entry, and 22 → 21 in #366, which advertised `rate_structure`.

    ⚠ THAT LAST ONE PAID TWO ENTRIES AND MOVED THIS FLOOR BY ONE, which is
    right rather than an accounting slip: the G4 debt and the backend G2 debt
    were the SAME debt read from two sides, and the contract could not advertise
    the values until the backend consumer held them. Only the G4 entry is in
    this seeding, so only one comes out of it.

    ⚠ #351 also COINED `not_applicable_reason`, and that moved the floor by
    nothing at all. A concept whose backend consumer holds every value on the
    day it is declared has never owed a G4 debt, so there is no entry to delete
    and the seeding does not shrink. A floor lowered for it would have been
    lowered for a deletion that never happened.

    Lowering it is the correct
    response to a debt being paid and the WRONG response to a walk breaking,
    and the two are told apart by the assertion above it rather than by this
    one: the equality already holds the real claim — as many entries as owed
    sites, in both directions — so a walk that returned nothing would fail
    there first, with a diff a reader can act on. This line exists for the case
    the equality cannot see, where BOTH halves collapse together, and a floor
    that only ever descends in step with a deletion still catches it.
    """
    assert len(_entries(programme)) == len(_owed_sites(decisions))
    assert len(_entries(programme)) >= 21, (
        f"only {len(_entries(programme))} G4 debts — the contract has not "
        f"suddenly caught up with the registry, so suspect the walk")
