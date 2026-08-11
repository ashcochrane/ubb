"""G7 — the forbidden-term sweep, with declared and counted exclusions (#206).

The workhorse gate (#154 §12): a retired word cannot re-enter on any surface
once the slice that removed it has landed. Its oracle is the registry's
`retired_aliases`, which #198 and #202 made data rather than a list somebody
maintains by memory; its declared plan is `gates/forbidden-term-sweep.yaml`.

The gate has three halves, and they fail differently on purpose.

**Did it read everything?** Total accounting: every tracked file is swept or
matched by exactly one declared rule. This is the half that catches a sweep
that stopped reading a surface — counting exclusions alone would not.

**Are the exclusions still what they claim?** Each rule's file count is pinned,
no rule is inert, no rule overlaps another, no rule covers an anchor, and the one
rule that ends names the slice that deletes it. #154 §14: *"an over-broad
exclusion silently disarms it."*

**What did it find?** Every retired word on a living surface is owed by a ledger
entry naming the slice that removes it, in no more files than that entry
records — and an entry whose word has left is a failure too, because paying a
debt and deleting its entry are one act.

Every negative control drives the REAL walker over a synthetic tree. Nothing
here patches the sweep's internals: a test that mocks the thing under test can
only reproduce its mistakes, which is how three SDK methods called routes that
existed nowhere and stayed green for months.

This module is itself excluded from the sweep, by name, in
`checks-whose-subject-is-a-retired-word` — it plants retired words on purpose.
"""

import subprocess

import pytest
import yaml

from _helpers import REPO_ROOT, concept, load
from tools.forbidden_terms import errors as codes
from tools.forbidden_terms.plan import (
    PLAN_PATH,
    UNTIL_SLICE_8,
    Area,
    ExclusionRule,
    Plan,
    load_plan,
)
from tools.forbidden_terms.sweep import (
    excused, gate_faults, run, tracked_files, unaccounted,
)
from tools.gates import load_programme
from tools.vocabulary import load_registry

GATE = "G7"


# ---------------------------------------------------------------------------
# The real repository, swept once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry():
    return load_registry(REPO_ROOT / "domain-vocabulary", REPO_ROOT)


@pytest.fixture(scope="module")
def programme():
    return load_programme(REPO_ROOT / "gates", REPO_ROOT)


@pytest.fixture(scope="module")
def plan(registry, programme):
    loaded, faults = load_plan(REPO_ROOT, registry.surfaces, programme.slices)
    assert not faults, (
        "the sweep's declared plan is invalid, so nothing below means "
        "anything:\n" + "\n".join(f"  {fault}" for fault in faults))
    return loaded


@pytest.fixture(scope="module")
def result(registry, plan):
    return run(REPO_ROOT, registry, plan)


@pytest.fixture(scope="module")
def entries(programme):
    return tuple(entry for entry in programme.entries if entry.gate == GATE)


# ---------------------------------------------------------------------------
# 1. Did it read everything?
# ---------------------------------------------------------------------------

def _git_listing():
    """The tree according to git, NOT according to the sweep.

    Deliberately a raw subprocess rather than `tracked_files`: the accounting
    below is only a real question if the listing it compares against comes from
    somewhere the sweep does not control. Compare the walker's own input with
    its own output and it passes by construction.
    """
    listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
                            capture_output=True, text=True, check=True)
    return tuple(sorted(p for p in listed.stdout.split("\0") if p))


def test_every_tracked_file_is_swept_or_excluded_by_exactly_one_rule(result):
    """The total accounting. There is no third category.

    A file that is neither swept nor excused is the shape of a surface quietly
    dropped from the walk — the failure that counting exclusions cannot see,
    because a sweep that stopped reading `ubb-sdk/` widens no rule at all.
    """
    faults = unaccounted(_git_listing(), result.swept, result.excluded)
    assert not faults, (
        f"{len(faults)} file(s) the tree reports and the sweep did not account "
        f"for:\n" + "\n".join(f"  {fault}" for fault in faults[:5]))


def test_negative_control_a_file_the_walk_missed_fails(result):
    """The accounting must be shown to fail, or it is an assertion not evidence.

    A file git reports and the sweep never classified: exactly what a narrowed
    walk would leave behind.
    """
    listing = _git_listing() + ("ubb-sdk/ubb/a_module_the_walk_skipped.py",)
    faults = unaccounted(listing, result.swept, result.excluded)
    assert _codes(faults) == {codes.UNACCOUNTED_FILE}
    assert "a_module_the_walk_skipped" in faults[0].location


def test_the_sweeps_own_listing_agrees_with_git(result):
    """And the other half: `tracked_files` itself is what git says.

    Without this, narrowing the walk inside `tracked_files` would narrow the
    check above with it, and both would stay green.
    """
    tracked, problem = tracked_files(REPO_ROOT)
    assert problem is None, problem
    assert set(tracked) == set(_git_listing())


def test_no_file_is_excused_by_two_rules_at_once(result):
    overlaps = [f for f in result.faults if f.code == codes.RULE_OVERLAP]
    assert not overlaps, "\n".join(str(fault) for fault in overlaps)


def test_the_sweep_read_a_substantial_tree(result):
    """A vacuity guard on the walk itself.

    Not a pinned number — that would fail on every file added — but a floor far
    below today's count and far above what a broken path resolution returns.
    """
    assert len(result.swept) > 1000, (
        f"the sweep read only {len(result.swept)} files. A repository this "
        f"size does not have that few, so the walk resolved the wrong root.")


def test_every_declared_anchor_was_actually_read(plan, result):
    """#191 story 20: a path-resolution bug must not make this always pass."""
    unread = sorted(set(plan.anchors) - set(result.swept))
    assert not unread, (
        f"declared anchors were not swept: {unread}. The sweep did not read a "
        f"surface it claims to cover.")


def test_every_area_carries_an_anchor(plan, result):
    """What stops a new area arriving unguarded — the way the check above rots."""
    faults = [f for f in result.faults if f.code == codes.AREA_UNANCHORED]
    assert not faults, "\n".join(str(fault) for fault in faults)


def test_every_swept_file_decoded(result):
    """A file the sweep cannot read is a file a retired word can hide in.

    So an undecodable file is a fault, never a skip. It is either declared in an
    exclusion rule, with a reason, or it fails here.
    """
    faults = [f for f in result.faults if f.code == codes.FILE_UNDECODABLE]
    assert not faults, "\n".join(str(fault) for fault in faults)


# ---------------------------------------------------------------------------
# 2. Are the exclusions exactly what they claim?
# ---------------------------------------------------------------------------

def test_each_rule_excludes_exactly_the_number_of_files_it_declares(result):
    """The anti-widening mechanism. A glob that grew changes the number."""
    faults = [f for f in result.faults if f.code == codes.RULE_COUNT_WRONG]
    assert not faults, "\n".join(str(fault) for fault in faults)


def test_no_exclusion_rule_is_inert(result):
    """An exclusion that excludes nothing is a check that cannot fail."""
    faults = [f for f in result.faults if f.code == codes.RULE_INERT]
    assert not faults, "\n".join(str(fault) for fault in faults)


def test_no_exclusion_rule_covers_an_anchor(result):
    faults = [f for f in result.faults if f.code == codes.RULE_HIDES_ANCHOR]
    assert not faults, "\n".join(str(fault) for fault in faults)


def test_the_declared_exclusion_set_is_exactly_what_the_file_says(plan):
    """The exclusion list cannot quietly widen, in the strongest available form.

    The rules that ship, their permanence and their counts, pinned as literals.
    A new rule, a widened one, or one that quietly became permanent all fail
    here rather than being noticed by a reader of a large diff.
    """
    declared = {rule.id: (rule.permanence, rule.files, len(rule.paths))
                for rule in plan.exclusions}
    assert declared == {
        "frozen-dated-documents": ("permanent", 121, 5),
        "historical-migrations": (UNTIL_SLICE_8, 197, 19),
        "vendored-dependency-manifests": ("permanent", 2, 2),
        "the-vocabulary-registry": ("permanent", 10, 1),
        "the-gate-bookkeeping": ("permanent", 7, 1),
        "checks-whose-subject-is-a-retired-word": ("permanent", 14, 14),
    }


def test_the_frozen_document_exclusion_is_permanent(plan):
    """Dated documents are evidence of what was decided, not current truth.

    Editing one to remove a word it correctly used would falsify the record to
    satisfy a gate, so this rule has no end date and must not acquire one.
    """
    rule = _rule(plan, "frozen-dated-documents")
    assert rule.is_permanent
    assert all(pattern.endswith("/**") for pattern in rule.paths)
    for directory in ("docs/plans/", "docs/reviews/"):
        assert any(pattern.startswith(directory) for pattern in rule.paths), (
            f"{directory} is the category CLAUDE.md calls frozen history")


def test_the_migration_exclusion_names_slice_8_as_its_end(plan, programme):
    """#155 §5.4: the cutover squash DELETES the category rather than excusing it.

    So the rule carries the slice that deletes it, and the reason a reader sees
    carries it too. An exclusion with no stated end is how one outlives its
    reason.
    """
    rule = _rule(plan, "historical-migrations")
    assert rule.permanence == UNTIL_SLICE_8
    assert "slice_8" in rule.reason
    assert "slice_8" in programme.slices, (
        "the exclusion's end date names a slice the programme does not declare")
    assert not programme.slices["slice_8"].landed, (
        "slice 8 has landed, so the historical-migration exclusion is due for "
        "deletion rather than renewal")


def test_no_rule_reaches_outside_the_two_declared_shapes(plan):
    """An exact tracked path, or a `dir/**` prefix. That is the whole language.

    Enforced at load, asserted here so the property is visible in the gate
    rather than only in the loader that happens to implement it.
    """
    for rule in plan.exclusions:
        for pattern in rule.paths:
            assert not (set("*?[]") & set(pattern[:-3] if
                                          pattern.endswith("/**") else pattern))
            if not pattern.endswith("/**"):
                assert (REPO_ROOT / pattern).is_file(), (
                    f"{rule.id} names `{pattern}`, which is not a file. An "
                    f"enumerated exclusion that names nothing is how a rule's "
                    f"count drifts from what it covers.")


# ---------------------------------------------------------------------------
# 3. What did it find?
# ---------------------------------------------------------------------------

def test_no_retired_word_appears_unaccounted_for(result, entries):
    """THE GATE. Every hit is owed by a ledger entry, within its recorded extent."""
    extents, extent_faults = excused(entries)
    faults = extent_faults + gate_faults(result, extents)
    assert not faults, (
        f"{len(faults)} finding(s):\n"
        + "\n".join(f"  {fault}" for fault in sorted(faults)))


def test_every_seeded_entry_is_still_a_real_violation(result, entries):
    """An entry cannot outlive the debt it records.

    #203's rule, applied here: paying a debt and deleting its entry are one act.
    Without this the ledger would go on claiming a word that had already left.
    """
    extents, _ = excused(entries)
    stale = [f for f in gate_faults(result, extents)
             if f.code == codes.LEDGER_ENTRY_STALE]
    assert not stale, "\n".join(str(fault) for fault in stale)


def test_every_entry_records_a_parseable_extent(entries):
    _, faults = excused(entries)
    assert not faults, "\n".join(str(fault) for fault in faults)


def test_every_entry_names_an_area_the_plan_declares(plan, entries):
    """A site against an area nothing defines can never be found or paid."""
    areas = set(plan.area_names)
    wrong = [entry.id for entry in entries
             if entry.site.partition("::")[0] not in areas]
    assert not wrong, (
        f"ledger entries name an area the plan does not declare: {wrong}")


def test_every_entry_expects_a_concept_the_registry_declares(registry, entries):
    """`expected` is what replaced the word, so it must be a live concept.

    This is what keeps the ledger and the registry from drifting in the other
    direction: an entry promising a replacement nothing declares is a debt
    nobody can pay correctly.
    """
    wrong = [(entry.id, entry.expected) for entry in entries
             if entry.expected not in registry.concepts]
    assert not wrong, (
        f"ledger entries expect a concept the registry does not declare: "
        f"{wrong}")


def test_the_ledger_and_the_registry_cannot_drift_apart(registry, entries):
    """Every entry's term is one the registry actually retires.

    With the negative control below — a term ADDED to the registry fails
    immediately — this is the acceptance criterion in both directions: the two
    lists cannot drift apart, whichever one moves.
    """
    retired = set(registry.retired_terms)
    orphans = [(entry.id, entry.site.partition("::")[2]) for entry in entries
               if entry.site.partition("::")[2] not in retired]
    assert not orphans, (
        f"ledger entries owe terms the registry no longer retires: {orphans}. "
        f"A word that stopped being retired is a debt nobody owes — delete the "
        f"entry in the same change that reclassifies the word.")


def test_sense_retired_words_are_not_swept(registry):
    """`retired_senses` is deliberately NOT sweep input (#202, ADR-0008 §1).

    The eight words are live in another sense, and sweeping them would force
    exclusions broad enough to disarm the gate — #154 §14's warning, arrived at
    from the other end.
    """
    swept = set(registry.retired_terms)
    for term in registry.retired_senses:
        assert term not in swept, (
            f"`{term}` is both a retired alias and a retired sense. It is one "
            f"or the other: the sweep works over text and cannot tell the "
            f"retired sense from the live one.")


# ---------------------------------------------------------------------------
# Negative controls — the sweep must FAIL on a synthetic violation
# ---------------------------------------------------------------------------

def _tree(tmp_path, files):
    for relative, text in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tuple(sorted(files))


def _plan(exclusions=(), anchors=("code/live.py",), areas=None,
          fallback="code"):
    """A minimal valid plan — one area, one anchor, and the controls' mutations.

    The fallback is the declared area's own name so that the default plan is
    fully anchored, and a control about an UNANCHORED area has to ask for one
    explicitly. A default that already tripped the vacuity guard would hide
    whichever fault each control is actually about.
    """
    return Plan(
        areas=areas if areas is not None else (
            Area("code", "code", "synthetic", "test"),),
        fallback_area=fallback, anchors=anchors, exclusions=tuple(exclusions))


#: The dotted-token override the real `webhook_event_type` carries, so a control
#: about a dotted retired term is built by the same rule the registry uses.
DOTTED = r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$'


def _registry(tmp_path, aliases=("rate_card",)):
    """A REAL registry, built by the shipped compiler, retiring ``aliases``.

    Written under its own directory so the synthetic tree the sweep walks and
    the registry that supplies its oracle never share a path — the sweep is
    given its files explicitly, and a registry sitting inside the swept tree
    would be a hit of its own.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    return load(tmp_path, concepts={"synthetic.yaml": {
        "synthetic_concept": concept(retired_aliases=list(aliases),
                                     token_pattern=DOTTED)}})


def _codes(faults):
    return {fault.code for fault in faults}


def test_negative_control_a_planted_retired_word_fails(tmp_path):
    """The gate's own reason to exist: a synthetic retired word on a living
    surface must be found. Without this, everything above is a green board over
    a walker that reads nothing."""
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/live.py": "CARD = 'rate_card'\n"})
    result = run(tmp_path, registry, _plan(), paths=paths)

    assert not result.faults, result.faults
    assert [(o.area, o.term) for o in result.occurrences] == [("code",
                                                              "rate_card")]
    assert _codes(gate_faults(result, {})) == {codes.TERM_ON_LIVING_SURFACE}


def test_positive_control_a_word_that_is_not_retired_is_not_a_hit(tmp_path):
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/live.py": "BOOK = 'pricing_book'\n"})
    result = run(tmp_path, registry, _plan(), paths=paths)
    assert not result.occurrences


def test_the_match_is_the_whole_token_and_nothing_less(tmp_path):
    """`rate_card` is not `rate_cards`, `x_rate_card` or `RateCard`.

    The last one is the stated limit rather than an oversight — see the module
    docstring of `tools/forbidden_terms/sweep.py`. Pinned here so that a change
    to the matcher has to come past a test that says what it decided.
    """
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {
        "code/live.py": "rate_cards = x_rate_card = RateCard = 1\n"})
    assert not run(tmp_path, registry, _plan(), paths=paths).occurrences

    paths = _tree(tmp_path, {"code/live.py": "d = {'rate_card': 1}\n"})
    assert run(tmp_path, registry, _plan(), paths=paths).occurrences


def test_a_dotted_event_name_is_matched_as_one_token(tmp_path):
    """`billing.balance_low` is a token with a dot in it, so `\\b` will not do."""
    registry = _registry(tmp_path / "reg", aliases=("billing.balance_low",))
    paths = _tree(tmp_path, {"code/live.py": "EVENT = 'billing.balance_low'\n"})
    assert run(tmp_path, registry, _plan(), paths=paths).occurrences

    paths = _tree(tmp_path, {"code/live.py": "E = 'x_billing.balance_lower'\n"})
    assert not run(tmp_path, registry, _plan(), paths=paths).occurrences


def test_negative_control_a_term_added_to_the_registry_fails_immediately(
        tmp_path):
    """The acceptance criterion, stated as a control.

    A word added to `retired_aliases` produces a failure on the next run with no
    other change, so the registry and the ledger cannot drift apart.
    """
    paths = _tree(tmp_path, {"code/live.py": "MODE = 'revenue_mode'\n"})
    before = run(tmp_path, _registry(tmp_path / "a"), _plan(), paths=paths)
    assert not gate_faults(before, {})

    after = run(tmp_path, _registry(tmp_path / "b",
                                    aliases=("rate_card", "revenue_mode")),
                _plan(), paths=paths)
    assert _codes(gate_faults(after, {})) == {codes.TERM_ON_LIVING_SURFACE}


def test_negative_control_a_ledgered_word_reaching_a_new_file_fails(tmp_path):
    """An excuse is an extent, not a licence.

    #203's review caught the shape this closes: an excuse keyed on the site
    alone stays green when the violation moves. Here it would stay green while
    a retired word spread across a surface it is already owed on.
    """
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/a.py": "x = 'rate_card'\n",
                             "code/b.py": "y = 'rate_card'\n",
                             "code/live.py": "# anchor\n"})
    result = run(tmp_path, registry, _plan(), paths=paths)

    assert not gate_faults(result, {("code", "rate_card"): 2})
    assert _codes(gate_faults(result, {("code", "rate_card"): 1})) == {
        codes.TERM_SPREAD}


def test_negative_control_an_overstated_extent_fails(tmp_path):
    """An excuse that may overstate is an excuse with no upper bound.

    Nothing else in the mechanism would catch it: the ledger's ratchet compares
    entry identities, not their contents, so `found: 999 files` would licence
    any amount of spread for as long as the entry stood.
    """
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/a.py": "x = 'rate_card'\n",
                             "code/live.py": "# anchor\n"})
    result = run(tmp_path, registry, _plan(), paths=paths)
    assert _codes(gate_faults(result, {("code", "rate_card"): 999})) == {
        codes.LEDGER_EXTENT_OVERSTATED}


def test_negative_control_a_paid_debt_left_in_the_ledger_fails(tmp_path):
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/live.py": "# nothing retired here\n"})
    result = run(tmp_path, registry, _plan(), paths=paths)
    assert _codes(gate_faults(result, {("code", "rate_card"): 1})) == {
        codes.LEDGER_ENTRY_STALE}


def test_negative_control_an_unparseable_extent_fails():
    """A `found` nobody can read would excuse any amount of spread."""
    class _Entry:
        def __init__(self, found):
            self.id, self.site, self.found = "g7-x", "code::rate_card", found

    for found in (None, "", "lots", "3", "3 files each"):
        _, faults = excused([_Entry(found)])
        assert _codes(faults) == {codes.LEDGER_EXTENT_UNPARSED}, found
    extents, faults = excused([_Entry("3 files")])
    assert not faults and extents == {("code", "rate_card"): 3}


def test_negative_control_a_widened_exclusion_fails(tmp_path):
    """The count is what a widening trips over."""
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/live.py": "# anchor\n",
                             "frozen/old.md": "rate_card\n",
                             "frozen/older.md": "rate_card\n"})
    honest = ExclusionRule("frozen", ("frozen/**",), "history", "permanent", 2)
    assert not run(tmp_path, registry, _plan([honest]), paths=paths).faults

    widened = ExclusionRule("frozen", ("frozen/**", "code/**"), "history",
                            "permanent", 2)
    faults = run(tmp_path, registry, _plan([widened]), paths=paths).faults
    assert codes.RULE_COUNT_WRONG in _codes(faults)
    assert codes.RULE_HIDES_ANCHOR in _codes(faults), (
        "widening over a living surface must fail on the anchor too, not only "
        "on the arithmetic")


def test_negative_control_an_inert_exclusion_fails(tmp_path):
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/live.py": "# anchor\n"})
    inert = ExclusionRule("gone", ("deleted/**",), "why", "permanent", 3)
    faults = run(tmp_path, registry, _plan([inert]), paths=paths).faults
    assert codes.RULE_INERT in _codes(faults)


def test_negative_control_two_rules_over_one_file_fails(tmp_path):
    """Overlap makes each rule's count a guess, and deleting one silently
    changes the other's."""
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/live.py": "# anchor\n",
                             "frozen/old.md": "rate_card\n"})
    rules = [ExclusionRule("a", ("frozen/**",), "why", "permanent", 1),
             ExclusionRule("b", ("frozen/old.md",), "why", "permanent", 1)]
    faults = run(tmp_path, registry, _plan(rules), paths=paths).faults
    assert codes.RULE_OVERLAP in _codes(faults)


def test_negative_control_an_unread_anchor_fails(tmp_path):
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/other.py": "# not the anchor\n"})
    faults = run(tmp_path, registry, _plan(), paths=paths).faults
    assert codes.ANCHOR_MISSING in _codes(faults)


def test_negative_control_an_area_with_no_anchor_fails(tmp_path):
    registry = _registry(tmp_path / "reg")
    paths = _tree(tmp_path, {"code/live.py": "# anchor\n"})
    areas = (Area("code", "code", "synthetic", "test"),
             Area("orphan", "orphan", "no anchor names it", "test"))
    faults = run(tmp_path, registry, _plan(areas=areas), paths=paths).faults
    assert codes.AREA_UNANCHORED in _codes(faults)


def test_negative_control_an_undecodable_file_fails(tmp_path):
    registry = _registry(tmp_path / "reg")
    _tree(tmp_path, {"code/live.py": "# anchor\n"})
    (tmp_path / "code" / "blob.bin").write_bytes(b"\xff\xfe\x00rate_card")
    faults = run(tmp_path, registry, _plan(),
                 paths=("code/blob.bin", "code/live.py")).faults
    assert codes.FILE_UNDECODABLE in _codes(faults)


def test_negative_control_an_unlistable_tree_fails(tmp_path):
    """Not an empty sweep. "Found nothing" and "read nothing" are one output,
    and the second is how a gate goes green by doing nothing."""
    paths, problem = tracked_files(tmp_path)
    assert paths == () and problem is not None
    assert problem.code == codes.TREE_UNREADABLE


def test_the_tracked_listing_is_what_the_sweep_walks():
    """A positive control on the one piece that shells out."""
    paths, problem = tracked_files(REPO_ROOT)
    assert problem is None
    assert "CLAUDE.md" in paths and PLAN_PATH in paths
    listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"],
                            capture_output=True, text=True, check=True)
    assert len(paths) == len([p for p in listed.stdout.splitlines() if p])


# ---------------------------------------------------------------------------
# Negative controls on the declared plan itself
# ---------------------------------------------------------------------------

def _document():
    return yaml.safe_load((REPO_ROOT / PLAN_PATH).read_text(encoding="utf-8"))


def _exclusions():
    return [dict(rule) for rule in _document()["exclusions"]]


def _load_synthetic(tmp_path, registry, programme, **changes):
    """The REAL plan with one thing changed, so a control proves one thing.

    Loaded against the real repository root — anchors and area roots must still
    resolve — but read from a temporary file. Nothing writes to the committed
    declaration: a control that edited it and restored it in a `finally` would
    leave the repository corrupted the one time a run was killed.
    """
    document = _document()
    document.update(changes)
    path = tmp_path / "forbidden-term-sweep.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return load_plan(REPO_ROOT, registry.surfaces, programme.slices,
                     plan_path=path)


@pytest.mark.parametrize("pattern", [
    "docs/**/*.md",          # a wildcard in the middle
    "docs/plans/*",          # a single-segment glob
    "**",                    # the entire repository
    "/docs/plans/**",        # not repository-relative
    "../elsewhere/**",       # outside the repository
    "docs\\plans\\**",       # a Windows separator
])
def test_negative_control_a_pattern_outside_the_two_shapes_is_refused(
        tmp_path, registry, programme, pattern):
    """No wildcard language. A matcher with corners is a way to disarm a gate."""
    exclusions = _exclusions()
    exclusions[0]["paths"] = [pattern]
    plan, faults = _load_synthetic(tmp_path, registry, programme,
                                   exclusions=exclusions)
    assert plan is None
    assert codes.BAD_PATTERN in _codes(faults), pattern


def test_negative_control_an_ending_exclusion_must_name_its_end(
        tmp_path, registry, programme):
    """#155 §5.4: the reason a reader sees carries the end date too."""
    exclusions = _exclusions()
    ending = next(r for r in exclusions if r["permanence"] == UNTIL_SLICE_8)
    ending["reason"] = "migrations carry historical column names."
    plan, faults = _load_synthetic(tmp_path, registry, programme,
                                   exclusions=exclusions)
    assert plan is None
    assert codes.PERMANENCE_UNSTATED in _codes(faults)


def test_negative_control_an_unstated_permanence_is_refused(
        tmp_path, registry, programme):
    exclusions = _exclusions()
    exclusions[0]["permanence"] = "for_now"
    plan, faults = _load_synthetic(tmp_path, registry, programme,
                                   exclusions=exclusions)
    assert plan is None
    assert codes.UNKNOWN_PERMANENCE in _codes(faults)


def test_negative_control_an_area_shadowing_a_registry_surface_is_refused(
        tmp_path, registry, programme):
    """The four surfaces come from consumers.yaml. A second copy of a root is a
    second thing to keep true."""
    plan, faults = _load_synthetic(
        tmp_path, registry, programme,
        areas={"backend": {"root": "ubb-platform", "summary": "again"}})
    assert plan is None
    assert codes.AREA_SHADOWS_SURFACE in _codes(faults)


def test_negative_control_a_missing_anchor_is_refused(tmp_path, registry,
                                                      programme):
    plan, faults = _load_synthetic(tmp_path, registry, programme,
                                   anchors=["no/such/file.py"])
    assert plan is None
    assert codes.ANCHOR_MISSING in _codes(faults)


def test_negative_control_an_unknown_section_is_refused(tmp_path, registry,
                                                        programme):
    """A plan that grew a section nothing reads is a declaration nobody enforces."""
    plan, faults = _load_synthetic(tmp_path, registry, programme,
                                   skip_if_awkward=["everything"])
    assert plan is None
    assert codes.PLAN_UNKNOWN_FIELD in _codes(faults)


def test_the_registry_surfaces_become_areas_without_being_restated(plan,
                                                                   registry):
    """Derived, not copied — so #207 adding a surface moves this sweep with it."""
    derived = {area.name for area in plan.areas
               if area.declared_by == "consumers.yaml"}
    assert derived == set(registry.surfaces)
    assert "docs" in plan.area_names and plan.fallback_area in plan.area_names


def _rule(plan, rule_id):
    return next(rule for rule in plan.exclusions if rule.id == rule_id)
