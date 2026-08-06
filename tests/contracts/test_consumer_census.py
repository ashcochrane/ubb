"""G2 and G3 — no surface restates a value set it could import (#227).

The registry's `consumers.yaml` says a declared consumer is an **end-state**
consumer: the place a canonical value will live once its slice has run, not a
claim that the file already carries it, and *"every disagreement that survives is
a migration-ledger entry naming the slice that removes it"*. These two gates are
that sentence made mechanical.

    G2  every value of a CLOSED concept is held by reference by every consumer
        the registry declares for it, on all three generated surfaces.
    G3  the same of an OPEN concept's KNOWN values — and in one direction only.

**One census, two readings.** Both gates call
:func:`tools.consumers.take_census`, which is also the predicate #208 consumes
for its own rule that the spec advertises a value only where the backend serves
it. Two implementations of one predicate is the shape that already bit #203,
whose agreement test was wrong until it was run.

**G3's asymmetry is enforced in one direction only**, and that is the half that
is easy to get backwards:

    a registry-known value missing from a UBB-owned consumer   -> defect
    a runtime value the registry has never seen                -> legal, silent

A G3 that reported the second would make UBB learning a new value a CI failure,
which is exactly what ADR-0003 exists to prevent. It is proved silent below
rather than asserted to be.

Every negative control drives the REAL census over a synthetic tree. Nothing
here patches its internals: a test that mocks the thing under test can only
reproduce its mistakes, which is how three SDK methods called routes that
existed nowhere and stayed green for months.
"""

import re

import pytest
import yaml

from _helpers import CONSUMER_PATH, REPO_ROOT, concept, write_registry
from tools.consumers import errors as codes
from tools.consumers import take_census
from tools.consumers.census import SURFACES, serving_surfaces
from tools.gates import load_programme
from tools.vocabulary import load_registry
from tools.vocabulary.generate import BACKEND_CONSTANTS, CONSOLE_VOCABULARY

#: Which gate reads which kind. The whole difference between them.
GATES = {"G2": ("closed",), "G3": ("open",)}

#: A ledger entry's extent: how much of the debt is already paid.
_EXTENT = re.compile(r"^(?P<held>\d+) of (?P<total>\d+) values$")


# ---------------------------------------------------------------------------
# The real repository, censused once
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


def entries_for(programme, gate):
    return tuple(e for e in programme.entries if e.gate == gate)


# ---------------------------------------------------------------------------
# 1. Could the census see at all?
# ---------------------------------------------------------------------------

def test_the_census_was_taken_without_a_fault(census):
    """A fault means the walk did not happen, and "found nothing" would be a
    lie about a tree nobody opened. So it fails here, before either gate."""
    assert not census.faults, (
        f"{len(census.faults)} fault(s) stopped the census being taken:\n"
        + "\n".join(f"  {fault}" for fault in census.faults))


def test_the_census_read_every_surface(census, registry):
    """#191 story 20's vacuity guard, in the form that matters here.

    Not a count of files — the number moves whenever the registry declares a
    consumer — but the claim the acceptance criterion makes: all three
    generated surfaces are walked. A resolution bug that silently dropped the
    SDK would leave five debts unrecorded and a green board.
    """
    walked = {v.surface for v in census.verdicts}
    assert walked == serving_surfaces(), (
        f"the census covered {sorted(walked)}; the surfaces with a generated "
        f"artifact to import are {sorted(serving_surfaces())}")
    for surface in serving_surfaces():
        assert (REPO_ROOT / SURFACES[surface].target.path).is_file()


def test_the_census_covers_every_valued_concept_the_registry_gives_a_consumer(
        census, registry):
    """Derived from the registry, so a concept declared tomorrow is walked
    tomorrow. What this refuses is a census that quietly stopped at a subset."""
    expected = {(c.name, consumer.surface)
                for c in registry.concepts.values() if c.declared_values
                for consumer in c.consumers
                if consumer.surface in serving_surfaces()}
    assert {(v.concept, v.surface) for v in census.verdicts} == expected


def test_every_censused_consumer_was_actually_read(census):
    assert census.read, "the census read no files at all"
    for path in census.read:
        assert (REPO_ROOT / path).is_file()


# ---------------------------------------------------------------------------
# 2. The gates
# ---------------------------------------------------------------------------

#
# One helper per question, and two named tests over each. NOT `parametrize`:
# the gate manifest names an enforcement site and proves the suite collects it,
# and it does that by finding the function — a parametrised id like
# `test_x[G2]` is collectible but not statically provable without evaluating
# the decorator. A gate whose armed-ness cannot be checked is the one thing
# #201 exists to refuse, so the manifest gets unambiguous nodes and the shared
# implementation stays in the helper.
#

def _unowed(census, programme, gate):
    owed = {entry.site for entry in entries_for(programme, gate)}
    return sorted({f.site for f in census.findings(GATES[gate])} - owed)


def _stale(census, programme, gate):
    live = {f.site for f in census.findings(GATES[gate])}
    return sorted(e.id for e in entries_for(programme, gate)
                  if e.site not in live)


def _extent_faults(census, programme, gate):
    extents = census.extents(GATES[gate])
    faults = []
    for entry in entries_for(programme, gate):
        recorded = _parse_extent(entry.found)
        if recorded is None:
            faults.append(f"{entry.id}: `found: {entry.found}` is not "
                          f"`<n> of <n> values`")
        elif entry.site in extents and recorded != extents[entry.site]:
            held, total = extents[entry.site]
            faults.append(f"{entry.id}: records {recorded[0]} of "
                          f"{recorded[1]}; the census finds {held} of {total}")
    return faults


def _assert_owed(census, programme, gate):
    unowed = _unowed(census, programme, gate)
    assert not unowed, (
        f"{len(unowed)} consumer(s) restate a value set they could import, "
        f"with no ledger entry naming the slice that removes them:\n"
        + "\n".join(f"  {site}" for site in unowed))


def _assert_not_stale(census, programme, gate):
    stale = _stale(census, programme, gate)
    assert not stale, (
        f"{len(stale)} ledger entr(ies) record a debt that has been paid — "
        f"delete them in the change that converted the consumer:\n"
        + "\n".join(f"  {entry}" for entry in stale))


def test_g2_every_closed_value_is_held_by_reference_or_owed(census, programme):
    """THE GATE. A value a declared consumer does not hold by reference is a
    second copy of a canonical token — the thing ADR-0008 §3 abolishes — and it
    is either fixed or owed by a named slice. There is no third answer."""
    _assert_owed(census, programme, "G2")


def test_g3_every_known_open_value_is_held_by_reference_or_owed(census,
                                                                programme):
    """THE GATE's open half. Same rule, `open` concepts, one direction only —
    see `test_negative_control_an_unknown_runtime_value_is_never_a_finding`."""
    _assert_owed(census, programme, "G3")


def test_g2_every_seeded_entry_is_still_a_real_violation(census, programme):
    """An entry cannot outlive the debt it records.

    #203's rule: paying a debt and deleting its entry are one act. Without
    this the ledger would go on claiming a consumer that had already been
    converted, and "the ledger only shrinks" would be satisfied by a list that
    had stopped meaning anything.
    """
    _assert_not_stale(census, programme, "G2")


def test_g3_every_seeded_entry_is_still_a_real_violation(census, programme):
    _assert_not_stale(census, programme, "G3")


def test_g2_every_entrys_extent_is_exactly_what_the_census_finds(census,
                                                                 programme):
    """The count is checked in BOTH directions, for G7's reason.

    Too few values held and the consumer has regressed. Too many and the entry
    is an excuse with no upper bound — the ratchet compares entry identities
    rather than their contents, so a `9 of 9 values` typed into one would
    licence the whole concept for as long as the entry stood. Paying part of a
    debt therefore means editing its number, which is the change being
    recorded rather than an inconvenience.
    """
    faults = _extent_faults(census, programme, "G2")
    assert not faults, "\n".join(f"  {fault}" for fault in faults)


def test_g3_every_entrys_extent_is_exactly_what_the_census_finds(census,
                                                                 programme):
    faults = _extent_faults(census, programme, "G3")
    assert not faults, "\n".join(f"  {fault}" for fault in faults)


def test_no_entry_names_a_concept_the_registry_does_not_declare(registry,
                                                                programme):
    """`expected` is the canonical term the site should import, so it must be a
    live concept. An entry promising a replacement nothing declares is a debt
    nobody can pay correctly."""
    wrong = [(e.id, e.expected) for gate in GATES
             for e in entries_for(programme, gate)
             if e.expected not in registry.concepts]
    assert not wrong, f"entries expect a concept the registry lacks: {wrong}"


def test_every_entry_expects_the_concept_its_site_names(programme):
    """The site carries the concept, and so does `expected`. They agree or the
    entry is about two different things."""
    wrong = [e.id for gate in GATES for e in entries_for(programme, gate)
             if e.site.rpartition("::")[2] != e.expected]
    assert not wrong, f"entries whose site and `expected` disagree: {wrong}"


def test_each_gate_reads_only_its_own_kind(programme, registry):
    """G2 is closed, G3 is open — the whole reason they are two gates.

    An entry filed under the wrong one would be checked against a census that
    never looks at its concept, and would sit there unfalsifiable.
    """
    for gate, kinds in GATES.items():
        wrong = [e.id for e in entries_for(programme, gate)
                 if registry.concepts[e.expected].kind not in kinds]
        assert not wrong, (
            f"{gate} covers {kinds[0]} concepts; these entries name another "
            f"kind: {wrong}")


# ---------------------------------------------------------------------------
# 3. G3's asymmetry — the half that must never fire
# ---------------------------------------------------------------------------

def test_the_census_never_reports_a_value_the_registry_has_never_seen(
        census, registry):
    """THE CONTROL the acceptance criterion asks for, over the real tree.

    An unknown value is not merely unreported — it is *unrepresentable*. Every
    verdict's `held` and `missing` partition exactly the registry's declared
    values for that concept, so there is nowhere for a runtime value to appear
    even if the walker wanted to report one. That is stronger than a rule
    somebody has to remember not to break, and it is why the asymmetry is a
    property of the data structure rather than of the check.
    """
    for verdict in census.verdicts:
        declared = set(registry.concepts[verdict.concept].declared_values)
        assert set(verdict.held) | set(verdict.missing) == declared
        assert not set(verdict.held) & set(verdict.missing)

    for finding in census.findings(("closed", "open")):
        assert finding.value in \
            registry.concepts[finding.concept].declared_values


def test_negative_control_an_unknown_runtime_value_is_never_a_finding(tmp_path):
    """The asymmetry, driven through the real census on a synthetic tree.

    An `open` concept whose consumer holds every known value AND handles one
    the registry has never seen is fully served, and the extra is not reported
    in any form. If it were, adding an enforcement path would turn CI red on
    the day UBB gained it — ADR-0003's whole subject.
    """
    census = _synthetic(
        tmp_path, kind="open", known_values=["alpha", "beta"],
        allow_unknown=True, values=None,
        source="from core.vocabulary import SYNTHETIC_CONCEPT_KNOWN_VALUES\n"
               "EXTRA = 'a_value_the_registry_has_never_seen'\n")

    assert census.serves("synthetic_concept", "backend")
    assert not census.findings(("open",))
    assert not census.findings(("closed",))


def test_negative_control_a_known_value_left_behind_is_a_finding(tmp_path):
    """And the direction that DOES fire, so the silence above is a choice.

    A consumer holding one of an open concept's two known values owes the
    other. Without this, the control above would be satisfied by a gate that
    reports nothing at all.
    """
    census = _synthetic(
        tmp_path, kind="open", known_values=["alpha", "beta"],
        allow_unknown=True, values=None,
        source="from core.vocabulary import SYNTHETIC_CONCEPT_ALPHA\n")

    assert not census.serves("synthetic_concept", "backend")
    assert [f.value for f in census.findings(("open",))] == ["beta"]


# ---------------------------------------------------------------------------
# 4. Negative controls — the gate must FAIL on a synthetic violation
# ---------------------------------------------------------------------------

def test_negative_control_a_restated_closed_value_set_is_a_finding(tmp_path):
    """#191 story 19. The gate's own reason to exist: a consumer that spells
    every value correctly and imports nothing holds nothing."""
    census = _synthetic(
        tmp_path, source='CHOICES = [("alpha", "A"), ("beta", "B")]\n')

    assert not census.serves("synthetic_concept", "backend")
    assert [f.value for f in census.findings(("closed",))] == ["alpha", "beta"]


def test_positive_control_an_importing_consumer_is_served(tmp_path):
    """The other half. Without it, the control above passes over a census that
    reports every consumer as unserved."""
    census = _synthetic(
        tmp_path,
        source="from core.vocabulary import SYNTHETIC_CONCEPT_VALUES\n")

    assert census.serves("synthetic_concept", "backend")
    assert not census.findings(("closed",))


def test_the_whole_set_name_and_the_per_value_constants_both_serve(tmp_path):
    """Two honest spellings of holding a value by reference.

    A Django `choices=` list needs the per-value constants, because each pairs
    with its own English; a service comparing membership wants the set. Both
    reach the artifact, so both serve — and the census measures per value, so a
    consumer that imported two of three is neither served nor wholly unserved.
    """
    census = _synthetic(
        tmp_path,
        source="from core.vocabulary import SYNTHETIC_CONCEPT_ALPHA\n")
    assert not census.serves("synthetic_concept", "backend")
    assert [f.value for f in census.findings(("closed",))] == ["beta"]
    assert census.extents(("closed",)) == {
        f"{CONSUMER_PATH}::synthetic_concept": (1, 2)}


def test_the_console_holds_a_closed_concept_through_its_union_type(tmp_path):
    """A type import is the strongest form of holding a value by reference.

    The console binds no per-value constant, so its handles are the array, the
    union type and the label-key map — and the console's own compiler is what
    enforces the set. Refusing to count a type import would report the tightest
    consumer as the emptiest one.
    """
    census = _synthetic(
        tmp_path, consumer="apps/ui/src/lib/labels.ts",
        source='import type { SyntheticConcept } from "./vocabulary";\n')
    assert census.serves("synthetic_concept", "console")


def test_an_open_concepts_own_type_does_not_hold_its_known_values(tmp_path):
    """THE SUBTLE ONE, and the reason `known_type_name` exists at all.

    An open concept's type renders as `<Known> | (string & {})` so an unseen
    value stays legal (ADR-0003) — which means a consumer typing a field with
    it has enumerated NOTHING. Counting it would report every open concept as
    served the moment the console named its type, and G3 would go quiet about
    the values it exists to require. The KNOWN type is the one that carries
    them, and it serves.
    """
    def census(imported):
        # Its own tree per import, so the two runs cannot share an artifact.
        root = tmp_path / imported
        root.mkdir(parents=True, exist_ok=True)
        return _synthetic(
            root, kind="open", known_values=["alpha", "beta"],
            allow_unknown=True, values=None,
            consumer="apps/ui/src/lib/labels.ts",
            source=f'import type {{ {imported} }} from "./vocabulary";\n')

    assert not census("SyntheticConcept").serves("synthetic_concept", "console")
    assert census("SyntheticConceptKnown").serves("synthetic_concept",
                                                  "console")


def test_negative_control_a_missing_artifact_is_a_fault_not_a_finding(tmp_path):
    """If the generated module is gone, every consumer on that surface is
    correctly unable to import it. Reporting them one by one would bury the one
    cause under fifty consequences."""
    census = _synthetic(tmp_path, source="x = 1\n", artifacts=("console",
                                                               "sdk"))
    assert {f.code for f in census.faults} == {codes.ARTIFACT_MISSING}


def test_negative_control_a_consumer_file_that_vanished_is_a_fault(tmp_path):
    """A declared consumer with no file is a fault, never a silent zero.

    The registry's own compiler refuses a consumer path that does not resolve,
    so this cannot arise from a committed registry — which is why the control
    deletes the file AFTER loading. The census still has to answer honestly:
    "the file is gone" and "the file holds nothing" are one output otherwise,
    and the second is a debt while the first is a broken walk.
    """
    registry_dir = write_registry(
        tmp_path, concepts={"synthetic.yaml": {"synthetic_concept": concept()}})
    registry = load_registry(registry_dir, tmp_path)
    _write_artifacts(tmp_path, registry)
    (tmp_path / CONSUMER_PATH).unlink()

    census = take_census(tmp_path, registry)
    assert {f.code for f in census.faults} == {codes.CONSUMER_MISSING}
    assert not census.verdicts


def test_negative_control_a_star_import_is_a_fault_not_a_pass(tmp_path):
    """One line must not be able to excuse a whole surface."""
    census = _synthetic(tmp_path,
                        source="from core.vocabulary import *\n")
    assert {f.code for f in census.faults} == {codes.STAR_IMPORT}


# ---------------------------------------------------------------------------
# 5. The predicate #208 consumes
# ---------------------------------------------------------------------------

def test_serves_refuses_a_surface_with_no_generated_artifact(census):
    """`openapi` is a declared surface with no importable artifact: a JSON
    document cannot hold a value by reference. Answering True or False would
    both be lies, and #208 must not read "the backend does not serve it" from
    "nobody asked"."""
    with pytest.raises(KeyError, match="no generated artifact"):
        census.serves("task_status", "openapi")


def test_serves_refuses_a_concept_it_has_no_verdict_on(census):
    with pytest.raises(KeyError, match="declares no"):
        census.serves("event_type_key", "backend")
    with pytest.raises(KeyError, match="declares no"):
        census.serves("a_concept_nobody_declared", "backend")


def test_serves_agrees_with_the_findings_it_is_derived_from(census):
    """One mechanism, asked two ways, giving one answer. This is the
    acceptance criterion — the predicate exists ONCE — stated as a test rather
    than as an intention about how #208 will use it."""
    unserved = {(f.concept, f.surface) for f in census.findings(("closed",
                                                                "open"))}
    for verdict in census.verdicts:
        assert census.serves(verdict.concept, verdict.surface) is (
            (verdict.concept, verdict.surface) not in unserved)


# ---------------------------------------------------------------------------
# 6. What the census may not do
# ---------------------------------------------------------------------------

def test_no_finding_is_derived_from_a_consumers_own_enumerations(census):
    """The declaration census is a fact about a FILE, and never a finding.

    Attributing an enumeration to a concept means comparing its members against
    a registry value set, which is the literal scan #191 decision 3 rules out.
    So the counts sit beside the verdicts, keyed by path, and this test is what
    stops a later change quietly promoting one to a finding.
    """
    assert set(census.enumerations) == census.read
    for path, found in census.enumerations.items():
        assert all(item.line > 0 for item in found), path


def test_the_console_keeps_its_own_value_arrays_and_the_sdk_keeps_none(census):
    """The two surfaces disagree in a way that changes what paying costs.

    `labels.ts` keeps `as const` arrays, so its debt is replacing a list. The
    SDK's hand-written surface declares no `Literal[...]` at all and types
    these fields as bare strings, so its debt is adding an import to a file
    with nothing to delete. Pinned because it is the fact the seeding rests on,
    and because a walker that silently stopped finding TypeScript arrays would
    otherwise look exactly like a console that had been converted.
    """
    console = [path for path in census.enumerations
               if path.startswith("apps/ui/")]
    assert console, "the console declares a consumer somewhere"
    assert any(census.enumerations[path] for path in console), (
        "the console's declared consumer keeps no enumeration of its own — "
        "either it has been converted, or the TypeScript walker stopped "
        "seeing `as const` arrays")

    sdk = {path: found for path, found in census.enumerations.items()
           if path.startswith("ubb-sdk/")}
    assert sdk, "the registry declares an SDK consumer"
    assert not any(sdk.values()), (
        f"the SDK's hand-written surface has grown an enumeration of its own: "
        f"{ {p: f for p, f in sdk.items() if f} }")


# ---------------------------------------------------------------------------
# Building a synthetic tree
# ---------------------------------------------------------------------------

def _synthetic(tmp_path, *, source, kind="closed", artifacts=(), consumer=None,
               **overrides):
    """A one-concept registry, its generated artifacts, and one consumer.

    The artifacts are RENDERED by the shipped generator rather than typed here,
    so the names the census looks for are the names the artifact actually binds.
    Typing them by hand would make every control pass against a fossil of what
    the generator used to emit.

    ``consumer`` moves the declared consumer to another surface — the surface
    is derived from the path so a control names one thing, not two that could
    disagree. ``artifacts`` names the surfaces to leave un-generated, for the
    control about a missing one.
    """
    path = consumer or CONSUMER_PATH
    body = concept(kind=kind, **overrides)
    body = {key: value for key, value in body.items() if value is not None}
    body["consumers"] = [{"surface": _surface_of(path), "path": path}]
    registry_dir = write_registry(
        tmp_path, concepts={"synthetic.yaml": {"synthetic_concept": body}},
        consumer_files=(path,))
    (tmp_path / path).write_text(source, encoding="utf-8")
    registry = load_registry(registry_dir, tmp_path)
    _write_artifacts(tmp_path, registry, skip=artifacts)
    return take_census(tmp_path, registry)


def _surface_of(path):
    """The surface whose declared root contains this consumer path.

    From the SHIPPED `consumers.yaml`, the same document the compiler reads, so
    a control names one path and cannot state a surface that disagrees with it.
    """
    surfaces = yaml.safe_load(
        (REPO_ROOT / "domain-vocabulary" / "consumers.yaml")
        .read_text(encoding="utf-8"))["surfaces"]
    for name in SURFACES:
        if path.startswith(surfaces[name]["root"].rstrip("/") + "/"):
            return name
    raise AssertionError(
        f"{path} is under no generated surface's declared root")


def _write_artifacts(tmp_path, registry=None, skip=()):
    """Render every surface's generated artifact into the synthetic tree.

    The console's `tsconfig.json` is COPIED from the real one rather than
    typed here, for `_helpers.py`'s stated reason: a control runs against the
    declaration actually in force, so an alias the console changes is felt
    immediately instead of passing against a stale copy.
    """
    for name, generated in SURFACES.items():
        path = tmp_path / generated.target.path
        path.parent.mkdir(parents=True, exist_ok=True)
        if name in skip:
            continue
        path.write_text(
            generated.target.render(registry) if registry is not None else "",
            encoding="utf-8")

    console = SURFACES["console"].target.path.split("/")[:2]
    tsconfig = tmp_path / "/".join(console) / "tsconfig.json"
    tsconfig.parent.mkdir(parents=True, exist_ok=True)
    tsconfig.write_text(
        (REPO_ROOT / "/".join(console) / "tsconfig.json").read_text(
            encoding="utf-8"), encoding="utf-8")


def _parse_extent(found):
    match = _EXTENT.match(found or "")
    return (int(match.group("held")), int(match.group("total"))) if match \
        else None


def test_the_generated_names_come_from_the_generator_not_from_this_test():
    """A guard on the controls above rather than on the gate.

    They import `SYNTHETIC_CONCEPT_VALUES` and `SYNTHETIC_CONCEPT_ALPHA` as
    literals in a source string, which is the one place a name is spelled by
    hand. If the generator's naming rule changed, those strings would stop
    matching and every positive control would silently become a test that the
    census reports a violation — still green, proving nothing.
    """
    synthetic = _Concept("synthetic_concept", ("alpha", "beta"))
    assert BACKEND_CONSTANTS.set_name(synthetic) == "SYNTHETIC_CONCEPT_VALUES"
    assert BACKEND_CONSTANTS.value_name(synthetic, "alpha") == \
        "SYNTHETIC_CONCEPT_ALPHA"
    assert CONSOLE_VOCABULARY.type_name(synthetic) == "SyntheticConcept"


class _Concept:
    """The two attributes the naming methods read. Not a registry concept: the
    point is to ask the generator what it calls things, with nothing else in
    the way."""

    def __init__(self, name, values):
        self.name, self.values, self.known_values = name, values, ()

    @property
    def declared_values(self):
        return self.values
