"""The gate manifest is true — slice 0's single coordinating verdict (#201).

ADR-0008 §8 lists twenty-seven standing gates. Before `gates/manifest.yaml`
existed, that list lived in a frozen decision document and nothing compared it
against the repository: a gate that quietly stopped running would have gone on
being listed as one.

So this suite asserts the manifest's claims rather than its existence:

1. **The inventory is complete.** Twenty-seven rows, each with a statement, an
   oracle and exactly one status.
2. **`installed` means running.** Every named site is verified — the job runs on
   push and pull request with no path filter, neither job nor step is
   `continue-on-error` or `if:`-conditional, and a named test node is one its
   suite actually collects and is not marked skip or xfail.
3. **`owned_by_slice_N` names a real slice** and states what must exist first.
   A gate whose subject does not exist is recorded against its owner, never
   installed as a test that passes on nothing.

Every rule carries a negative control that puts a synthetic violation through
:func:`tools.gates.load_programme` — the same entry point CI uses — because a
gate that has never been shown to fail is an assertion, not evidence. And the
shipped manifest carries a vacuity guard, because a checker that walked nothing
would pass every rule above while proving none of them.
"""

import pytest
import yaml

from _gate_helpers import (
    SUITE_ROOT,
    TEST_FILE,
    TEST_NODE,
    copy_real_programme,
    gates,
    installed,
    load,
    obligation,
    owned,
    real,
    rejection,
    suites,
    workflow_document,
)
from _helpers import REPO_ROOT
from tools.gates import GatesInvalid, load_programme, owner_slice_of
from tools.gates import errors as codes
from tools.gates.enforcement import Collection

GATES_DIR = REPO_ROOT / "gates"


@pytest.fixture(scope="module")
def programme():
    return load_programme(GATES_DIR, REPO_ROOT)


# ---------------------------------------------------------------------------
# 1. The shipped manifest
# ---------------------------------------------------------------------------

def test_the_shipped_manifest_is_true(programme):
    """The single coordinating verdict: every claim in the manifest holds.

    Loading it IS the check — `load_programme` verifies each `installed` row
    against the workflow and the suites' collection rules, and raises with every
    fault at once. Reaching this line means none were found.
    """
    assert programme.gates


def test_the_gate_actually_read_the_manifest(programme):
    """Vacuity guard: prove the load produced the real programme, not an empty
    mapping that would make every check here pass on nothing."""
    declared = yaml.safe_load((GATES_DIR / "manifest.yaml").read_text("utf-8"))
    assert set(programme.gates) == set(declared["gates"])
    assert len(programme.gates) == 27, "ADR-0008 §8 lists twenty-seven gates"
    assert set(programme.slices) >= {"slice_0", "slice_8", "slice_builder"}
    assert programme.suites, "no pytest suite was declared or verified"
    # At least one gate must actually be installed, or "installed means running"
    # is a rule with no subject and the negative controls below are the only
    # thing exercising it.
    assert programme.installed_gates()


def test_every_row_states_what_it_asserts_and_what_settles_it(programme):
    for name, row in programme.rows.items():
        assert row.statement.strip(), f"{name} states no gate"
        assert row.oracle.strip(), f"{name} names no oracle"


def test_every_installed_row_names_where_it_runs(programme):
    for name, row in programme.installed_gates().items():
        assert row.sites, f"{name} claims to be installed and names nowhere"


def test_every_owed_row_names_a_real_slice_and_what_must_exist_first(programme):
    owed = {name: row for name, row in programme.rows.items()
            if row.owner_slice is not None}
    assert owed, "no gate is owed — suspect the parse"
    for name, row in owed.items():
        assert row.owner_slice in programme.slices, name
        assert not programme.slices[row.owner_slice].landed, name
        assert row.body["blocked_on"].strip(), (
            f"{name} is owed by {row.owner_slice} without saying what must "
            f"exist before it can be installed")


def test_the_gates_whose_subject_does_not_exist_are_owed_not_faked(programme):
    """#191 decision 6 names these three explicitly, and the reason is the same
    for each: the column, the protected field and the squash do not exist, so
    installing the gate would be installing a test that passes on nothing."""
    for name in ("G14", "G19", "G20"):
        row = programme.gates[name]
        assert row.owner_slice is not None, (
            f"{name}'s subject does not exist yet, so it cannot be installed")


def test_slice_0_declares_the_payment_rail_names_and_owes_the_machinery(programme):
    """#191 decision 14's split, as a claim about this manifest (#202).

    Slice 0 declares `payment_rail` and its environment values as `closed`
    registry concepts, because ADR-0008 §10.4 requires the names to exist before
    anything is built on them. Slice 8 builds the record, the flag and the
    centrally enforced invariant. The audit has to be able to tell the early
    declaration from the later implementation, and this is what says so: the
    names existing must never be read as the invariant being enforced.

    The general shape of an owed row and of a deferred obligation is asserted
    over every row above; what is asserted here is the pairing those checks
    cannot know — that it is *slice 8* that owes G27, and that the obligation
    beside it is the live-money one rather than some other deferral.
    """
    assert programme.gates["G27"].owner_slice == "slice_8"
    assert "live" in programme.obligations["O3"].body["evidence_required"]


#: The gates whose statement IS "a consumer carries the registry's values".
#: While any of them is uninstalled the registry's disagreement with that
#: consumer cannot be a ledger entry, because an entry may only name an
#: installed gate — so `blocked_on` is the only place that debt is visible.
CONSUMER_AGREEMENT_GATES = ("G2", "G3", "G4", "G6")


def test_the_registrys_consumer_gates_name_what_will_seed_them(programme):
    """#202 authored the vocabulary these four gates will compare against, and
    nothing else ties the two together (#202's own acceptance criteria asked for
    a ledger entry per disagreeing concept, which rule 2 does not admit while
    the gates are owed).

    So each row states the registry as the input its installer seeds from. It is
    the weakest useful form of the tie — prose in a checked field — but it is
    the form available before the consumers exist, and it fails loudly if
    somebody flips one of these to `installed` without a consumer to compare.
    """
    for name in CONSUMER_AGREEMENT_GATES:
        row = programme.gates[name]
        if row.installed:
            continue
        assert "domain-vocabulary" in row.body["blocked_on"], (
            f"{name} does not say it will be seeded from the registry — a "
            f"reader installing it has nowhere to look for what it should find"
        )


def test_every_deferred_obligation_carries_its_reason_owner_and_evidence(programme):
    """ADR-0008 §6: these are carried explicitly, "never silently marked passed"."""
    assert programme.obligations, "the deferred obligations went missing"
    for name, row in programme.obligations.items():
        assert row.status == "deferred_obligation", name
        for field in ("reason", "owner_role", "evidence_required"):
            assert row.body[field].strip(), f"{name} carries no {field}"


#: The script that would have performed O3's live-money check, deleted by #242.
#: O3's `notes` carry what it was and why it went; this file holds only the path,
#: because the path is the part an assertion can be wrong about.
DELETED_MONEY_SCRIPT = "ubb-platform/scripts/integration_test.py"

#: A surviving sibling, and the vacuity guard for the absence above. `scripts/`
#: moving or being re-rooted would make the absence true for the wrong reason.
SURVIVING_SIBLING_SCRIPT = "ubb-platform/scripts/export_openapi.py"


def test_the_deleted_money_script_did_not_take_its_obligation_with_it(programme):
    """#242, and the one guarantee that ticket is about: the mechanism went, the
    obligation did not.

    #155 §11.4 recorded the script so a cleanup could not take the obligation
    with it, and #158 §11 then amended the timing rather than the debt. Deleting
    it left the tie between the two living ONLY in frozen dated plans, which may
    not be edited and which nobody greps on the way past a deletion — so O3
    carries the pointer instead.

    Both halves are asserted together because separately each is weak: an
    absence says nothing about the debt, and a note claiming a deletion is prose
    until something reads the tree. The pairing is what says the deletion was
    not a discharge.
    """
    assert (REPO_ROOT / SURVIVING_SIBLING_SCRIPT).exists(), (
        f"{SURVIVING_SIBLING_SCRIPT} is gone, so the absence asserted below is "
        f"no longer evidence of anything — `ubb-platform/scripts/` has moved or "
        f"been re-rooted and both paths here need respelling"
    )
    assert not (REPO_ROOT / DELETED_MONEY_SCRIPT).exists(), (
        f"{DELETED_MONEY_SCRIPT} is back. O3's note says it was deleted and the "
        f"obligation outlived it; if a live-money runner returns, that note is "
        f"what has to change — not this assertion, quietly"
    )

    live_money = programme.obligations["O3"]
    assert live_money.status == "deferred_obligation", (
        "O3 is the live-money obligation. ADR-0008 §6: never silently marked "
        "passed — and deleting the script that would have run it is not the "
        "act that settles it"
    )

    notes = live_money.body.get("notes", "")
    assert DELETED_MONEY_SCRIPT in notes, (
        "O3 does not say where the deleted money script went, so a reader "
        "arriving from the deletion has nothing living to land on"
    )
    for pointer in ("#158 §11", "ADR-0008 §6"):
        assert pointer in notes, f"O3's note does not point at {pointer}"


def test_every_declared_suite_config_can_actually_be_read(programme):
    """A suite's collection rules are consulted only when a gate names a node in
    it, and today none does for two of the three. Reading them here means a
    configuration the checker cannot parse is found now, rather than by the
    slice that installs the first gate there and has to debug it.
    """
    for name, suite in programme.suites.items():
        collection = Collection.from_config(
            REPO_ROOT / suite.config if suite.config else None)
        assert collection.python_files, name
        assert collection.python_functions, name

    # The exclusion this checker exists to be able to see: the platform suite
    # keeps `conformance` out of the default run, so a gate hosted there would
    # be listed, collected by nothing, and green.
    platform = Collection.from_config(REPO_ROOT / "ubb-platform" / "pytest.ini")
    assert "conformance" in platform.norecursedirs


def test_the_declared_inventory_is_adr_0008_section_8(programme):
    """The inventory lives in `schema.yaml` rather than in the compiler, so
    amending it is a reviewable diff that makes CI demand the matching row."""
    declared = yaml.safe_load(real("schema.yaml"))["gate_inventory"]
    assert declared == [f"G{number}" for number in range(1, 28)]


# ---------------------------------------------------------------------------
# 2. `installed` means running — negative controls
# ---------------------------------------------------------------------------

def test_a_row_claiming_a_test_that_does_not_exist_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed(
        [{"suite": "contracts", "node": f"{TEST_FILE}::test_imaginary"}])))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}


def test_a_row_claiming_a_skipped_test_is_rejected(tmp_path):
    """The failure this manifest exists to catch, in its cheapest form: a gate
    listed as installed that pytest collects and then does not run."""
    invalid = rejection(tmp_path, gates=gates(G1=installed(
        [{"suite": "contracts", "node": f"{TEST_FILE}::test_skipped"}])))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}
    assert any("marked skip" in error.message for error in invalid.errors)


def test_a_row_claiming_a_file_the_suite_excludes_is_rejected(tmp_path):
    """`ubb-platform/pytest.ini` excludes `conformance` from the default run.
    A gate hosted there would be listed, collected by nothing, and green."""
    invalid = rejection(
        tmp_path,
        suites=suites(contracts={"summary": "s", "job": "contracts",
                                 "step": "Contract suite", "root": SUITE_ROOT,
                                 "config": "pytest.ini"}),
        files={"pytest.ini": "[pytest]\nnorecursedirs = excluded\n",
               f"{SUITE_ROOT}/excluded/test_hidden.py":
                   "def test_hidden():\n    assert True\n"},
        gates=gates(G1=installed([{
            "suite": "contracts",
            "node": f"{SUITE_ROOT}/excluded/test_hidden.py::test_hidden"}])))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}
    assert any("norecursedirs" in error.message for error in invalid.errors)


def test_a_row_claiming_a_file_addopts_ignores_is_rejected(tmp_path):
    invalid = rejection(
        tmp_path,
        suites=suites(contracts={"summary": "s", "job": "contracts",
                                 "step": "Contract suite", "root": SUITE_ROOT,
                                 "config": "pytest.ini"}),
        files={"pytest.ini":
                   f"[pytest]\naddopts = --ignore={SUITE_ROOT}/skipped\n",
               f"{SUITE_ROOT}/skipped/test_hidden.py":
                   "def test_hidden():\n    assert True\n"},
        gates=gates(G1=installed([{
            "suite": "contracts",
            "node": f"{SUITE_ROOT}/skipped/test_hidden.py::test_hidden"}])))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}
    assert any("--ignore" in error.message for error in invalid.errors)


def test_a_row_claiming_a_file_pytest_never_collects_is_rejected(tmp_path):
    """A perfectly good assertion in a file named so pytest walks past it."""
    invalid = rejection(
        tmp_path,
        files={f"{SUITE_ROOT}/checks.py": "def test_thing():\n    assert True\n"},
        gates=gates(G1=installed([{
            "suite": "contracts",
            "node": f"{SUITE_ROOT}/checks.py::test_thing"}])))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}
    assert any("python_files" in error.message for error in invalid.errors)


@pytest.mark.parametrize("disarm", [
    {"continue-on-error": True},
    {"if": "github.ref == 'refs/heads/main'"},
])
def test_a_row_in_a_disarmed_job_is_rejected(tmp_path, disarm):
    workflow = workflow_document()
    workflow["jobs"]["contracts"].update(disarm)
    invalid = rejection(tmp_path, workflow=workflow,
                        gates=gates(G1=installed()))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}


@pytest.mark.parametrize("disarm", [
    {"continue-on-error": True},
    {"if": "github.event_name == 'schedule'"},
])
def test_a_row_naming_a_disarmed_step_is_rejected(tmp_path, disarm):
    """The `conformance` sweep's exact shape: a step whose findings annotate the
    run and can never turn a pull request red."""
    workflow = workflow_document()
    workflow["jobs"]["checks"]["steps"][0].update(disarm)
    invalid = rejection(tmp_path, workflow=workflow, gates=gates(
        G1=installed([{"job": "checks", "step": "Named step"}])))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}


def test_a_row_naming_a_step_that_does_not_exist_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(
        G1=installed([{"job": "checks", "step": "A step nobody wrote"}])))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}


def test_a_path_filtered_workflow_disarms_every_gate(tmp_path):
    """#158 §16's hazard: a filter listing six inputs and not the seventh."""
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        workflow=workflow_document(**{
                            "on": {"push": {"paths": ["ubb-platform/**"]},
                                   "pull_request": None}}))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}
    assert any("paths" in error.message for error in invalid.errors)


def test_a_workflow_that_does_not_run_on_pull_requests_disarms_every_gate(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed()),
                        workflow=workflow_document(**{"on": {"push": None}}))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}


def test_a_row_naming_a_suite_the_manifest_does_not_declare_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed(
        [{"suite": "imaginary", "node": TEST_NODE}])))
    assert invalid.codes() == {codes.UNKNOWN_SUITE}


def test_a_declared_suite_is_verified_even_when_no_gate_names_it(tmp_path):
    """Declaring a suite is a claim, not a convenience: it must be armed even
    while every gate that will use it is still owed."""
    invalid = rejection(tmp_path, suites=suites(
        platform={"summary": "s", "job": "test", "step": "Platform test suite",
                  "root": SUITE_ROOT}))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}


def test_a_suite_whose_root_is_not_in_the_repository_is_rejected(tmp_path):
    invalid = rejection(tmp_path, suites=suites(
        contracts={"summary": "s", "job": "contracts", "step": "Contract suite",
                   "root": "nowhere"}))
    assert invalid.codes() == {codes.SUITE_ROOT_MISSING}


def test_a_suite_whose_declared_config_is_absent_is_rejected(tmp_path):
    invalid = rejection(tmp_path, suites=suites(
        contracts={"summary": "s", "job": "contracts", "step": "Contract suite",
                   "root": SUITE_ROOT, "config": "nowhere/pytest.ini"}))
    assert invalid.codes() == {codes.SUITE_CONFIG_MISSING}


def test_a_disarmed_job_is_blamed_once_however_many_gates_name_it(tmp_path):
    """One cause, one error. A `continue-on-error` job is the suite's fault, and
    repeating it for every gate that names the suite buries the other faults in
    a run — which is how a reader stops reading the list."""
    workflow = workflow_document()
    workflow["jobs"]["contracts"]["continue-on-error"] = True
    invalid = rejection(tmp_path, workflow=workflow,
                        gates=gates(G1=installed(), G2=installed(),
                                    G3=installed()))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}
    assert len(invalid.errors) == 1, "the same cause was reported more than once"


def test_deleting_a_test_the_real_manifest_names_turns_ci_red(tmp_path):
    """The same control against the SHIPPED manifest, so it is the real rows
    being defended rather than a synthetic stand-in."""
    gates_dir = copy_real_programme(tmp_path)
    manifest = yaml.safe_load((gates_dir / "manifest.yaml").read_text("utf-8"))
    node = next(site["node"]
                for row in manifest["gates"].values()
                for site in row.get("enforced_by") or []
                if "node" in site)
    (tmp_path / node.split("::")[0]).unlink()

    with pytest.raises(GatesInvalid) as raised:
        load_programme(gates_dir, tmp_path)
    assert codes.GATE_NOT_RUNNING in raised.value.codes()


# ---------------------------------------------------------------------------
# 3. Statuses, shapes and the inventory — negative controls
# ---------------------------------------------------------------------------

def test_an_unknown_status_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=owned(status="probably_fine")))
    assert invalid.codes() == {codes.UNKNOWN_STATUS}


def test_a_status_naming_a_slice_that_does_not_exist_is_rejected(tmp_path):
    """"Every `owned_by_slice_N` names a real slice" is true by construction:
    the status vocabulary is derived from `slices.yaml`."""
    invalid = rejection(tmp_path, gates=gates(G1=owned("slice_99")))
    assert invalid.codes() == {codes.UNKNOWN_STATUS}


def test_an_owed_row_that_does_not_say_what_must_exist_first_is_rejected(tmp_path):
    body = owned()
    del body["blocked_on"]
    invalid = rejection(tmp_path, gates=gates(G1=body))
    assert invalid.codes() == {codes.MISSING_FIELD}


def test_an_installed_row_that_names_nowhere_is_rejected(tmp_path):
    body = installed()
    del body["enforced_by"]
    invalid = rejection(tmp_path, gates=gates(G1=body))
    assert invalid.codes() == {codes.MISSING_FIELD}


def test_an_installed_row_with_an_empty_enforcement_list_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed([])))
    assert invalid.codes() == {codes.ENFORCEMENT_EMPTY}


def test_an_installed_row_that_is_also_blocked_is_rejected(tmp_path):
    """Two statuses at once, spelled as one status plus the other's field."""
    invalid = rejection(tmp_path, gates=gates(
        G1=installed(blocked_on="something that does not exist")))
    assert invalid.codes() == {codes.FORBIDDEN_FIELD}


def test_an_enforcement_entry_of_no_known_kind_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed(
        [{"suite": "contracts", "step": "Contract suite"}])))
    assert invalid.codes() == {codes.UNKNOWN_ENFORCEMENT_KIND}


def test_a_row_carrying_a_field_the_schema_declares_nowhere_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=owned(probably="fine")))
    assert invalid.codes() == {codes.UNKNOWN_FIELD}


def test_a_row_missing_its_statement_is_rejected(tmp_path):
    body = owned()
    del body["statement"]
    invalid = rejection(tmp_path, gates=gates(G1=body))
    assert invalid.codes() == {codes.MISSING_FIELD}


def test_a_blank_oracle_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=owned(oracle="   ")))
    assert invalid.codes() == {codes.INVALID_FIELD_TYPE}


def test_a_deferred_obligation_missing_its_owner_is_rejected(tmp_path):
    body = obligation()
    del body["owner_role"]
    invalid = rejection(tmp_path, obligations={"O1": body})
    assert invalid.codes() == {codes.MISSING_FIELD}


def test_a_gate_dropped_from_the_manifest_is_rejected(tmp_path):
    rows = gates()
    del rows["G13"]
    invalid = rejection(tmp_path, gates=rows)
    assert invalid.codes() == {codes.INVENTORY_MISMATCH}
    assert any("G13" in error.message for error in invalid.errors)


def test_a_gate_the_inventory_does_not_declare_is_rejected(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G28=owned()))
    assert invalid.codes() == {codes.INVENTORY_MISMATCH}


def test_a_landed_slice_may_not_still_owe_a_gate(tmp_path):
    """The manifest's half of #155 §17: a slice cannot land owing an
    installation it never did, and this is what says so."""
    slices = yaml.safe_load(real("slices.yaml"))
    slices["slices"]["slice_0"]["landed"] = True
    invalid = rejection(tmp_path, slices=slices)
    assert invalid.codes() == {codes.LANDED_SLICE_OWNS_GATE}


def test_a_duplicate_key_in_the_manifest_is_rejected(tmp_path):
    """PyYAML's `safe_load` keeps the last of two identical keys. For a manifest
    whose point is that every gate is accounted for exactly once, silently
    dropping one is the worst possible default."""
    invalid = rejection(tmp_path, manifest=(
        "version: 1\n"
        "gates:\n"
        "  G1:\n    statement: a\n    oracle: b\n    status: installed\n"
        "  G1:\n    statement: c\n    oracle: d\n    status: installed\n"))
    assert invalid.codes() == {codes.DUPLICATE_KEY}


def test_a_missing_gates_file_is_rejected_by_name(tmp_path):
    gates_dir = tmp_path / "gates"
    gates_dir.mkdir()
    with pytest.raises(GatesInvalid) as raised:
        load_programme(gates_dir, tmp_path)
    assert raised.value.codes() == {codes.GATES_MISSING}
    assert len(raised.value.errors) == 5, "each missing file is named"


def test_a_workflow_that_cannot_be_read_is_rejected(tmp_path):
    invalid = rejection(tmp_path, workflow="{{ not: yaml ]")
    assert codes.WORKFLOW_INVALID in invalid.codes()


def test_a_file_the_gates_directory_would_not_carry_is_rejected(tmp_path):
    """No ignored category. A file here that nothing reads is either a document
    somebody believes is enforced and is not, or a mislaid one."""
    invalid = rejection(tmp_path, files={"gates/notes.yaml": "entries: []\n"})
    assert invalid.codes() == {codes.UNEXPECTED_FILE}


def test_the_readme_beside_the_gates_is_not_gate_content(tmp_path):
    """The reasoning has to live somewhere, and beside the data is the right
    place — so the rule above must not make it an error."""
    load(tmp_path, files={"gates/README.md": "# why\n"})


# ---------------------------------------------------------------------------
# 4. Positive controls — the legal constructions must keep passing
# ---------------------------------------------------------------------------

def test_a_legal_programme_of_both_enforcement_kinds_loads(tmp_path):
    programme = load(tmp_path, gates=gates(
        G1=installed([{"suite": "contracts", "node": TEST_NODE},
                      {"job": "checks", "step": "Named step"}])))
    assert programme.gates["G1"].installed
    assert {site.kind for site in programme.gates["G1"].sites} == {
        "suite_node", "workflow_step"}


def test_a_test_inside_a_class_is_collected(tmp_path):
    """pytest collects `TestThings::test_in_a_class`, so the manifest must too —
    a checker that only looked at module scope would call a real gate missing."""
    programme = load(tmp_path, gates=gates(G1=installed(
        [{"suite": "contracts", "node": f"{TEST_FILE}::test_in_a_class"}])))
    assert programme.gates["G1"].installed


def test_a_helper_that_is_not_a_test_is_not_accepted_as_one(tmp_path):
    invalid = rejection(tmp_path, gates=gates(G1=installed(
        [{"suite": "contracts", "node": f"{TEST_FILE}::helper_not_a_test"}])))
    assert invalid.codes() == {codes.GATE_NOT_RUNNING}
    assert any("python_functions" in error.message for error in invalid.errors)


def test_an_explicitly_false_continue_on_error_is_not_read_as_set(tmp_path):
    workflow = workflow_document()
    workflow["jobs"]["contracts"]["continue-on-error"] = False
    programme = load(tmp_path, workflow=workflow, gates=gates(G1=installed()))
    assert programme.gates["G1"].installed


def test_owner_slice_of_reads_only_the_owned_family():
    assert owner_slice_of("owned_by_slice_4") == "slice_4"
    assert owner_slice_of("installed") is None
    assert owner_slice_of("deferred_obligation") is None
