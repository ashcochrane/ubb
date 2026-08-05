"""The zero-diff gate over every generated vocabulary artifact (issue #200).

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

Backend modules are **not** scanned for matching string literals (#191
decision 3). They import the generated module, so agreement is structural: the
difference between a check a coincidence can satisfy and one it cannot. What is
checked here is that the generated module means what the registry says — the
names it binds, the values behind them, and the set behind each concept — by
executing it, not by matching its text against a second copy of the rendering
rules.

Every claim carries a negative control, because a gate that has never been
shown to fail is an assertion rather than evidence. Two of them mutate a copy
of the real registry, so a *positive* control on the untouched copy is here as
well: without it, a broken copy would make both mutations "differ" for the
wrong reason and the controls would pass while proving nothing.
"""

import ast
import re

import pytest

from tools.vocabulary import load_registry
from tools.vocabulary.generate import (
    BACKEND_CONSTANTS,
    DIFFERS,
    MISSING,
    TARGETS,
    GenerationFailed,
    stale_targets,
    write_targets,
)

from _helpers import (REAL_REGISTRY, REPO_ROOT, concept, copy_real_registry,
                      load, redeclare, write_registry)


@pytest.fixture(scope="module")
def registry():
    """The real, shipped registry — the generator's only input."""
    return load_registry(REAL_REGISTRY, REPO_ROOT)


def committed(target):
    return (REPO_ROOT / target.path).read_text(encoding="utf-8")


def namespace(source):
    """Execute a generated module and return what it bound.

    Safe precisely because of what `test_the_generated_module_imports_nothing`
    asserts: the artifact is literals and nothing else. Executing it is what
    makes this a check on the module's *meaning* rather than a second
    implementation of the rendering rules, which would only ever agree with
    itself.
    """
    bound = {}
    exec(compile(source, "<generated>", "exec"), bound)  # noqa: S102
    return {name: value for name, value in bound.items()
            if not name.startswith("__")}


# ---------------------------------------------------------------------------
# 1. The gate, and the guard against a vacuous pass
# ---------------------------------------------------------------------------

def test_every_generated_artifact_matches_the_registry(registry):
    """AC: CI regenerates the module and fails on any diff.

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
    assertion about two empty strings."""
    assert TARGETS, "no generated targets — the gate would pass on nothing"
    for target in TARGETS:
        assert (REPO_ROOT / target.path).is_file(), f"{target.path} is missing"
        assert len(committed(target)) > 500, f"{target.path} is suspiciously small"
    # Named, so a target silently dropped from the tuple fails here rather than
    # reducing the gate's subject in silence.
    assert BACKEND_CONSTANTS in TARGETS
    assert BACKEND_CONSTANTS.path == "ubb-platform/core/vocabulary.py"


def test_stale_targets_reports_nothing_for_the_committed_tree(registry):
    """The same gate, byte-exact, through the function the CLI and CI ask.

    The comparison above is over decoded text, which reads well when it fails
    but folds CRLF into LF — so this is the half that would catch a working
    copy `.gitattributes` should have pinned to LF and did not. Both must pass:
    one for a legible diff, one for the bytes that are actually committed.
    """
    assert stale_targets(registry, REPO_ROOT) == ()


# ---------------------------------------------------------------------------
# 2. The generated module means what the registry says
# ---------------------------------------------------------------------------

def test_the_generated_module_imports_nothing(registry):
    """Literals and nothing else.

    Three things ride on it: the module is importable from a migration or a
    settings-free tool without dragging anything in, it can never take part in
    an import cycle, and the contract suite can execute it without Django —
    which is what lets the checks below be about meaning rather than text.
    """
    tree = ast.parse(BACKEND_CONSTANTS.render(registry))
    imports = [node for node in ast.walk(tree)
               if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not imports, f"generated module imports: {ast.dump(imports[0])}"


def test_the_generated_module_binds_every_declared_value(registry):
    """The structural half of "the backend stops holding its own copy".

    Every value UBB itself authored is reachable by name, and the set behind
    the concept is exactly those values — asserted against the registry, so
    this fails if the generator quietly drops one.
    """
    bound = namespace(BACKEND_CONSTANTS.render(registry))
    checked = 0
    for name, concept_ in sorted(registry.concepts.items()):
        if not concept_.declared_values:
            continue
        set_name = BACKEND_CONSTANTS.set_name(concept_)
        assert bound[set_name] == frozenset(concept_.declared_values)
        for value in concept_.declared_values:
            assert bound[BACKEND_CONSTANTS.value_name(concept_, value)] == value
            checked += 1
    assert checked >= 6, f"only {checked} values checked — suspect the registry"


def test_an_open_concept_names_its_values_known_rather_than_complete(registry):
    """ADR-0003, as a naming rule the generator cannot forget.

    `x not in REASON_CODE_VALUES` would read as "reject it", and rejecting a
    value UBB has never seen is exactly what an `open` concept forbids. The
    name says `KNOWN_VALUES` so the wrong reading is not available.
    """
    bound = namespace(BACKEND_CONSTANTS.render(registry))
    open_concepts = registry.of_kind("open")
    assert open_concepts, "no open concept in the registry — nothing proven"
    for concept_ in open_concepts:
        assert f"{concept_.name.upper()}_KNOWN_VALUES" in bound
        assert f"{concept_.name.upper()}_VALUES" not in bound

    for concept_ in registry.of_kind("closed"):
        assert f"{concept_.name.upper()}_VALUES" in bound
        assert f"{concept_.name.upper()}_KNOWN_VALUES" not in bound


def test_a_kind_that_declares_no_values_is_accounted_for_not_omitted(registry):
    """`tenant_defined` and `free_text` carry no values by construction, so
    they contribute no constants. The module still names them, because a
    reader cannot otherwise tell "declares nothing" from "the generator lost
    it" — and the second is the failure worth catching."""
    source = BACKEND_CONSTANTS.render(registry)
    silent = [c for kind in ("tenant_defined", "free_text")
              for c in registry.of_kind(kind)]
    assert silent, "no valueless concept in the registry — nothing proven"
    for concept_ in silent:
        assert concept_.name in source, f"{concept_.name} is unaccounted for"


def test_the_module_is_marked_generated_and_names_its_source(registry):
    """AC: the generated module is clearly marked as generated and names the
    registry as its source. A reader who arrives by "go to definition" must
    learn, in the first line, that editing here is pointless."""
    head = BACKEND_CONSTANTS.render(registry).splitlines()[0]
    assert head.startswith("# @generated")
    assert "domain-vocabulary/" in head
    assert "python -m tools.vocabulary --write" in BACKEND_CONSTANTS.render(registry)


def test_the_generated_module_names_no_retired_term(registry):
    """A retired word must not land in a file nobody may hand-edit.

    The forbidden-term sweep (#206) reads `retired_aliases` straight from the
    registry, so a retired term appearing in generated backend source would be
    a fresh sweep hit with no owner and no legal fix — the only way to remove
    it would be to edit the registry. Which is the right answer, and this is
    what says so at the moment the word is introduced rather than at #206.
    """
    retired = registry.retired_terms
    assert retired, "no retired terms declared — nothing proven"
    source = BACKEND_CONSTANTS.render(registry)
    for term in retired:
        assert not re.search(rf"\b{re.escape(term)}\b", source), (
            f"the generated module names the retired term {term!r} — reword "
            f"the concept's summary in {REAL_REGISTRY.name}/"
        )


# ---------------------------------------------------------------------------
# 3. Negative controls — the gate is shown to fail
# ---------------------------------------------------------------------------

def test_a_hand_edit_to_a_generated_artifact_is_caught(registry, tmp_path):
    """AC: a hand edit to the generated module turns CI red.

    The edit is the plausible one — somebody fixes a value in place instead of
    fixing the registry — and it goes through `stale_targets`, the same
    function CI and the CLI ask.
    """
    edited = committed(BACKEND_CONSTANTS).replace("'prepaid'", "'pre_paid'", 1)
    assert edited != committed(BACKEND_CONSTANTS), "the edit changed nothing"
    (tmp_path / BACKEND_CONSTANTS.path).parent.mkdir(parents=True, exist_ok=True)
    # Bytes, and LF: `write_text` would substitute the platform's newline, and
    # the control would then "differ" on Windows whatever the edit did.
    (tmp_path / BACKEND_CONSTANTS.path).write_bytes(edited.encode("utf-8"))

    stale = stale_targets(registry, tmp_path)

    assert [entry.path for entry in stale] == [BACKEND_CONSTANTS.path]
    assert stale[0].reason == DIFFERS


def test_a_missing_artifact_is_caught_as_its_own_reason(registry, tmp_path):
    """Deleting the file must not read as "no differences found" — an absent
    artifact and a wrong one are different faults and a reader should be told
    which one they have."""
    stale = stale_targets(registry, tmp_path)

    assert [entry.path for entry in stale] == [BACKEND_CONSTANTS.path]
    assert stale[0].reason == MISSING


def test_a_value_added_to_the_registry_without_regenerating_is_caught(tmp_path):
    """AC: adding a value to the registry without regenerating turns CI red.

    The mutation is on a verbatim copy of the SHIPPED registry, loaded through
    the real entry point, so this is the actual sequence a contributor would
    perform — not a synthetic registry that happens to render differently.
    """
    copy = copy_real_registry(tmp_path)
    redeclare(copy, "economics.yaml", "customer_billing_mode",
              values=["external", "prepaid", "postpaid", "sponsored"])

    # The committed tree is the real one — only the registry moved. That is
    # precisely the state of a branch where somebody edited the vocabulary and
    # committed without regenerating.
    stale = stale_targets(load_registry(copy, REPO_ROOT), REPO_ROOT)

    assert [entry.path for entry in stale] == [BACKEND_CONSTANTS.path]
    assert stale[0].reason == DIFFERS


def test_a_value_removed_from_the_registry_without_regenerating_is_caught(tmp_path):
    """The other direction. A shrinking value set is the change most likely to
    be made in the registry alone, because deleting a constant nobody imports
    looks like it costs nothing."""
    copy = copy_real_registry(tmp_path)
    redeclare(copy, "economics.yaml", "customer_billing_mode",
              values=["external", "prepaid"])

    stale = stale_targets(load_registry(copy, REPO_ROOT), REPO_ROOT)

    assert [entry.path for entry in stale] == [BACKEND_CONSTANTS.path]


def test_positive_control_an_untouched_copy_reproduces_the_committed_bytes(tmp_path):
    """The control that gives the two above their meaning.

    Without it, a copy helper that dropped a file would make every mutation
    "differ" — and both controls would pass while proving only that the copy
    was broken.
    """
    copy = copy_real_registry(tmp_path)

    assert stale_targets(load_registry(copy, REPO_ROOT), REPO_ROOT) == ()


def test_writing_the_artifacts_reproduces_the_committed_bytes(registry, tmp_path):
    """The renderer is not the whole tool: a writer that emitted CRLF, or wrote
    to the wrong path, would leave every check above green while a contributor
    running the documented command corrupted the file."""
    written = write_targets(registry, tmp_path)

    assert [entry for entry in written] == [BACKEND_CONSTANTS.path]
    on_disk = (tmp_path / BACKEND_CONSTANTS.path).read_bytes()
    assert on_disk == (REPO_ROOT / BACKEND_CONSTANTS.path).read_bytes()
    assert b"\r\n" not in on_disk, "the writer emitted CRLF"
    assert stale_targets(registry, tmp_path) == ()


def test_writing_an_unchanged_artifact_reports_no_change(registry, tmp_path):
    """`--write` names what it changed, so running it twice must not claim a
    second rewrite — the report is what a contributor reads to decide whether
    a commit is needed."""
    write_targets(registry, tmp_path)

    assert write_targets(registry, tmp_path) == ()


# ---------------------------------------------------------------------------
# 4. The generator refuses what it cannot render honestly
# ---------------------------------------------------------------------------

def test_two_concepts_whose_constants_would_collide_are_refused(tmp_path):
    """`billing_mode` + `is_x` and `billing` + `mode_is_x` both want
    `BILLING_MODE_IS_X`. Emitting it once would silently give one concept the
    other's value; emitting it twice would let the second assignment win.

    Neither is a diff anybody would notice, so the generator refuses instead.
    """
    registry = load(tmp_path, concepts={"economics.yaml": {
        "billing_mode": concept(values=["is_x"], label_key_prefix="one"),
        "billing": concept(values=["mode_is_x"], label_key_prefix="two"),
    }})

    with pytest.raises(GenerationFailed) as raised:
        BACKEND_CONSTANTS.render(registry)
    assert "BILLING_MODE_IS_X" in str(raised.value)


def test_a_structured_value_becomes_a_valid_python_name(tmp_path):
    """The webhook catalogue's `<owner>.<past-tense>` names arrive with #202
    (the compiler already admits them). `TASK.COMPLETED` is not an identifier,
    so the generator must not emit it — and must not wait until #202 to find
    out."""
    registry = load(tmp_path, concepts={"economics.yaml": {"webhook_event": concept(
        token_pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
        values=["task.completed", "invoice.finalized"],
    )}})

    bound = namespace(BACKEND_CONSTANTS.render(registry))

    assert bound["WEBHOOK_EVENT_TASK_COMPLETED"] == "task.completed"
    assert bound["WEBHOOK_EVENT_INVOICE_FINALIZED"] == "invoice.finalized"


def test_a_value_that_needs_escaping_is_emitted_correctly(tmp_path):
    """A concept may override `token_pattern` with any regular expression, so a
    value carrying a quote or a backslash is one the compiler accepts.

    Interpolating it into a quoted literal would emit Python that is broken —
    or, for the backslash, valid and quietly wrong.
    """
    registry = load(tmp_path, concepts={"economics.yaml": {"quoted": concept(
        token_pattern=r"^[a-z'\\]+$",
        values=["it's", "back\\slash"],
    )}})

    bound = namespace(BACKEND_CONSTANTS.render(registry))

    assert bound["QUOTED_IT_S"] == "it's"
    assert bound["QUOTED_BACK_SLASH"] == "back\\slash"


def test_the_renderer_is_stable_across_runs(registry):
    """A zero-diff gate over a renderer with any iteration-order dependence
    would fail at random, which is the fastest way to get a gate disabled."""
    assert BACKEND_CONSTANTS.render(registry) == BACKEND_CONSTANTS.render(registry)


def test_concepts_are_emitted_in_a_stable_order_not_file_order(registry):
    """Sorted by name, so moving a concept between domain files — which #202
    will do — is not also a diff in every generated artifact."""
    source = BACKEND_CONSTANTS.render(registry)
    positions = [source.index(f"# --- {name} ") for name in sorted(registry.concepts)]
    assert positions == sorted(positions)


# ---------------------------------------------------------------------------
# 5. The CLI reaches the same verdict a human can run
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
    assert BACKEND_CONSTANTS.path in error
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
    assert (tmp_path / BACKEND_CONSTANTS.path).is_file()
    assert main(["--registry", str(registry_dir), "--repo-root", str(tmp_path)]) == 0
    assert "generated artifacts: 1 up to date" in capsys.readouterr().out


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
    assert not (tmp_path / BACKEND_CONSTANTS.path).exists()


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
    assert not (tmp_path / BACKEND_CONSTANTS.path).exists()
