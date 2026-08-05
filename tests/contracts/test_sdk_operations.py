"""The SDK's call surface agrees with the committed contract, both ways (#204).

G17 and G18 in `gates/manifest.yaml`, from ADR-0007 §4 and #155 §8.2. Two
properties, settled from one join:

- **Forward** — every hand-written call targets a published operation, matched
  on the complete identity: HTTP method AND normalised path. A path match alone
  is insufficient, because `GET /x/{id}` is not `POST /x/{id}`.
- **Reverse** — every published operation carries a disposition in
  `ubb-sdk/operation-coverage.yaml`, which regenerates with zero diff.

#155 §8.5 names six cases CI must prove and calls them not negotiable. They are
section 2 below, one test each, in its order. Section 3 carries the controls for
the rules this gate adds beyond them; section 4 is the ratchet.

**Why this suite and not `ubb-sdk/tests/`.** The gate reads source with `ast`
and never imports the client, so it needs no `httpx` and no running server —
and the thing it checks is agreement *between* the SDK and the contract, which
is what this suite is for. It also means the ledger is read directly rather
than mirrored: unlike #203's model-naming gates, which run in the platform suite
and therefore need `test_model_naming_ledger_agreement.py` to hold two
encodings together, there is exactly one copy of the excused-call list here.

**Why no mock, said plainly.** Three SDK methods called routes that existed in
no spec and no router, and were green for months, *because their tests patched
the HTTP client*. Every control below builds a real repository on disk and runs
the real entry point over it.
"""

import json

import pytest
import yaml

from _gate_helpers import git
from _helpers import REPO_ROOT
from _sdk_helpers import (
    ROOT, THING_LIST, THING_READ, THING_WRITE, client_module, excusing,
    interpolated, literal, spec, write_repository,
)
from tools.sdk_operations import SurfaceInvalid, assess, load_coverage
from tools.sdk_operations import errors as codes
from tools.sdk_operations.coverage import (
    DISPOSITIONS, GENERATED_ONLY, LEDGER_PATH, NOT_YET_WRAPPED, WRAPPED,
)
from tools.sdk_operations.calls import SHELL_ROOT
from tools.sdk_operations.manifest import MANIFEST_PATH, compare, render
from tools.sdk_operations.ratchet import AUTHORISATIONS_PATH
from tools.sdk_operations.ratchet import compare as ratchet_compare
from tools.sdk_operations.ratchet import run as ratchet_run
from tools.sdk_operations.spec import SPEC_PATH

#: The modules the walker must have visited. A vacuity guard names them because
#: a walker that silently found nothing passes every assertion below.
HAND_WRITTEN_MODULES = ("billing.py", "client.py", "metering.py",
                        "referrals.py", "subscriptions.py")

#: The faults that mean a call did not resolve. Named as a set so the forward
#: test asserts on the property rather than on "no errors at all", which would
#: also go red for a stale manifest and say the wrong thing about why.
FORWARD_FAULTS = frozenset({
    codes.NO_SUCH_OPERATION, codes.CALL_NOT_LITERAL, codes.CALL_MALFORMED,
    codes.STRAY_ROUTE_LITERAL, codes.UNSCANNED_PACKAGE, codes.SHELL_MISSING,
    codes.SHELL_EMPTY, codes.SHELL_UNREADABLE,
})


@pytest.fixture(scope="module")
def shipped():
    """The gate's verdict on the tree as committed."""
    return assess(REPO_ROOT)


def rejection(tmp_path, **kwargs):
    """Build a synthetic repository and return the :class:`SurfaceInvalid` it
    must raise. Fails the test if it loads — which is the shape that makes
    these negative controls, rather than assertions about a passing run."""
    write_repository(tmp_path, **kwargs)
    return refusal(tmp_path)


def refusal(repo_root):
    """The same, for a repository a control has already mutated on disk."""
    with pytest.raises(SurfaceInvalid) as raised:
        load_coverage(repo_root)
    return raised.value


def accepted(tmp_path, **kwargs):
    """Build a synthetic repository and return the coverage it must produce.

    Through `load_coverage`, the entry point the CLI and CI call, so a passing
    control passes for the reason a passing build would.
    """
    write_repository(tmp_path, **kwargs)
    return load_coverage(tmp_path)


def disposition_of(coverage, operation_id):
    for row in coverage.rows:
        if row.operation_id == operation_id:
            return row
    raise AssertionError(f"{operation_id} has no row at all")


# ---------------------------------------------------------------------------
# 1. The shipped tree
# ---------------------------------------------------------------------------

def test_every_hand_written_call_targets_a_published_operation(shipped):
    """G17. Every call in `ubb-sdk/ubb/*.py` resolves, or the ledger owes it."""
    coverage, errors = shipped
    unresolved = [error for error in errors if error.code in FORWARD_FAULTS]
    assert not unresolved, (
        "\n" + "\n".join(str(error) for error in unresolved)
        + f"\n\nA call that cannot be resolved is either wrong or must be "
          f"recorded in {LEDGER_PATH} against G17, owned by the slice that "
          f"removes it.")

    # What the excused calls ARE is the ledger's business, held to the gate by
    # `test_the_ledger_records_exactly_what_the_gate_excuses` below and to the
    # base branch by the ratchet. Naming the three here as well would be a
    # third copy that goes stale the day slice 4 pays one of them.
    assert len(coverage.excused) <= 3, (
        f"{len(coverage.excused)} invalid calls are excused and #155 §1.3 "
        f"found three. The list only shrinks and reaches zero before the "
        f"cutover.")


def test_every_published_operation_carries_a_disposition(shipped):
    """G18. One row per published operation, each classified from evidence."""
    coverage, errors = shipped
    assert not errors, (
        "\n" + "\n".join(str(error) for error in errors)
        + "\n\nThe rows below are derived from the contract and the SDK's "
          "source. If either did not read cleanly they describe nothing, so "
          "this asserts the read before asserting anything about the result.")

    published = json.loads((REPO_ROOT / SPEC_PATH).read_text(encoding="utf-8"))
    expected = sum(1 for item in published["paths"].values()
                   for method in item
                   if method in ("get", "put", "post", "delete", "patch"))
    assert len(coverage.rows) == expected, (
        f"{len(coverage.rows)} rows for {expected} published operations")

    for row in coverage.rows:
        assert row.disposition in DISPOSITIONS, (
            f"{row.operation_id} carries `{row.disposition}`, which is not one "
            f"of ADR-0007 §4's three")
        assert bool(row.wrapped_by) == row.is_wrapped, (
            f"{row.operation_id} is `{row.disposition}` and names "
            f"{row.wrapped_by} as its wrappers — the two cannot both be true")

    counts = coverage.counts()
    assert sum(counts.values()) == len(coverage.rows)
    assert coverage.unwrapped == counts[GENERATED_ONLY] + counts[NOT_YET_WRAPPED]


def test_the_coverage_manifest_regenerates_with_zero_diff(shipped):
    """G18's accuracy half: the committed bytes are what the tree produces."""
    coverage, _ = shipped
    stale, _ = compare(coverage, REPO_ROOT)
    assert stale is None, str(stale)


def test_every_excused_invalid_call_is_still_a_real_violation(shipped):
    """A seeded debt cannot outlive the violation it records.

    `assess` reports an excuse nothing matches, so paying a debt and deleting
    its entry are one act. Without this, the ledger would keep suppressing a
    call that had already been fixed — a suppression the ratchet cannot see,
    because removing an entry is always allowed and adding one back is not.
    """
    _, errors = shipped
    stale = [error for error in errors
             if error.code == codes.EXCUSE_NOT_A_VIOLATION]
    assert not stale, "\n" + "\n".join(str(error) for error in stale)


def test_the_ledger_records_exactly_what_the_gate_excuses(shipped):
    """The ledger's G17 entries and the gate's excuses are the same list.

    Both directions. An entry the gate never used is caught above; this catches
    the reverse — a call the gate excused that the ledger does not carry, which
    could only happen if the reader silently widened.
    """
    coverage, _ = shipped
    document = yaml.safe_load((REPO_ROOT / LEDGER_PATH).read_text("utf-8"))
    recorded = {(entry["site"], entry["found"])
                for entry in document["entries"] if entry["gate"] == "G17"}
    assert set(coverage.excused) == recorded
    assert len(recorded) <= 3, (
        f"{len(recorded)} G17 debts, and #155 §1.3 found three. Adding one is "
        f"refused by the ledger ratchet without a seeding authorisation; this "
        f"catches the case where the authorisation was written anyway.")


def test_the_walker_visited_the_whole_hand_written_surface(shipped):
    """Vacuity guard: a gate that walks nothing passes everything.

    Names the modules and a floor on the calls, so a glob that stops matching —
    or a hand shell moved into a package — turns this red rather than quietly
    reporting a clean surface with nothing in it.
    """
    coverage, _ = shipped
    wrapped = [row for row in coverage.rows if row.is_wrapped]
    sites = {site for row in wrapped for site in row.wrapped_by}
    modules = {site.split("::")[0] for site in sites}

    assert modules >= {f"{SHELL_ROOT}/{name}" for name in HAND_WRITTEN_MODULES}, (
        f"the walker resolved calls in {sorted(modules)} and one of the five "
        f"known clients is missing — a glob that stopped matching reports a "
        f"clean surface rather than an empty one")
    assert len(sites) >= 70, (
        f"only {len(sites)} resolved call sites; #155 §1.3 counted 105 route "
        f"references across the hand shell, so a number this low means the "
        f"walker stopped seeing most of them")
    assert len(coverage.rows) > 100, "suspect the contract read"


def test_the_dead_calls_are_owed_by_the_slice_that_replaces_them():
    """The debts name slice 4 — where the Pricing Book lands.

    `tools.gates` already enforces the general rule that an entry names a real,
    unlanded slice, and its ratchet already refuses an owner moving later. What
    this adds is the *specific* owner: these three are the ergonomics for the
    rate-card surface, and slice 4 is what replaces it. An entry drifting onto
    some other slice would satisfy every general rule and still be owed by
    somebody who is not doing the work — #155 §17's failure with a nicer label.
    """
    ledger = yaml.safe_load((REPO_ROOT / LEDGER_PATH).read_text("utf-8"))
    owners = {entry["owner_slice"] for entry in ledger["entries"]
              if entry["gate"] == "G17"}
    assert owners <= {"slice_4"}, (
        f"a G17 debt is owed by {sorted(owners - {'slice_4'})}. It may move "
        f"EARLIER — any slice rewriting the SDK's pricing methods may take it "
        f"— but slice 4 is the last slice that can pay it, because that is "
        f"where the surface it calls stops existing.")


# ---------------------------------------------------------------------------
# 2. #155 §8.5's six cases, in its order
# ---------------------------------------------------------------------------

def test_case_1_a_nonexistent_route_fails(tmp_path):
    invalid = rejection(tmp_path, modules={
        "things.py": client_module(("get", literal(f"{ROOT}/nowhere"))),
    })
    assert codes.NO_SUCH_OPERATION in invalid.codes()
    assert any("/nowhere" in error.message for error in invalid.errors)


def test_case_2_a_valid_path_with_the_wrong_method_fails(tmp_path):
    """ADR-0007 §4's own example. The path exists; the method does not.

    The message must name the method that IS published, because this is the
    failure a reader is likeliest to misread as "the route is wrong".
    """
    invalid = rejection(tmp_path, operations=(THING_LIST,), modules={
        "things.py": client_module(("post", literal(f"{ROOT}/things"))),
    })
    faults = [error for error in invalid.errors
              if error.code == codes.NO_SUCH_OPERATION]
    assert len(faults) == 1
    assert f"GET {ROOT}/things" in faults[0].message


def test_case_3_a_renamed_operation_with_a_stale_wrapper_fails(tmp_path):
    """The wrapper is untouched; the contract moved under it.

    Built as a genuine before-and-after so the rename is what breaks it. A
    control that only asserted the "after" would be case 1 again wearing a
    different name, and would still pass if the gate had never resolved the
    call in the first place.
    """
    before = tmp_path / "before"
    after = tmp_path / "after"
    wrapper = {"things.py": client_module(("get", literal(f"{ROOT}/things")))}

    coverage = accepted(before, operations=(THING_LIST,), modules=wrapper)
    assert disposition_of(coverage, "things_list").disposition == WRAPPED

    renamed = ("get", f"{ROOT}/widgets", "things_list")
    invalid = rejection(after, operations=(renamed,), modules=wrapper)
    assert codes.NO_SUCH_OPERATION in invalid.codes()


def test_case_4_a_new_operation_absent_from_the_manifest_fails(tmp_path):
    """The manifest was generated before the operation existed."""
    stale_text = render(accepted(tmp_path / "before",
                                 operations=(THING_LIST,),
                                 modules={"things.py": client_module()}))

    write_repository(tmp_path / "after", operations=(THING_LIST, THING_READ),
                     modules={"things.py": client_module()},
                     manifest=stale_text)
    coverage, errors = assess(tmp_path / "after")
    assert not errors, "the tree itself is fine; only the manifest is stale"

    difference, _ = compare(coverage, tmp_path / "after")
    assert difference is not None
    assert difference.code == codes.MANIFEST_DIFFERS


def test_case_5_a_deliberate_gap_passes_and_stays_visible(tmp_path):
    """Both kinds of gap: reachable through the generated client, and not.

    "Passes and remains visible" is two claims, so both are asserted — the load
    succeeds AND the operation has a row naming its disposition. A gate that
    passed by dropping the row would satisfy the first and defeat the point.
    """
    coverage = accepted(
        tmp_path,
        operations=(THING_LIST, THING_READ, THING_WRITE),
        # `things_write` has no generated module: unreachable by any route.
        generated=("things_list", "things_read"),
        modules={"things.py": client_module(("get", literal(f"{ROOT}/things")))})

    assert disposition_of(coverage, "things_list").disposition == WRAPPED
    assert disposition_of(coverage, "things_read").disposition == GENERATED_ONLY
    assert disposition_of(coverage, "things_write").disposition == NOT_YET_WRAPPED
    assert coverage.unwrapped == 2

    text = render(coverage)
    for operation_id in ("things_read", "things_write"):
        assert f"operation_id: {operation_id}" in text, (
            f"{operation_id} is unwrapped and vanished from the manifest — "
            f"a gap nobody can see is not a declared gap")


def test_case_6_a_correctly_mapped_wrapper_passes(tmp_path):
    """Including an interpolated path, which is how 39 of the real calls read."""
    coverage = accepted(tmp_path, modules={
        "things.py": client_module(
            ("get", literal(f"{ROOT}/things")),
            ("get", interpolated(f"{ROOT}/things/{{}}")),
        )})

    assert disposition_of(coverage, "things_list").disposition == WRAPPED
    assert disposition_of(coverage, "things_read").wrapped_by == (
        f"{SHELL_ROOT}/things.py::ThingsClient.call_1",)
    assert coverage.unwrapped == 0


# ---------------------------------------------------------------------------
# 3. The rules this gate adds beyond the six
# ---------------------------------------------------------------------------

def test_a_route_spelled_outside_a_readable_call_is_refused(tmp_path):
    """The conjunct that makes the forward check honest.

    Without it the gate reads only `_request`-shaped calls, and
    `self._http.get("/api/v1/...")` is a route it never sees — a hole an author
    could fall into without meaning to, and step through on purpose.
    """
    invalid = rejection(tmp_path, modules={"things.py": client_module(
        extra=f'\n\ndef sneak(client):\n'
              f'    return client._http.get("{ROOT}/things")\n')})
    assert codes.STRAY_ROUTE_LITERAL in invalid.codes()


def test_a_docstring_naming_a_route_is_prose_and_not_a_call(tmp_path):
    """The other side of that rule, and the reason it needs one.

    Every real client method documents the route it calls. Treating those as
    unaccounted routes would make the gate unusable on the day it shipped —
    which is how a gate ends up with an exclusion list nobody can read.
    """
    coverage = accepted(tmp_path, operations=(THING_LIST,), modules={
        "things.py": client_module(
            ("get", literal(f"{ROOT}/things")),
            extra=f'\n\ndef documented():\n'
                  f'    """Wraps GET {ROOT}/things, and calls nothing."""\n'
                  f'    return None\n')})
    assert coverage.unwrapped == 0


def test_a_computed_path_is_refused_rather_than_skipped(tmp_path):
    """A call this gate cannot read is not a call it can vouch for.

    Skipping it would make the gate optional: anyone who assembles a route from
    a variable would be exempt, and the exemption would be invisible.
    """
    invalid = rejection(tmp_path, modules={"things.py": client_module(
        extra='\n\nclass Sneaky:\n'
              '    def _request(self, method, path, **kwargs): ...\n\n'
              '    def go(self, route):\n'
              '        return self._request("get", route)\n')})
    assert codes.CALL_NOT_LITERAL in invalid.codes()


def test_a_computed_method_is_refused_too(tmp_path):
    """Half an identity is not an identity. The path alone cannot decide."""
    invalid = rejection(tmp_path, modules={"things.py": client_module(
        extra=f'\n\nclass Sneaky:\n'
              f'    def _request(self, method, path, **kwargs): ...\n\n'
              f'    def go(self, verb):\n'
              f'        return self._request(verb, "{ROOT}/things")\n')})
    assert codes.CALL_NOT_LITERAL in invalid.codes()


def test_a_keyword_spelled_call_is_read_the_same_way(tmp_path):
    """`_request(method="get", path=...)` is the same call, and must resolve.

    A positional-only reader would report this as malformed and send an author
    looking for a bug in their route.
    """
    coverage = accepted(tmp_path, operations=(THING_LIST,), modules={
        "things.py": client_module(
            extra=f'\n\nclass Keyword:\n'
                  f'    def _request(self, method, path, **kwargs): ...\n\n'
                  f'    def go(self):\n'
                  f'        return self._request(method="get", '
                  f'path="{ROOT}/things")\n')})
    assert disposition_of(coverage, "things_list").wrapped_by == (
        f"{SHELL_ROOT}/things.py::Keyword.go",)


def test_a_new_sub_package_is_refused_rather_than_unwalked(tmp_path):
    """Only the generated client is exempt, and only because G16 regenerates it.

    Hand-written ergonomics moved into a folder would otherwise leave the gate
    silently. An exclusion nobody can see is how the sweep that shipped
    `continue-on-error` looked from the board.
    """
    write_repository(tmp_path, modules={"things.py": client_module()})
    ergonomics = tmp_path / SHELL_ROOT / "ergonomics"
    ergonomics.mkdir()
    (ergonomics / "__init__.py").write_text("", encoding="utf-8")

    assert codes.UNSCANNED_PACKAGE in refusal(tmp_path).codes()


def test_an_excused_call_that_changed_its_route_is_no_longer_excused(tmp_path):
    """#203's correction, applied here.

    Keyed on the site alone, a dead method rewritten to call a DIFFERENT
    nonexistent route would stay excused by an entry describing the old one,
    and the ledger would look like it was doing its job. The key carries the
    route, so the excuse stops covering it.
    """
    site = f"{SHELL_ROOT}/things.py::ThingsClient.call_0"
    excuse = excusing((site, f"GET {ROOT}/gone"))

    coverage = accepted(tmp_path / "matching", ledger=excuse, modules={
        "things.py": client_module(("get", literal(f"{ROOT}/gone")))})
    assert coverage.excused == ((site, f"GET {ROOT}/gone"),)

    invalid = rejection(tmp_path / "moved", ledger=excuse, modules={
        "things.py": client_module(("get", literal(f"{ROOT}/somewhere-else")))})
    reported = invalid.codes()
    assert codes.NO_SUCH_OPERATION in reported, "the new bad route must be caught"
    assert codes.EXCUSE_NOT_A_VIOLATION in reported, (
        "and the entry describing the old one must be reported as spent")


def test_an_excuse_for_a_call_that_now_resolves_is_reported(tmp_path):
    """Paying a debt and deleting its entry are one act."""
    invalid = rejection(
        tmp_path,
        operations=(THING_LIST,),
        ledger=excusing((f"{SHELL_ROOT}/things.py::ThingsClient.call_0",
                         f"GET {ROOT}/things")),
        modules={"things.py": client_module(("get", literal(f"{ROOT}/things")))})
    assert codes.EXCUSE_NOT_A_VIOLATION in invalid.codes()


def test_two_paths_the_gate_cannot_tell_apart_are_refused(tmp_path):
    """The premise of collapsing `{param}` to `{}`, checked rather than trusted.

    OpenAPI forbids two paths differing only in parameter name, so this should
    be unreachable — which is exactly why it is asserted. If it ever happened,
    a call to either would silently resolve against the other and the manifest
    would credit the wrong operation.
    """
    invalid = rejection(tmp_path, operations=(
        ("get", f"{ROOT}/things/{{thing_id}}", "things_read"),
        ("get", f"{ROOT}/things/{{other_id}}", "things_read_again"),
    ), modules={"things.py": client_module()})
    assert codes.TEMPLATE_COLLISION in invalid.codes()


def test_a_contract_published_outside_the_route_marker_is_refused(tmp_path):
    """The stray-literal sweep's own premise.

    `ROUTE_MARKER` decides which strings in the hand shell are routes. A
    contract that published outside it would exempt a whole family of routes
    from the sweep with no diff anywhere — a gate narrowing in silence, which
    is the failure this programme exists to refuse.
    """
    invalid = rejection(tmp_path, operations=(("get", "/v2/things", "v2_list"),),
                        modules={"things.py": client_module()})
    assert codes.ROUTE_MARKER_STALE in invalid.codes()


def test_a_generated_client_with_no_modules_fails(tmp_path):
    """Rather than reporting every operation as unreachable.

    That would describe a missing directory as an SDK with no reach — a
    catastrophe-shaped manifest for a one-line bug, and the sort of false
    signal that gets a gate turned off.
    """
    write_repository(tmp_path, generated=(),
                     modules={"things.py": client_module()})
    assert codes.GENERATED_CLIENT_EMPTY in refusal(tmp_path).codes()


def test_a_missing_contract_fails_rather_than_reporting_a_clean_surface(tmp_path):
    """Reading zero operations must never look like agreement."""
    write_repository(tmp_path, modules={"things.py": client_module()})
    (tmp_path / SPEC_PATH).unlink()
    assert codes.SPEC_MISSING in refusal(tmp_path).codes()


def test_a_missing_hand_shell_fails_rather_than_reporting_a_clean_surface(tmp_path):
    """And neither must walking zero modules."""
    write_repository(tmp_path, modules={"things.py": client_module()})
    (tmp_path / SHELL_ROOT / "things.py").unlink()
    assert codes.SHELL_EMPTY in refusal(tmp_path).codes()


def test_the_manifest_renders_the_same_bytes_twice(tmp_path):
    """Determinism, because a zero-diff gate over an unstable renderer fails at
    random — and a gate that cries wolf gets disabled rather than obeyed."""
    coverage = accepted(tmp_path, modules={
        "things.py": client_module(
            ("get", literal(f"{ROOT}/things")),
            ("get", interpolated(f"{ROOT}/things/{{}}")),
        )})
    assert render(coverage) == render(coverage)
    assert render(coverage).endswith("\n")


def test_a_missing_manifest_is_a_different_fault_from_a_stale_one(tmp_path):
    """"No differences found" must never be what a deleted manifest looks like."""
    coverage = accepted(tmp_path, modules={"things.py": client_module()})
    missing, _ = compare(coverage, tmp_path)
    assert missing is not None and missing.code == codes.MANIFEST_MISSING


# ---------------------------------------------------------------------------
# 4. The ratchet: the unwrapped count only falls
# ---------------------------------------------------------------------------

def manifest_document(unwrapped):
    return {"version": 1, "summary": {"operations": 10, "unwrapped": unwrapped}}


def authorisations(*entries):
    return {"version": 1, "authorisations": [
        {"id": identifier, "issue": 204, "operations_added": count,
         "reason": "a synthetic authorisation."}
        for identifier, count in entries]}


def test_a_rise_with_no_authorisation_is_refused():
    comparison = ratchet_compare(manifest_document(2), manifest_document(3),
                                 authorisations(), authorisations())
    assert not comparison.ok
    assert comparison.faults[0].code == codes.UNWRAPPED_ROSE


def test_a_rise_licensed_by_a_new_authorisation_is_allowed():
    comparison = ratchet_compare(manifest_document(2), manifest_document(3),
                                 authorisations(), authorisations(("new", 1)))
    assert comparison.ok, [str(fault) for fault in comparison.faults]
    assert comparison.rise == 1


def test_an_authorisation_carried_over_from_the_base_licenses_nothing():
    """Otherwise the file is standing permission wearing an audit trail's clothes."""
    old = authorisations(("already-there", 5))
    comparison = ratchet_compare(manifest_document(2), manifest_document(3),
                                 old, old)
    assert not comparison.ok
    assert comparison.faults[0].code == codes.UNWRAPPED_ROSE


def test_an_authorisation_that_miscounts_is_refused():
    """A reviewer approves a quantity, not an intention."""
    comparison = ratchet_compare(manifest_document(2), manifest_document(3),
                                 authorisations(), authorisations(("new", 4)))
    assert not comparison.ok
    assert comparison.faults[0].code == codes.AUTHORISATION_COUNT_WRONG


def test_an_authorisation_that_licenses_nothing_is_refused():
    """An override that overrides nothing is the shape of a check that cannot fail."""
    comparison = ratchet_compare(manifest_document(3), manifest_document(3),
                                 authorisations(), authorisations(("new", 2)))
    assert not comparison.ok
    assert comparison.faults[0].code == codes.AUTHORISATION_INERT


def test_a_fall_needs_no_authorisation_at_all():
    """Nothing here demands the count shrink, and nothing penalises it either."""
    comparison = ratchet_compare(manifest_document(9), manifest_document(4),
                                 authorisations(), authorisations())
    assert comparison.ok
    assert comparison.rise == 0


def test_a_base_with_no_manifest_treats_every_gap_as_new():
    """A branch taken before this ticket landed genuinely has no manifest, and
    every unwrapped operation in the proposal genuinely is a rise from nothing —
    which is what makes this pull request's own authorisation load-bearing."""
    comparison = ratchet_compare({}, manifest_document(56),
                                 {}, authorisations(("seed", 56)))
    assert comparison.ok
    assert comparison.was == 0 and comparison.now == 56


@pytest.fixture
def repository(tmp_path):
    """A real git repository with a manifest committed on `main`.

    Real git, because resolving the base ref is the one part a pure comparison
    cannot reach — and it is the part that decides whether the gate runs.
    """
    git(tmp_path, "init", "-b", "main", str(tmp_path))
    git(tmp_path, "config", "user.email", "ci@example.invalid")
    git(tmp_path, "config", "user.name", "CI")
    _commit(tmp_path, manifest_document(2), authorisations(), "as it stands")
    return tmp_path


def _commit(repository, manifest, authorisation_document, message):
    for relative, document in ((MANIFEST_PATH, manifest),
                               (AUTHORISATIONS_PATH, authorisation_document)):
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(document, sort_keys=False),
                        encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", message)


def test_a_branch_that_raises_the_count_fails_against_its_base(repository):
    git(repository, "checkout", "-b", "feature")
    _commit(repository, manifest_document(3), authorisations(), "one more gap")
    comparison = ratchet_run(repository, "main")
    assert not comparison.ok
    assert comparison.faults[0].code == codes.UNWRAPPED_ROSE


def test_a_branch_that_raises_it_with_a_signature_passes(repository):
    git(repository, "checkout", "-b", "feature")
    _commit(repository, manifest_document(3), authorisations(("new", 1)),
            "one more gap, signed for")
    assert ratchet_run(repository, "main").ok


def test_an_unresolvable_base_fails_rather_than_skipping(repository):
    """A silently skipped comparison is how an unreviewed rise reaches main."""
    comparison = ratchet_run(repository, "origin/does-not-exist")
    assert not comparison.ok
    assert comparison.faults[0].code == codes.BASE_UNREADABLE


# ---------------------------------------------------------------------------
# 5. The gate is wired the way the manifest says
# ---------------------------------------------------------------------------

def test_the_workflow_runs_the_regeneration_gate_and_the_ratchet():
    """`gates/manifest.yaml` claims two workflow steps for G18, and
    `tools.gates` proves those steps are armed. This asserts the commands they
    run are this tool's, so renaming the module cannot leave two correctly
    armed steps running nothing."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/ci.yml").read_text("utf-8"))
    steps = workflow["jobs"]["contracts"]["steps"]
    commands = " ".join(str(step.get("run", "")) for step in steps)
    assert "python -m tools.sdk_operations --write" in commands
    assert "python -m tools.sdk_operations ratchet" in commands


def test_every_gap_that_exists_was_signed_for_at_some_point():
    """The authorisations account for at least the gaps standing today.

    Authorisations record *rises* and nothing records a fall, so the durable
    relation is `sum(licensed) >= unwrapped`: today's count is every rise minus
    every operation since wrapped. Asserting equality would be true only until
    the first slice wraps something, and a test that has to be edited to stay
    true is one that gets edited without being read.

    What it still catches is the case that matters — an unwrapped count larger
    than anything anybody ever signed for, which means a rise got through. CI's
    ratchet catches that against the base branch; this catches it offline, and
    against the whole history rather than one hop of it.
    """
    manifest = yaml.safe_load((REPO_ROOT / MANIFEST_PATH).read_text("utf-8"))
    signed = yaml.safe_load((REPO_ROOT / AUTHORISATIONS_PATH).read_text("utf-8"))
    licensed = sum(entry["operations_added"]
                   for entry in signed["authorisations"])
    assert licensed >= manifest["summary"]["unwrapped"], (
        f"{manifest['summary']['unwrapped']} operations are unwrapped and the "
        f"authorisations account for {licensed}. Every rise needs a signature, "
        f"so the total signed for can never be less than the total standing.")
