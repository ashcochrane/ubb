"""The zero-diff gate over every generated vocabulary artifact (#200, #207).

ADR-0008 §3: **a canonical token is authored once; every other appearance is
generated or verified.** This file is the "verified" half for the generated
half — the ratchet that stops a hand edit or a stale generation from rotting
quietly, which is the one the SDK's generated core and its registry-derived
exception hierarchy already ride.

The gate is one comparison: render each target from the shipped registry and
require the committed artifact to be exactly that. Rendering in memory needs no
git, cannot be confused by a dirty working tree, and fails with both texts in
hand. The workflow's `Vocabulary generation gate` step covers what this cannot
— that the command a CONTRIBUTOR runs writes those same bytes, rather than the
renderer being right and the writer wrong.

Consumer source is **not** scanned for matching string literals (#191
decision 3). Each consumer imports its generated artifact, so agreement is
structural: the difference between a check a coincidence can satisfy and one it
cannot. What is checked here is that each artifact MEANS what the registry says
— the names it binds, the values behind them, and the set behind each concept.

How that meaning is read differs by language, and the difference is worth
knowing about. The two Python artifacts are **executed**, so the check is about
what they bind rather than about their text. The console's cannot be executed
here — the contract suite has no TypeScript — so it is read structurally, and
its own toolchain asks the questions this suite cannot: `apps/ui/src/lib/
vocabulary.test.ts` imports it, and `tsc` proves each label map is total over
its concept via `satisfies`.

Every claim carries a negative control, because a gate that has never been
shown to fail is an assertion rather than evidence. Several mutate a copy of
the real registry, so a *positive* control on the untouched copy is here as
well: without it, a broken copy would make every mutation "differ" for the
wrong reason and the controls would pass while proving nothing.
"""

import ast
import json
import re

import pytest

from tools.vocabulary import load_registry
from tools.vocabulary.generate import (
    BACKEND_CONSTANTS,
    CONSOLE_VOCABULARY,
    DIFFERS,
    MISSING,
    SDK_CONSTANTS,
    TARGETS,
    GenerationFailed,
    stale_targets,
    write_targets,
)

from _helpers import (REAL_REGISTRY, REPO_ROOT, concept, copy_real_registry,
                      load, redeclare, write_registry)

#: The targets whose artifact is a Python module, and can therefore be executed
#: rather than read. Named here rather than derived from a base class so that
#: adding a target (#208's spec metadata) has to come through this file and
#: decide which checks apply to it — `test_the_gate_actually_read_the_artifacts`
#: is what makes that unavoidable.
PYTHON_TARGETS = (BACKEND_CONSTANTS, SDK_CONSTANTS)


@pytest.fixture(scope="module")
def registry():
    """The real, shipped registry — the generator's only input."""
    return load_registry(REAL_REGISTRY, REPO_ROOT)


def committed(target):
    return (REPO_ROOT / target.path).read_text(encoding="utf-8")


def namespace(source):
    """Execute a generated Python module and return what it bound.

    Safe precisely because of what `test_the_generated_modules_import_nothing`
    asserts: the artifact is literals and nothing else. Executing it is what
    makes this a check on the module's *meaning* rather than a second
    implementation of the rendering rules, which would only ever agree with
    itself.
    """
    bound = {}
    exec(compile(source, "<generated>", "exec"), bound)  # noqa: S102
    return {name: value for name, value in bound.items()
            if not name.startswith("__")}


# --- reading the console artifact -------------------------------------------
#
# A deliberately DUMB reader: it finds the two literal shapes the artifact emits
# and parses their bodies as JSON, which they are by construction (the renderer
# emits JSON string syntax exactly so that a value carrying a quote cannot
# produce broken TypeScript). It knows nothing about which values belong to
# which concept — that is what the assertions compare against the registry, and
# a reader that knew would only ever agree with the renderer.

_TS_ARRAY = re.compile(
    r"^export const (\w+) = \[\n(.*?)^\] as const;$", re.M | re.S)
_TS_RECORD = re.compile(
    r"^export const (\w+) = \{\n(.*?)^\} as const satisfies Record<(\w+), string>;$",
    re.M | re.S)


def _json_body(body, open_, close):
    """One emitted literal body as the JSON it is, minus its trailing comma."""
    return json.loads(f"{open_}{body.strip().rstrip(',')}{close}")


def console_value_lists(source):
    """``{export name: [value, ...]}`` for every emitted value array."""
    return {name: _json_body(body, "[", "]")
            for name, body in _TS_ARRAY.findall(source)}


def console_label_maps(source):
    """``{export name: ({value: label key}, the type it is total over)}``."""
    return {name: (_json_body(body, "{", "}"), domain)
            for name, body, domain in _TS_RECORD.findall(source)}


def console_strings(source):
    """Every string literal in the artifact, comments removed.

    The comment strip is exact rather than approximate because the renderer
    only ever emits comments at the start of a line — so a "string" found here
    is genuinely a string the console could render.
    """
    code = [line for line in source.splitlines()
            if not line.lstrip().startswith(("//", "/**", "*"))]
    return re.findall(r'"(?:[^"\\]|\\.)*"', "\n".join(code))


# ---------------------------------------------------------------------------
# 1. The gate, and the guard against a vacuous pass
# ---------------------------------------------------------------------------

def test_every_generated_artifact_matches_the_registry(registry):
    """AC: CI regenerates each artifact and fails on any diff.

    The whole gate in one comparison. A hand edit, a stale generation and a
    registry change nobody regenerated all land here, because all three are the
    same fact: the committed bytes are not what the registry produces.
    """
    for target in TARGETS:
        assert committed(target) == target.render(registry), (
            f"{target.path} is not what {REAL_REGISTRY.name}/ produces — "
            f"run `python -m tools.vocabulary --write`"
        )


def test_the_gate_actually_read_the_artifacts(registry):
    """Vacuity guard: a path bug must not turn the comparison above into an
    assertion about two empty strings.

    The targets are named, so one silently dropped from the tuple fails here
    rather than reducing the gate's subject in silence — and a target ADDED
    fails too, which is what makes #208 come through this file and say which of
    the checks below its artifact is subject to.
    """
    assert set(TARGETS) == {BACKEND_CONSTANTS, CONSOLE_VOCABULARY, SDK_CONSTANTS}
    assert BACKEND_CONSTANTS.path == "ubb-platform/core/vocabulary.py"
    assert CONSOLE_VOCABULARY.path == "apps/ui/src/lib/vocabulary.ts"
    assert SDK_CONSTANTS.path == "ubb-sdk/ubb/vocabulary.py"
    for target in TARGETS:
        assert (REPO_ROOT / target.path).is_file(), f"{target.path} is missing"
        assert len(committed(target)) > 500, f"{target.path} is suspiciously small"


def test_stale_targets_reports_nothing_for_the_committed_tree(registry):
    """The same gate, byte-exact, through the function the CLI and CI ask.

    The comparison above is over decoded text, which reads well when it fails
    but folds CRLF into LF — so this is the half that would catch a working
    copy `.gitattributes` should have pinned to LF and did not. Both must pass:
    one for a legible diff, one for the bytes that are actually committed.
    """
    assert stale_targets(registry, REPO_ROOT) == ()


# ---------------------------------------------------------------------------
# 2. Every artifact is marked, sourced, and free of retired words
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.path)
def test_each_artifact_is_marked_generated_and_names_its_source(registry, target):
    """AC: both artifacts are clearly marked as generated and name the registry
    as their source. A reader who arrives by "go to definition" must learn, in
    the first line, that editing here is pointless — and where to edit instead.
    """
    source = target.render(registry)
    head = source.splitlines()[0]

    assert "@generated" in head, f"{target.path} does not announce itself"
    assert "domain-vocabulary/" in head
    assert "python -m tools.vocabulary --write" in source


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.path)
def test_no_artifact_names_a_retired_term(registry, target):
    """A retired word must not land in a file nobody may hand-edit.

    The forbidden-term sweep (#206) reads `retired_aliases` straight from the
    registry, so a retired term appearing in generated source would be a fresh
    sweep hit with no owner and no legal fix — the only way to remove it would
    be to edit the registry. Which is the right answer, and this is what says
    so at the moment the word is introduced rather than at the sweep.
    """
    retired = registry.retired_terms
    assert retired, "no retired terms declared — nothing proven"
    source = target.render(registry)
    for term in retired:
        assert not re.search(rf"\b{re.escape(term)}\b", source), (
            f"{target.path} names the retired term {term!r} — reword the "
            f"concept's summary in {REAL_REGISTRY.name}/"
        )


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.path)
def test_no_artifact_carries_user_facing_english(registry, target):
    """AC: neither generated artifact carries user-facing English.

    Stated precisely, because "no English" cannot mean "no prose at all" — the
    concept summaries are what make these files readable, and they are
    comments. What must not happen is a WORD becoming a value: the moment a
    string in one of these files is something a user could be shown, the
    artifact is a copy deck, and ADR-0008 §4 rules that out for reasons that
    outlive any one wording — translation and capitalisation change far more
    often than the token underneath.

    So the rule is exact: every string literal an artifact emits is a registry
    token or a label key built from one. Prose lives in comments, where nothing
    can render it.
    """
    speakable = _emitted_strings(target, registry)
    assert speakable, f"{target.path}: no strings found — the reader is broken"

    allowed = {value for c in registry.concepts.values()
               for value in c.declared_values}
    allowed |= {f"{c.label_key_prefix}.{value}"
                for c in registry.concepts.values()
                for value in c.declared_values if c.label_key_prefix}

    unexpected = sorted(set(speakable) - allowed)
    assert not unexpected, (
        f"{target.path} emits {len(unexpected)} string(s) that are neither a "
        f"registry value nor a label key, starting with {unexpected[0]!r} — "
        f"vocabulary artifacts carry tokens, never words (ADR-0008 §4)"
    )


def _emitted_strings(target, registry):
    """Every string an artifact emits, by whatever its language allows.

    The module docstring is excluded for the Python targets and the block
    comment for the console: both are documentation for whoever opens the file,
    which is the one place these artifacts are allowed to use sentences.
    """
    source = target.render(registry)
    if target is CONSOLE_VOCABULARY:
        return [json.loads(literal) for literal in console_strings(source)]
    tree = ast.parse(source)
    docstring = tree.body[0].value if ast.get_docstring(tree) else None
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node is not docstring]


# ---------------------------------------------------------------------------
# 3. The Python artifacts mean what the registry says
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target", PYTHON_TARGETS, ids=lambda t: t.path)
def test_the_generated_modules_import_nothing(registry, target):
    """Literals and nothing else.

    Three things ride on it: each module is importable from a migration, a
    settings-free tool or an integrator's own script without dragging anything
    in, it can never take part in an import cycle, and this suite can execute
    it without Django — which is what lets the checks below be about meaning
    rather than text.
    """
    tree = ast.parse(target.render(registry))
    imports = [node for node in ast.walk(tree)
               if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not imports, f"{target.path} imports: {ast.dump(imports[0])}"


@pytest.mark.parametrize("target", PYTHON_TARGETS, ids=lambda t: t.path)
def test_the_generated_modules_bind_every_declared_value(registry, target):
    """The structural half of "the consumer stops holding its own copy".

    Every value UBB itself authored is reachable by name, and the set behind
    the concept is exactly those values — asserted against the registry, so
    this fails if the generator quietly drops one.
    """
    bound = namespace(target.render(registry))
    checked = 0
    for _, concept_ in sorted(registry.concepts.items()):
        if not concept_.declared_values:
            continue
        assert bound[target.set_name(concept_)] == frozenset(concept_.declared_values)
        for value in concept_.declared_values:
            assert bound[target.value_name(concept_, value)] == value
            checked += 1
    assert checked >= 6, f"only {checked} values checked — suspect the registry"


@pytest.mark.parametrize("target", PYTHON_TARGETS, ids=lambda t: t.path)
def test_an_open_concept_names_its_values_known_rather_than_complete(registry,
                                                                    target):
    """ADR-0003, as a naming rule the generator cannot forget.

    `x not in REASON_CODE_VALUES` would read as "reject it", and rejecting a
    value UBB has never seen is exactly what an `open` concept forbids. The
    name says `KNOWN_VALUES` so the wrong reading is not available.
    """
    bound = namespace(target.render(registry))
    open_concepts = registry.of_kind("open")
    assert open_concepts, "no open concept in the registry — nothing proven"
    for concept_ in open_concepts:
        assert f"{concept_.name.upper()}_KNOWN_VALUES" in bound
        assert f"{concept_.name.upper()}_VALUES" not in bound

    for concept_ in registry.of_kind("closed"):
        assert f"{concept_.name.upper()}_VALUES" in bound
        assert f"{concept_.name.upper()}_KNOWN_VALUES" not in bound


def test_the_sdk_module_is_not_the_backend_module_under_another_name(registry):
    """Two homes, one authored source — and each says why it exists.

    The values are identical by design; that is the point of generating both.
    What must differ is the account each gives of itself, because an integrator
    reading the SDK's copy needs ADR-0003's consequence for THEM — an SDK that
    refused an unrecognised value would break on the day UBB adds one — not a
    note about Django migrations.
    """
    backend = namespace(BACKEND_CONSTANTS.render(registry))
    sdk = namespace(SDK_CONSTANTS.render(registry))
    assert backend == sdk, "the two Python artifacts must bind the same values"

    backend_doc = ast.get_docstring(ast.parse(BACKEND_CONSTANTS.render(registry)))
    sdk_doc = ast.get_docstring(ast.parse(SDK_CONSTANTS.render(registry)))
    assert backend_doc and sdk_doc and backend_doc != sdk_doc
    assert "SDK" in sdk_doc


# ---------------------------------------------------------------------------
# 4. The console artifact means what the registry says
# ---------------------------------------------------------------------------

def test_the_console_emits_a_value_list_for_every_valued_concept(registry):
    """AC: the compiler generates canonical value lists into the console.

    Read from the artifact and compared against the registry, including the
    ORDER: a value list is what a filter or a picker iterates, so a set
    comparison would call a reordering current when the console's own output
    moved.
    """
    lists = console_value_lists(CONSOLE_VOCABULARY.render(registry))
    valued = [c for c in registry.concepts.values() if c.declared_values]
    assert len(valued) >= 20, "suspect the registry — too few valued concepts"

    assert set(lists) == {CONSOLE_VOCABULARY.set_name(c) for c in valued}
    for concept_ in valued:
        assert lists[CONSOLE_VOCABULARY.set_name(concept_)] == \
            list(concept_.declared_values)


def test_the_console_emits_a_stable_label_key_for_every_value(registry):
    """AC: the compiler generates the stable label keys into the console.

    A key, never a word. The form is `<label_key_prefix>.<value>`, so a
    catalogue entry can be found from a value and a value recovered from a key
    — which is what makes #210's coverage check possible in both directions.
    """
    maps = console_label_maps(CONSOLE_VOCABULARY.render(registry))
    valued = [c for c in registry.concepts.values() if c.declared_values]

    assert set(maps) == {CONSOLE_VOCABULARY.label_keys_name(c) for c in valued}
    for concept_ in valued:
        keys, _ = maps[CONSOLE_VOCABULARY.label_keys_name(concept_)]
        assert keys == {value: f"{concept_.label_key_prefix}.{value}"
                        for value in concept_.declared_values}


def test_each_console_label_map_is_proved_total_by_the_consoles_own_compiler(
        registry):
    """`satisfies Record<T, string>` is the check, and T is what makes it one.

    For a closed concept T is its type; for an open one it is the KNOWN type,
    never the concept's own — because an open concept's type admits any string,
    and a map declared total over `string` is total over nothing at all. Get
    this wrong and `tsc` stops proving the console labels every value, silently.
    """
    maps = console_label_maps(CONSOLE_VOCABULARY.render(registry))
    for concept_ in registry.concepts.values():
        if not concept_.declared_values:
            continue
        _, domain = maps[CONSOLE_VOCABULARY.label_keys_name(concept_)]
        expected = (CONSOLE_VOCABULARY.known_type_name(concept_)
                    if concept_.kind == "open"
                    else CONSOLE_VOCABULARY.type_name(concept_))
        assert domain == expected, f"{concept_.name}'s label map proves nothing"


def test_the_console_records_that_an_open_concepts_unknown_values_are_legal(
        registry):
    """AC: an open concept emits its known values AND records that unknown
    values are legal.

    In the type, where it binds: the union with `string` is what stops a
    console author writing an exhaustive `switch` that silently drops a value
    UBB has not shipped yet. A closed concept must NOT carry it, or the
    console loses the exhaustiveness checking that is the whole benefit of a
    closed set.
    """
    source = CONSOLE_VOCABULARY.render(registry)
    open_concepts = registry.of_kind("open")
    assert open_concepts, "no open concept in the registry — nothing proven"

    for concept_ in open_concepts:
        name, known = (CONSOLE_VOCABULARY.type_name(concept_),
                       CONSOLE_VOCABULARY.known_type_name(concept_))
        assert f"export type {name} = {known} | (string & {{}});" in source
        assert f"export type {known} = (typeof " in source

    for concept_ in registry.of_kind("closed"):
        name = CONSOLE_VOCABULARY.type_name(concept_)
        assert f"export type {name} = (typeof " in source
        assert f"export type {name} = {name}Known" not in source


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.path)
def test_a_kind_that_declares_no_values_is_accounted_for_not_omitted(registry,
                                                                    target):
    """AC: a tenant-defined concept emits no value list.

    `tenant_defined` and `free_text` carry no values by construction, so they
    contribute no constants to any artifact — map #137 constraint 5, which is
    why no generator may enumerate what the tenant owns. Each artifact still
    NAMES them, because a reader cannot otherwise tell "declares nothing" from
    "the generator lost it", and the second is the failure worth catching.
    """
    source = target.render(registry)
    silent = [c for kind in ("tenant_defined", "free_text")
              for c in registry.of_kind(kind)]
    assert silent, "no valueless concept in the registry — nothing proven"

    emitted = (set(console_value_lists(source)) if target is CONSOLE_VOCABULARY
               else set(namespace(source)))
    for concept_ in silent:
        assert concept_.name in source, f"{concept_.name} is unaccounted for"
        assert not [name for name in emitted
                    if name.startswith(f"{concept_.name.upper()}_")], (
            f"{target.path} enumerates {concept_.name}, which UBB does not own"
        )


# ---------------------------------------------------------------------------
# 5. Negative controls — the gate is shown to fail
# ---------------------------------------------------------------------------

#: The plausible hand edit for each artifact: somebody fixes a value in place
#: instead of fixing the registry. One per language, because the point is that
#: the ratchet holds in all three, not that a Python edit is caught three times.
_HAND_EDITS = {
    BACKEND_CONSTANTS.path: ("'prepaid'", "'pre_paid'"),
    CONSOLE_VOCABULARY.path: ('"prepaid"', '"pre_paid"'),
    SDK_CONSTANTS.path: ("'prepaid'", "'pre_paid'"),
}


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.path)
def test_a_hand_edit_to_a_generated_artifact_is_caught(registry, tmp_path, target):
    """AC: a hand edit to either artifact turns CI red.

    The edit goes through `stale_targets`, the same function CI and the CLI
    ask. Every other artifact is written out unedited, so the one reported is
    the one that was touched rather than every target being trivially absent.
    """
    write_targets(registry, tmp_path)
    old, new = _HAND_EDITS[target.path]
    edited = committed(target).replace(old, new, 1)
    assert edited != committed(target), f"the edit changed nothing in {target.path}"
    # Bytes, and LF: `write_text` would substitute the platform's newline, and
    # the control would then "differ" on Windows whatever the edit did.
    (tmp_path / target.path).write_bytes(edited.encode("utf-8"))

    stale = stale_targets(registry, tmp_path)

    assert [entry.path for entry in stale] == [target.path]
    assert stale[0].reason == DIFFERS


def test_a_missing_artifact_is_caught_as_its_own_reason(registry, tmp_path):
    """Deleting a file must not read as "no differences found" — an absent
    artifact and a wrong one are different faults and a reader should be told
    which one they have."""
    stale = stale_targets(registry, tmp_path)

    assert {entry.path for entry in stale} == {t.path for t in TARGETS}
    assert {entry.reason for entry in stale} == {MISSING}


def test_a_value_added_to_the_registry_without_regenerating_is_caught(tmp_path):
    """AC: adding a value to the registry without regenerating turns CI red for
    BOTH consumers.

    The mutation is on a verbatim copy of the SHIPPED registry, loaded through
    the real entry point, so this is the actual sequence a contributor would
    perform — not a synthetic registry that happens to render differently. That
    every target is named is the acceptance criterion itself: a change to the
    vocabulary reaches the backend, the console and the SDK or it reaches none
    of them.
    """
    copy = copy_real_registry(tmp_path)
    redeclare(copy, "economics.yaml", "customer_billing_mode",
              values=["external", "prepaid", "postpaid", "sponsored"])

    # The committed tree is the real one — only the registry moved. That is
    # precisely the state of a branch where somebody edited the vocabulary and
    # committed without regenerating.
    stale = stale_targets(load_registry(copy, REPO_ROOT), REPO_ROOT)

    assert {entry.path for entry in stale} == {t.path for t in TARGETS}
    assert {entry.reason for entry in stale} == {DIFFERS}


def test_a_value_removed_from_the_registry_without_regenerating_is_caught(tmp_path):
    """The other direction. A shrinking value set is the change most likely to
    be made in the registry alone, because deleting a constant nobody imports
    looks like it costs nothing."""
    copy = copy_real_registry(tmp_path)
    redeclare(copy, "economics.yaml", "customer_billing_mode",
              values=["external", "prepaid"])

    stale = stale_targets(load_registry(copy, REPO_ROOT), REPO_ROOT)

    assert {entry.path for entry in stale} == {t.path for t in TARGETS}


def test_a_reworded_label_key_prefix_is_caught_in_the_console(tmp_path):
    """The console-only change, which must not be able to pass unnoticed.

    A `label_key_prefix` edit moves no value, so the two Python artifacts are
    byte-identical afterwards. If the console's keys were not generated, this
    registry edit would land with CI green and the console's catalogue would
    quietly look up keys nothing emits.
    """
    copy = copy_real_registry(tmp_path)
    redeclare(copy, "economics.yaml", "customer_billing_mode",
              label_key_prefix="settlement_mode")

    stale = stale_targets(load_registry(copy, REPO_ROOT), REPO_ROOT)

    assert [entry.path for entry in stale] == [CONSOLE_VOCABULARY.path]
    assert stale[0].reason == DIFFERS


def test_positive_control_an_untouched_copy_reproduces_the_committed_bytes(tmp_path):
    """The control that gives the ones above their meaning.

    Without it, a copy helper that dropped a file would make every mutation
    "differ" — and every control would pass while proving only that the copy
    was broken.
    """
    copy = copy_real_registry(tmp_path)

    assert stale_targets(load_registry(copy, REPO_ROOT), REPO_ROOT) == ()


def test_writing_the_artifacts_reproduces_the_committed_bytes(registry, tmp_path):
    """The renderer is not the whole tool: a writer that emitted CRLF, or wrote
    to the wrong path, would leave every check above green while a contributor
    running the documented command corrupted the file."""
    written = write_targets(registry, tmp_path)

    assert set(written) == {target.path for target in TARGETS}
    for target in TARGETS:
        on_disk = (tmp_path / target.path).read_bytes()
        assert on_disk == (REPO_ROOT / target.path).read_bytes()
        assert b"\r\n" not in on_disk, f"the writer emitted CRLF into {target.path}"
    assert stale_targets(registry, tmp_path) == ()


def test_a_surface_that_cannot_render_leaves_every_artifact_untouched(tmp_path):
    """No half-regenerated working tree.

    A label-key collision is renderable by the backend and refused by the
    console, and the console is not first in `TARGETS` — so a writer that
    emitted as it went would rewrite the backend module, hit the refusal, and
    exit non-zero having already changed a file the contributor did not ask it
    to change. The two-artifact case could not show this; the three-artifact
    one can, which is why the control arrives with the surfaces that made it
    reachable.
    """
    registry = load(tmp_path, concepts={"economics.yaml": {
        "first_concept": concept(values=["shared"], label_key_prefix="same"),
        "second_concept": concept(values=["shared"], label_key_prefix="same"),
    }})

    with pytest.raises(GenerationFailed):
        write_targets(registry, tmp_path)

    for target in TARGETS:
        assert not (tmp_path / target.path).exists(), (
            f"{target.path} was written before a later surface refused"
        )


def test_writing_an_unchanged_artifact_reports_no_change(registry, tmp_path):
    """`--write` names what it changed, so running it twice must not claim a
    second rewrite — the report is what a contributor reads to decide whether
    a commit is needed."""
    write_targets(registry, tmp_path)

    assert write_targets(registry, tmp_path) == ()


# ---------------------------------------------------------------------------
# 6. The generators refuse what they cannot render honestly
# ---------------------------------------------------------------------------

def test_two_concepts_whose_constants_would_collide_are_refused(tmp_path):
    """`billing_mode` + `is_x` and `billing` + `mode_is_x` both want
    `BILLING_MODE_IS_X`. Emitting it once would silently give one concept the
    other's value; emitting it twice would let the second assignment win.

    Neither is a diff anybody would notice, so the Python generators refuse.

    **The console does not, and must not.** It binds no per-value constant, so
    on this registry its names are `BILLING_MODE_VALUES` and `BILLING_VALUES`
    and nothing collides. That asymmetry is the whole reason `GenerationFailed`
    is separate from a registry error: the fault is in what one surface can
    express, and telling the console its registry is broken would be false.
    """
    registry = load(tmp_path, concepts={"economics.yaml": {
        "billing_mode": concept(values=["is_x"], label_key_prefix="one"),
        "billing": concept(values=["mode_is_x"], label_key_prefix="two"),
    }})

    for target in PYTHON_TARGETS:
        with pytest.raises(GenerationFailed) as raised:
            target.render(registry)
        assert "BILLING_MODE_IS_X" in str(raised.value)

    console = console_value_lists(CONSOLE_VOCABULARY.render(registry))
    assert set(console) == {"BILLING_MODE_VALUES", "BILLING_VALUES"}


def test_two_concepts_whose_label_keys_would_collide_are_refused(tmp_path):
    """A console-only fault, and the reason the console checks its own claims.

    `label_key_prefix` is free to repeat as far as the compiler is concerned —
    nothing in the registry flattens the keys into one namespace. The console's
    catalogue does. Two concepts sharing a prefix AND a value would file one
    concept's wording under the other's key, and #210's coverage check would
    then be green about a label that is wrong.

    The Python targets are unaffected, and asserting that is the point: this
    proves the collision check is per-surface rather than a registry rule in
    the wrong place.
    """
    registry = load(tmp_path, concepts={"economics.yaml": {
        "first_concept": concept(values=["shared"], label_key_prefix="same"),
        "second_concept": concept(values=["shared"], label_key_prefix="same"),
    }})

    with pytest.raises(GenerationFailed) as raised:
        CONSOLE_VOCABULARY.render(registry)
    assert "same.shared" in str(raised.value)

    for target in PYTHON_TARGETS:
        target.render(registry)


def test_two_concepts_whose_type_names_would_collide_are_refused(tmp_path):
    """The console's OTHER namespace, checked separately from its constants.

    `foo_1bar` and `foo1bar` give distinct constant names (`FOO_1BAR_VALUES`
    and `FOO1BAR_VALUES`) and the same type name — so a check that only looked
    at constants would emit two `export type Foo1bar`, and TypeScript would
    reject the artifact after it was committed rather than before.
    """
    registry = load(tmp_path, concepts={"economics.yaml": {
        "foo_1bar": concept(values=["a"], label_key_prefix="one"),
        "foo1bar": concept(values=["b"], label_key_prefix="two"),
    }})

    with pytest.raises(GenerationFailed) as raised:
        CONSOLE_VOCABULARY.render(registry)
    assert "Foo1bar" in str(raised.value)

    for target in PYTHON_TARGETS:
        target.render(registry)


def test_a_structured_value_becomes_a_valid_name_in_every_language(tmp_path):
    """The webhook catalogue's `<owner>.<past-tense state entered>` names
    (ADR-0006 §5). `TASK.COMPLETED` is not a Python identifier, and a dotted
    key is not a bare TypeScript one — so each surface has to say the value in
    a form its own language accepts, without losing the value itself."""
    registry = load(tmp_path, concepts={"economics.yaml": {"webhook_event": concept(
        token_pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
        values=["task.completed", "invoice.finalized"],
        label_key_prefix="webhook_event",
    )}})

    for target in PYTHON_TARGETS:
        bound = namespace(target.render(registry))
        assert bound["WEBHOOK_EVENT_TASK_COMPLETED"] == "task.completed"
        assert bound["WEBHOOK_EVENT_INVOICE_FINALIZED"] == "invoice.finalized"

    source = CONSOLE_VOCABULARY.render(registry)
    assert console_value_lists(source)["WEBHOOK_EVENT_VALUES"] == \
        ["task.completed", "invoice.finalized"]
    keys, _ = console_label_maps(source)["WEBHOOK_EVENT_LABEL_KEYS"]
    assert keys["task.completed"] == "webhook_event.task.completed"


def test_a_value_that_needs_escaping_is_emitted_correctly(tmp_path):
    """A concept may override `token_pattern` with any regular expression, so a
    value carrying a quote or a backslash is one the compiler accepts.

    Interpolating it into a quoted literal would emit source that is broken —
    or, for the backslash, valid and quietly wrong. Checked in both languages,
    because they escape by different rules and only one of them was ever tested.
    """
    registry = load(tmp_path, concepts={"economics.yaml": {"quoted": concept(
        token_pattern=r"^[a-z'\\]+$",
        values=["it's", "back\\slash"],
    )}})

    for target in PYTHON_TARGETS:
        bound = namespace(target.render(registry))
        assert bound["QUOTED_IT_S"] == "it's"
        assert bound["QUOTED_BACK_SLASH"] == "back\\slash"

    # Read back through JSON, which is what the console's parser will do too:
    # a mis-escaped backslash survives a naive string comparison and does not
    # survive this.
    assert console_value_lists(CONSOLE_VOCABULARY.render(registry))["QUOTED_VALUES"] \
        == ["it's", "back\\slash"]


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.path)
def test_the_renderers_are_stable_across_runs(registry, target):
    """A zero-diff gate over a renderer with any iteration-order dependence
    would fail at random, which is the fastest way to get a gate disabled."""
    assert target.render(registry) == target.render(registry)


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.path)
def test_concepts_are_emitted_in_a_stable_order_not_file_order(registry, target):
    """Sorted by name in every artifact, so moving a concept between domain
    files is not also a diff in three generated files at once."""
    source = target.render(registry)
    positions = [source.index(f"--- {name} ") for name in sorted(registry.concepts)]
    assert positions == sorted(positions)


# ---------------------------------------------------------------------------
# 7. The CLI reaches the same verdict a human can run
# ---------------------------------------------------------------------------

def test_the_cli_reports_a_stale_artifact_and_exits_nonzero(tmp_path, capsys):
    """A contributor who edits the registry and commits must be told by the
    same command that told them the registry is valid — not by CI."""
    from tools.vocabulary.__main__ import main

    registry_dir = write_registry(tmp_path, concepts={
        "economics.yaml": {"thing": concept()},
    })
    status = main(["--registry", str(registry_dir), "--repo-root", str(tmp_path)])

    assert status == 1
    error = capsys.readouterr().err
    for target in TARGETS:
        assert target.path in error
    assert "--write" in error


def test_the_cli_writes_the_artifacts_and_then_reports_them_current(tmp_path, capsys):
    from tools.vocabulary.__main__ import main

    registry_dir = write_registry(tmp_path, concepts={
        "economics.yaml": {"thing": concept()},
    })
    written = main(["--registry", str(registry_dir), "--repo-root", str(tmp_path),
                    "--write"])
    capsys.readouterr()

    assert written == 0
    for target in TARGETS:
        assert (tmp_path / target.path).is_file()
    assert main(["--registry", str(registry_dir), "--repo-root", str(tmp_path)]) == 0
    assert f"generated artifacts: {len(TARGETS)} up to date" in capsys.readouterr().out


def test_the_cli_reports_an_unrenderable_registry_rather_than_crashing(tmp_path,
                                                                      capsys):
    """A valid registry no artifact can be rendered from is still a fault the
    tool names, not a traceback out of the generator.

    And it must not be reported as an INVALID registry, which would be false:
    the registry passed every rule it declares, and the author would go looking
    for a registry error that is not there. Both `--write` and the plain check
    reach the generator, so both are covered.
    """
    from tools.vocabulary.__main__ import main

    registry_dir = write_registry(tmp_path, concepts={"economics.yaml": {
        "billing_mode": concept(values=["is_x"], label_key_prefix="one"),
        "billing": concept(values=["mode_is_x"], label_key_prefix="two"),
    }})
    argv = ["--registry", str(registry_dir), "--repo-root", str(tmp_path)]

    for extra in ([], ["--write"]):
        assert main(argv + extra) == 1
        error = capsys.readouterr().err
        assert "BILLING_MODE_IS_X" in error
        assert "INVALID" not in error
    for target in TARGETS:
        assert not (tmp_path / target.path).exists()


def test_the_cli_does_not_write_when_the_registry_is_invalid(tmp_path, capsys):
    """An invalid registry has no verdict to emit. Writing from one would
    replace a correct artifact with whatever a half-broken registry rendered —
    the failure mode a generator gets exactly one chance to avoid."""
    from tools.vocabulary.__main__ import main

    registry_dir = write_registry(tmp_path, concepts={
        "economics.yaml": {"thing": concept(kind="mostly_closed")},
    })
    status = main(["--registry", str(registry_dir), "--repo-root", str(tmp_path),
                   "--write"])

    assert status == 1
    for target in TARGETS:
        assert not (tmp_path / target.path).exists()
