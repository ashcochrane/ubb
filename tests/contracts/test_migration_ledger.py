"""The migration ledger only shrinks, and it is not the exceptions list (#201).

The ledger is a finite migration plan that reaches zero at slice 8, before
platform admission (#158 §11.3). Three mechanical rules make it one rather than
a bucket of excuses, and each has controls here:

1. **It only shrinks**, compared against the base branch — additions are refused
   unless a seeding authorisation naming the gate is new in the change, and a
   debt cannot be deferred by quietly moving its owner slice later.
2. **Every entry names a real gate and a real slice** — and the gate must be
   `installed`, because a debt recorded against a check that cannot fail
   anything is a note nothing will ever prove or clear.
3. **An entry whose owner slice has already landed fails CI.** That is #155
   §17's recorded residue closed: the seeded allowlists had no stated owner per
   entry, so an entry could survive to slice 8 by everyone assuming somebody
   else owned it.

**Permanent reasoned exceptions are a separate list**, and the separation is
structural rather than a convention: an exception carries no owner slice and no
expected term, because no rename is coming. The tests below assert that shape,
so the two lists cannot quietly merge — which would make "the ledger is at zero"
unachievable by construction, and G22 depends on it being reachable.

The ratchet's comparison is a pure function over two parsed ledgers, so the
controls feed it synthetic revisions through the same entry point CI uses. One
control drives it through real git in a real repository, because the plumbing
that resolves a base ref is exactly the part a pure test cannot reach.
"""

import pytest
import yaml

from _gate_helpers import (
    UNLANDED_SLICE,
    gates,
    git,
    installed,
    load,
    real,
    rejection,
)
from _helpers import REPO_ROOT
from tools.gates import errors as codes
from tools.gates import load_programme
from tools.gates.enforcement import step_faults
from tools.gates.ratchet import LEDGER_PATH, compare, ledger_at, resolve_base, run

GATES_DIR = REPO_ROOT / "gates"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

#: The CI step that runs the ratchet. Named here so disarming it is a visible
#: act in a diff rather than a silent one.
RATCHET_JOB = "contracts"
RATCHET_STEP = "Migration ledger ratchet — it only shrinks"


@pytest.fixture(scope="module")
def programme():
    return load_programme(GATES_DIR, REPO_ROOT)


@pytest.fixture(scope="module")
def slices(programme):
    return programme.slices


@pytest.fixture(scope="module")
def unlanded(slices):
    """Every slice that has not landed, earliest in the chain first.

    DERIVED rather than typed, and slice 2 landing is why. `entry`'s default
    owner was `slice_2`, and `test_an_entry_owned_by_a_landed_slice_is_rejected`
    mutated slice 2 by name — so on the day it landed that control went on
    passing with its mutation line deleted entirely, proving nothing.

    The two order-pair controls did NOT go red then, and that is the sharper
    reason to derive rather than re-point: `compare` reads a slice's `order` and
    never its `landed` flag, so a landed slice named there keeps passing while
    describing a move :func:`load_programme` refuses outright. Re-typing a
    different slice would only move the expiry date, and nothing would go red
    when it arrived.

    A filter cannot name a landed slice, so vacuity here is structurally
    unavailable rather than something a future reader has to remember to check.
    """
    ordered = sorted((declared for declared in slices.values()
                      if not declared.landed),
                     key=lambda declared: declared.order)
    assert len(ordered) >= 2, (
        "fewer than two slices have yet to land, so the controls about the "
        "ratchet's direction have no unlanded pair to run on — at that point "
        "the ledger is at or near zero and they are asserting about history")
    return tuple(declared.key for declared in ordered)


def ledger(entries=(), authorisations=()):
    return {"version": 1, "entries": list(entries),
            "seeding_authorisations": list(authorisations)}


def entry(identifier="L001", gate="G1", site="a/site.py::Thing",
          owner_slice=UNLANDED_SLICE, **overrides):
    body = {"id": identifier, "gate": gate, "site": site,
            "expected": "the_canonical_term", "owner_slice": owner_slice,
            "reason": "it predates the rename"}
    body.update(overrides)
    return body


def authorisation(gate="G1", issue=203, entries_added=1):
    return {"gate": gate, "issue": issue, "entries_added": entries_added,
            "reason": "this pull request installs the gate and records what it finds"}


# ---------------------------------------------------------------------------
# 1. The shipped ledger, and the ratchet that guards it
# ---------------------------------------------------------------------------

def test_every_shipped_record_names_an_installed_gate_and_an_unlanded_owner(
        programme):
    """Rules 2 and 3, over the ledger and exceptions this repository ships.

    #201 shipped this as *"the ledger is empty and that is the rule, not an
    omission"*, with the instruction that when the assertion first failed the fix
    was to replace it with the loop over real entries rather than delete the
    rule. #203 is what made it fail: installing the four model-naming gates put
    six debts and one permanent exception on the record, in the same pull
    request, which is the ordering rule 2 exists to force.

    Deliberately **not** an assertion that the ledger is non-empty. It reaches
    zero at slice 8, and a test that had to be edited on the day it did would be
    a test arguing with the outcome it exists to produce. What is asserted is
    the rule — true of seven records today and of none then.
    """
    assert programme.installed_gates(), "no gate is installed — suspect the parse"

    for record in programme.entries + programme.exceptions:
        assert programme.gates[record.gate].installed, (
            f"{record.id} names {record.gate}, which is not installed — a debt "
            f"against a check that cannot fail anything is a note nothing will "
            f"ever prove or clear")

    for record in programme.entries:
        owner = programme.slices[record.owner_slice]
        assert not owner.landed, (
            f"{record.id} is owed by {record.owner_slice} (#{owner.issue}), "
            f"which has landed — so this debt is owed by nobody")


def test_no_shipped_entry_expects_the_term_it_already_carries(programme):
    """An entry whose `expected` equals its `found` records no debt at all.

    The compiler checks that both are non-empty strings, which a copy-paste
    while seeding satisfies perfectly. This is the assertion that a seeded entry
    describes an actual difference — and it is worth making precisely because
    seeding happens in bulk, by hand, in the pull request that installs a gate.
    """
    inert = sorted(record.id for record in programme.entries
                   if record.found is not None
                   and record.found == record.expected)
    assert not inert, (
        "these entries expect the term the site already carries, so nothing "
        "would change when they are 'paid': " + ", ".join(inert))


def test_ci_runs_the_ratchet_and_can_fail_on_it():
    """The gate over the gate. Everything else about the ledger is checked in
    this suite, offline; the shrink-only comparison needs git history and so
    runs as its own CI step — which means it can be disarmed the same way the
    conformance sweep was, and this is what says so."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert step_faults(workflow, RATCHET_JOB, RATCHET_STEP) == []


def test_the_ratchet_job_fetches_the_history_it_needs():
    """A comparison against the base branch cannot run on a shallow checkout,
    and `resolve_base` fails rather than skipping when it cannot — so a missing
    `fetch-depth` would turn CI red rather than green. This keeps the fix in the
    workflow instead of leaving it to be rediscovered from a failure."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    checkouts = [step for step in workflow["jobs"][RATCHET_JOB]["steps"]
                 if str(step.get("uses", "")).startswith("actions/checkout")]
    assert checkouts, "the ratchet's job checks nothing out"
    assert any((step.get("with") or {}).get("fetch-depth") == 0
               for step in checkouts)


def test_permanent_exceptions_are_a_different_shape_from_debts():
    """The separation, in data rather than in a convention: an exception has no
    owner slice and no expected term, because nobody owes a rename."""
    schema = yaml.safe_load(real("schema.yaml"))
    exception_fields = set(schema["exception_fields"]["required"]) | set(
        schema["exception_fields"].get("optional") or ())
    assert "owner_slice" not in exception_fields
    assert "expected" not in exception_fields
    assert {"owner_slice", "expected"} <= set(
        schema["ledger_entry_fields"]["required"])


def test_permanent_exceptions_live_in_their_own_file():
    assert (GATES_DIR / "permanent-exceptions.yaml").is_file()
    committed = yaml.safe_load(
        (GATES_DIR / "migration-ledger.yaml").read_text(encoding="utf-8"))
    assert "exceptions" not in committed, (
        "the ledger has acquired an exceptions list; the two must stay apart or "
        "'the ledger is at zero' becomes unreachable")


def test_an_exception_that_claims_an_owner_is_rejected(tmp_path):
    """Belt and braces on the separation: the shape rule is enforced, not just
    declared, so an exception cannot be filed as a debt in disguise."""
    invalid = rejection(
        tmp_path, gates=gates(G1=installed()),
        exceptions={"version": 1, "exceptions": [
            {"id": "X1", "gate": "G1", "site": "a/site.py::Thing",
             "reason": "a single acronym token", "owner_slice": "slice_8"}]})
    assert invalid.codes() == {codes.ENTRY_UNKNOWN_FIELD}


# ---------------------------------------------------------------------------
# 2. Entry validity — negative controls
# ---------------------------------------------------------------------------

def test_an_entry_naming_a_gate_that_does_not_exist_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        ledger=ledger([entry(gate="G99")]))
    assert invalid.codes() == {codes.UNKNOWN_GATE}


def test_an_entry_naming_a_gate_that_is_not_installed_is_rejected(tmp_path):
    """A debt against a check nothing runs cannot shrink: no gate would go green
    when the site is fixed, and nothing would ever prove the entry right."""
    invalid = rejection(tmp_path, ledger=ledger([entry(gate="G7")]))
    assert invalid.codes() == {codes.GATE_NOT_INSTALLED}


def test_an_entry_naming_a_slice_that_does_not_exist_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        ledger=ledger([entry(owner_slice="slice_99")]))
    assert invalid.codes() == {codes.UNKNOWN_SLICE}


def test_an_entry_owned_by_a_landed_slice_is_rejected(tmp_path, unlanded):
    """#155 §17, closed. An entry cannot survive to slice 8 because everyone
    assumed somebody else owned it: the moment its owner lands, it goes red.

    The mutation IS the control, so it names a slice that has not landed and
    lands it here. Naming one that already had is how this went vacuous when
    slice 2 landed: the shipped file carried `landed: true` by itself, the
    rejection arrived for a reason the test had not caused, and the assertion
    held with the mutation line deleted outright.
    """
    owner = unlanded[0]
    assert owner != UNLANDED_SLICE, (
        f"the synthetic gate rows are owed by {UNLANDED_SLICE}, so landing it "
        f"here would fault all of them for `landed_slice_owns_gate` too and "
        f"this control could no longer say the ledger's code is the ONLY one. "
        f"It cannot happen while that slice carries the highest `order`, which "
        f"is what makes it last — but the assertion below depends on it, so it "
        f"is stated rather than left to be inferred")
    declared = yaml.safe_load(real("slices.yaml"))
    declared["slices"][owner]["landed"] = True
    invalid = rejection(tmp_path, slices=declared,
                        gates=gates(G1=installed(), G14=installed()),
                        ledger=ledger([entry(owner_slice=owner)]))
    assert invalid.codes() == {codes.OWNER_SLICE_LANDED}


def test_an_entry_missing_its_owner_is_rejected(tmp_path):
    body = entry()
    del body["owner_slice"]
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        ledger=ledger([body]))
    assert invalid.codes() == {codes.ENTRY_MISSING_FIELD}


def test_an_entry_missing_the_term_it_expects_is_rejected(tmp_path):
    body = entry()
    del body["expected"]
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        ledger=ledger([body]))
    assert invalid.codes() == {codes.ENTRY_MISSING_FIELD}


def test_two_entries_with_one_identifier_are_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        ledger=ledger([entry(site="a.py::One"),
                                       entry(site="b.py::Two")]))
    assert invalid.codes() == {codes.DUPLICATE_ENTRY_ID}


def test_one_debt_recorded_twice_is_rejected(tmp_path):
    """Two entries for one site would let the ledger shrink by one while nothing
    changed — the count is what slice 8 reads."""
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        ledger=ledger([entry("L001"), entry("L002")]))
    assert invalid.codes() == {codes.DUPLICATE_ENTRY_SITE}


def test_an_authorisation_that_miscounts_its_type_is_rejected(tmp_path):
    invalid = rejection(
        tmp_path, gates=gates(G1=installed()),
        ledger=ledger([], [authorisation(entries_added="lots")]))
    assert invalid.codes() == {codes.AUTHORISATION_INVALID_FIELD_TYPE}


def test_an_authorisation_for_a_gate_that_does_not_exist_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        ledger=ledger([], [authorisation(gate="G99")]))
    assert invalid.codes() == {codes.UNKNOWN_GATE}


def test_a_legal_ledger_loads(tmp_path):
    programme = load(tmp_path, gates=gates(G1=installed()),
                     ledger=ledger([entry()], [authorisation()]))
    assert [record.id for record in programme.entries] == ["L001"]
    assert programme.entries[0].identity == ("G1", "a/site.py::Thing")


# ---------------------------------------------------------------------------
# 3. The ratchet — the comparison against the base branch
# ---------------------------------------------------------------------------

def test_removing_entries_is_always_allowed(slices):
    comparison = compare(ledger([entry("L001"), entry("L002", site="b.py::Two")]),
                         ledger([entry("L001")]), slices)
    assert comparison.ok
    assert comparison.removed == (("G1", "b.py::Two"),)


def test_adding_an_entry_without_an_override_fails(slices):
    comparison = compare(ledger(), ledger([entry()]), slices)
    assert not comparison.ok
    assert {fault.code for fault in comparison.faults} == {codes.LEDGER_GREW}


def test_adding_an_entry_with_a_reviewed_override_passes(slices):
    comparison = compare(ledger(), ledger([entry()], [authorisation()]), slices)
    assert comparison.ok
    assert comparison.added == (("G1", "a/site.py::Thing"),)


def test_an_override_that_undercounts_the_additions_fails(slices):
    """A reviewer approves a quantity, not an intention: an authorisation for
    one entry cannot wave three through."""
    head = ledger([entry("L001", site="a.py::One"),
                   entry("L002", site="b.py::Two"),
                   entry("L003", site="c.py::Three")], [authorisation()])
    comparison = compare(ledger(), head, slices)
    assert {fault.code for fault in comparison.faults} == {
        codes.AUTHORISATION_COUNT_WRONG}


def test_an_override_carried_over_from_the_base_licenses_nothing(slices):
    """The authorisation list is an audit trail, not standing permission. The
    entry that seeded G1 last month must not wave through a new one today."""
    base = ledger([entry("L001")], [authorisation()])
    head = ledger([entry("L001"), entry("L002", site="b.py::Two")],
                  [authorisation()])
    comparison = compare(base, head, slices)
    assert {fault.code for fault in comparison.faults} == {codes.LEDGER_GREW}


def test_a_second_seeding_of_the_same_gate_needs_its_own_override(slices):
    base = ledger([entry("L001")], [authorisation()])
    head = ledger([entry("L001"), entry("L002", site="b.py::Two")],
                  [authorisation(), authorisation(issue=206)])
    assert compare(base, head, slices).ok


def test_an_override_that_licensed_nothing_fails(slices):
    """An override that overrides nothing is the shape of a check that cannot
    fail — the same defect the inert-suppression rule catches in the spec gate."""
    comparison = compare(ledger(), ledger([], [authorisation()]), slices)
    assert {fault.code for fault in comparison.faults} == {
        codes.AUTHORISATION_INERT}


def test_deferring_a_debt_to_a_later_slice_fails(slices, unlanded):
    """Not an addition, and not a shrink either: the entry is still owed and now
    lands nearer the cutover. #155 §17's failure with an extra step."""
    earliest, latest = unlanded[0], unlanded[-1]
    comparison = compare(ledger([entry(owner_slice=earliest)]),
                         ledger([entry(owner_slice=latest)]), slices)
    assert {fault.code for fault in comparison.faults} == {codes.DEBT_DEFERRED}


def test_pulling_a_debt_earlier_is_free(slices, unlanded):
    earliest, latest = unlanded[0], unlanded[-1]
    comparison = compare(ledger([entry(owner_slice=latest)]),
                         ledger([entry(owner_slice=earliest)]), slices)
    assert comparison.ok


def test_relabelling_an_entry_is_neither_a_payment_nor_a_debt(slices):
    """Identity is the gate and the place, not the label somebody typed."""
    comparison = compare(ledger([entry("L001")]), ledger([entry("L999")]),
                         slices)
    assert comparison.ok
    assert comparison.added == () and comparison.removed == ()


def test_moving_a_site_is_an_addition_and_needs_review(slices):
    comparison = compare(ledger([entry(site="a.py::One")]),
                         ledger([entry(site="b.py::Two")]), slices)
    assert {fault.code for fault in comparison.faults} == {codes.LEDGER_GREW}


def test_a_base_with_no_ledger_at_all_treats_every_entry_as_new(slices):
    """The true state of a branch taken before this ticket landed."""
    comparison = compare({}, ledger([entry()]), slices)
    assert {fault.code for fault in comparison.faults} == {codes.LEDGER_GREW}
    assert compare({}, ledger(), slices).ok


# ---------------------------------------------------------------------------
# 4. The ratchet, driven through real git
# ---------------------------------------------------------------------------

@pytest.fixture
def repository(tmp_path):
    """A real git repository with a real ledger committed on `main`.

    Real git, because resolving the base ref is exactly the part the pure
    comparison above cannot reach — and it is the part that decides whether the
    gate runs at all.
    """
    git(tmp_path, "init", "-b", "main", str(tmp_path))
    git(tmp_path, "config", "user.email", "ci@example.invalid")
    git(tmp_path, "config", "user.name", "CI")
    write(tmp_path, ledger([entry("L001")]))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "the ledger as it stands")
    return tmp_path


def write(repository, document):
    path = repository / LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def test_a_branch_that_adds_an_entry_fails_against_its_base(repository, slices):
    git(repository, "checkout", "-b", "feature")
    write(repository, ledger([entry("L001"), entry("L002", site="b.py::Two")]))
    comparison = run(repository, slices, base="main")
    assert {fault.code for fault in comparison.faults} == {codes.LEDGER_GREW}


def test_the_same_branch_passes_once_the_addition_is_authorised(repository,
                                                                slices):
    git(repository, "checkout", "-b", "feature")
    write(repository, ledger([entry("L001"), entry("L002", site="b.py::Two")],
                             [authorisation()]))
    assert run(repository, slices, base="main").ok


def test_a_branch_that_pays_a_debt_off_passes(repository, slices):
    git(repository, "checkout", "-b", "feature")
    write(repository, ledger())
    comparison = run(repository, slices, base="main")
    assert comparison.ok and len(comparison.removed) == 1


def test_on_the_base_branch_itself_the_comparison_is_against_the_parent(
        repository, slices):
    """The merge base with `main` IS HEAD here, so a naive comparison would be
    against the change itself and prove nothing. It falls back to the parent,
    which makes the question "did this commit add entries?" — so a direct push
    is gated too."""
    write(repository, ledger([entry("L001"), entry("L002", site="b.py::Two")]))
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "a debt added straight to main")
    comparison = run(repository, slices, base="main")
    assert {fault.code for fault in comparison.faults} == {codes.LEDGER_GREW}


def test_a_baseline_that_cannot_be_resolved_fails_rather_than_skipping(
        repository, slices):
    """A silently skipped comparison is how a debt reaches main unreviewed —
    openapi/contract_gate.py made the same call for its tag."""
    comparison = run(repository, slices, base="origin/nonexistent")
    assert {fault.code for fault in comparison.faults} == {codes.BASE_UNREADABLE}


def test_a_ref_whose_tree_has_no_ledger_reads_as_an_empty_one(repository):
    """A branch taken before this ticket landed has no ledger file at all. That
    is an empty ledger, not an unreadable one — every entry is genuinely new."""
    git(repository, "checkout", "-b", "feature")
    git(repository, "rm", "-r", "--quiet", "gates")
    git(repository, "commit", "-m", "before the ledger existed")
    assert ledger_at(repository, "HEAD") == {}
    assert ledger_at(repository, "main") != {}


def test_a_committed_proposal_is_never_compared_against_itself(repository):
    """The merge base with `main` IS HEAD once a change lands there. Comparing
    HEAD against HEAD would make the gate pass on everything."""
    write(repository, ledger([entry("L001"), entry("L002", site="b.py::Two")]))
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "a second commit on main")

    reference, problem = resolve_base(repository, base="main")
    assert problem is None
    assert reference == git(repository, "rev-parse", "HEAD^")


def test_an_uncommitted_proposal_is_compared_against_head(repository):
    """The author's case: the ledger is edited and not yet committed, so HEAD is
    the baseline and there is nothing else it could be. Falling back to the
    parent here would compare the proposal against a ledger two revisions old."""
    write(repository, ledger([entry("L001"), entry("L002", site="b.py::Two")]))
    reference, problem = resolve_base(repository, base="main",
                                      proposal_is_committed=False)
    assert problem is None
    assert reference == git(repository, "rev-parse", "HEAD")


def test_an_uncommitted_addition_is_caught_before_it_is_committed(repository,
                                                                  slices):
    write(repository, ledger([entry("L001"), entry("L002", site="b.py::Two")]))
    comparison = run(repository, slices, base="main")
    assert {fault.code for fault in comparison.faults} == {codes.LEDGER_GREW}
