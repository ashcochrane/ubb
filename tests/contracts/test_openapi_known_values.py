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
worse than saying nothing because a consumer can act on it. Today that rule
withholds every concept: nothing in the tree is served yet, so the contract
carries no metadata and 29 concepts are individually identified migration-ledger
entries owed by the slices that rename them. **That is the correct outcome for
slice 0 and it is not a sign the mechanism is wrong.**

It does mean the marker-driven half of the gate has nothing in the committed
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
    """
    assert len(_entries(programme)) == len(_owed_sites(decisions))
    assert len(_entries(programme)) >= 25, (
        f"only {len(_entries(programme))} G4 debts — the contract has not "
        f"suddenly caught up with the registry, so suspect the walk")
