"""The SDK's call surface agrees with the committed contract, both ways (#204, #209).

G17 and G18 in `gates/manifest.yaml`, from ADR-0007 §4 and #155 §8.2 and §8.3.
Three properties now, settled from one join:

- **Forward** — every hand-written call targets a published operation, matched
  on the complete identity: HTTP method AND normalised path. A path match alone
  is insufficient, because `GET /x/{id}` is not `POST /x/{id}`.
- **Reverse** — every published operation carries a disposition in
  `ubb-sdk/operation-coverage.yaml`, which regenerates with zero diff.
- **Confined** (#209) — a call *names* an operation rather than spelling a
  route, and the only file under `ubb-sdk/ubb/` allowed to spell one is the
  generated registry, which regenerates with zero diff too.

#155 §8.5 names six cases CI must prove and calls them not negotiable. They are
section 2 below, one test each, in its order. #209 moved where two of them can
go wrong without changing what they assert, and each says so at its own head —
that is the only concession made to the refactor, and it is a deliberate one:
the cases are a specification, not a description of an implementation.

Section 3 carries the controls for the rules this gate adds beyond them,
section 4 is the ratchet, and section 5 checks the wiring.

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
    A_DEBT_FOUND, A_DEBT_ROUTE, A_DEBT_SITE, ROOT, THING_LIST, THING_READ,
    THING_WRITE, a_debt_constant, a_repository_with_one_debt, call,
    client_module, constant, excusing, interpolated, literal,
    modules_spelling_the_unpublished_prefix, registry_source, spec,
    write_repository,
)
from tools.sdk_operations import SurfaceInvalid, assess, load_coverage
from tools.sdk_operations import errors as codes
from tools.sdk_operations import registry as registry_module
from tools.sdk_operations.coverage import (
    DISPOSITIONS, GENERATED_ONLY, LEDGER_PATH, NOT_YET_WRAPPED, WRAPPED,
)
from tools.sdk_operations.calls import ROUTE_MARKER, SHELL_ROOT
from tools.sdk_operations.manifest import MANIFEST_PATH, compare, render
from tools.sdk_operations.ratchet import AUTHORISATIONS_PATH
from tools.sdk_operations.ratchet import compare as ratchet_compare
from tools.sdk_operations.ratchet import run as ratchet_run
from tools.sdk_operations.registry import REGISTRY_PATH
from tools.sdk_operations.registry import compare as compare_registry
from tools.sdk_operations.spec import HTTP_METHODS, SPEC_PATH, load_operations

#: The modules the walker must have visited. A vacuity guard names them because
#: a walker that silently found nothing passes every assertion below.
HAND_WRITTEN_MODULES = ("billing.py", "client.py", "metering.py",
                        "referrals.py", "subscriptions.py")

#: The book surface the metering client keeps, after #373 removed the three
#: methods that reached routes nothing publishes.
#:
#: A SET, deliberately, and not a count. #155 §8.6 says the hand shell survives
#: this slice; what a test has to catch is one of these methods leaving ahead of
#: the coordinated break, and a set names which one while a floor only says the
#: total fell. It is also the honest answer to a number that moved: the spec
#: counted seven surviving call sites against `d940e7f`, then #368 split the
#: container in two — three of them became six — and #369 deleted the four
#: markup methods that made up the rest.
SURVIVING_BOOK_CALLS = frozenset({
    "MeteringClient.declare_pricing_book",
    "MeteringClient.withdraw_pricing_book",
    "MeteringClient.list_pricing_books",
    "MeteringClient.declare_cost_book",
    "MeteringClient.withdraw_cost_book",
    "MeteringClient.list_cost_books",
})

#: The faults that mean a call did not resolve. Named as a set so the forward
#: test asserts on the property rather than on "no errors at all", which would
#: also go red for a stale manifest and say the wrong thing about why.
FORWARD_FAULTS = frozenset({
    codes.NO_SUCH_OPERATION, codes.NO_SUCH_OPERATION_CONSTANT,
    codes.CALL_NOT_AN_OPERATION, codes.CALL_MALFORMED,
    codes.PARAMETER_COUNT_WRONG, codes.STRAY_ROUTE_LITERAL,
    codes.STALE_DOCUMENTED_ROUTE, codes.UNSCANNED_PACKAGE,
    codes.SHELL_MISSING, codes.SHELL_EMPTY, codes.SHELL_UNREADABLE,
})

#: The faults that mean the registry is not the contract's.
REGISTRY_FAULTS = frozenset({
    codes.REGISTRY_MISSING, codes.REGISTRY_UNREADABLE,
    codes.REGISTRY_INCOMPLETE, codes.REGISTRY_ENTRY_UNKNOWN,
    codes.REGISTRY_ENTRY_WRONG, codes.OPERATION_ID_NOT_A_NAME,
    codes.REGISTRY_NAME_COLLISION,
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
    return must_refuse(tmp_path)


def must_refuse(repo_root):
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


def messages(invalid, code):
    return [error.message for error in invalid.errors if error.code == code]


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
    # base branch by the ratchet. Naming them here as well would be a third
    # copy of a list that is now empty anyway.
    #
    # ⚠ THIS WAS A CEILING OF THREE UNTIL #373 AND IS NOW AN EQUALITY. The
    # ceiling was the honest form while the count was coming down — it let a
    # partial payment land without a test edit. That is exactly why it may not
    # survive reaching zero: `<= 0` and `== 0` are the same assertion, but the
    # first says the number may still fall, and it cannot. An excused call now
    # requires a seeding authorisation, which the ratchet refuses on its own.
    assert len(coverage.excused) == 0, (
        f"{len(coverage.excused)} invalid calls are excused. #155 §1.3 found "
        f"three and slice 4 paid all three at once; the count is zero and a "
        f"new one is a seeding authorisation, not a debt this gate absorbs.")


def test_no_route_literal_survives_in_the_hand_written_layer(shipped):
    """#209's own claim, asserted over the real tree rather than a synthetic one.

    Two halves, and the second is what makes the first mean anything. There is
    no route literal outside the registry — and the reason there is none is
    that no call site can spell one, not that somebody tidied up. Both are
    checked by `assess`; this names the fault codes so a regression reads as
    "a path came back into the hand shell" rather than as a generic red.
    """
    _, errors = shipped
    strays = [error for error in errors
              if error.code in (codes.STRAY_ROUTE_LITERAL,
                                codes.CALL_NOT_AN_OPERATION)]
    assert not strays, (
        "\n" + "\n".join(str(error) for error in strays)
        + f"\n\nSince #209 the only file under {SHELL_ROOT}/ that may spell a "
          f"path is {REGISTRY_PATH}, and it is generated.")


def test_the_registry_regenerates_with_zero_diff(shipped):
    """The committed registry is exactly what the contract and ledger render.

    Without this, "confined to one mechanically checked registry" would be
    confined to one registry and checked by nothing: a hand edit could point a
    constant anywhere, and every wrapper naming it would follow.
    """
    coverage, _ = shipped
    stale, _ = compare_registry(coverage.entries, REPO_ROOT)
    assert stale is None, str(stale)


def test_the_committed_registry_is_the_contract_operation_by_operation(shipped):
    """Not the same claim as the zero-diff gate above, and the difference matters.

    Zero diff compares BYTES against what the renderer produces now. This
    compares the committed file's declarations against the contract one
    operation at a time, so a disagreement is reported as "this constant says
    POST and the contract says GET" rather than as a diff a reader has to
    interpret. It is also the check that survives a renderer whose layout
    changes: the bytes would differ for a reason that is not a fault, and this
    would still be the thing that says whether anything is actually wrong.
    """
    _, errors = shipped
    faults = [error for error in errors if error.code in REGISTRY_FAULTS]
    assert not faults, (
        "\n" + "\n".join(str(error) for error in faults)
        + f"\n\n{REGISTRY_PATH} is generated: run "
          f"`python -m tools.sdk_operations --write`.")


def test_every_published_operation_can_be_named():
    """One constant per published operation, so no operation is unreachable.

    Read off DISK — the committed registry parsed on one side, the committed
    contract parsed on the other — rather than from the `shipped` fixture.
    `coverage.entries` is what the renderer produces from the contract, so
    comparing it to `coverage.rows` would compare two things derived from the
    same dictionary: a check that cannot fail, which is the shape this whole
    programme exists to refuse.

    The two ends genuinely differ. `registry.load` reads Python source with
    `ast`; `load_operations` reads JSON. Nothing but the repository connects
    them, which is what makes disagreement possible and therefore worth
    asserting.
    """
    committed = registry_module.load(REPO_ROOT, [])
    operations, _ = load_operations(REPO_ROOT)

    named = {entry.operation_id for entry in committed.values()
             if entry.is_published}
    published = {operation.operation_id for operation in operations.values()}
    assert named == published, (
        f"the committed registry names {len(named)} operations and the "
        f"contract publishes {len(published)}; the difference is "
        f"{sorted(published ^ named)}. Run "
        f"`python -m tools.sdk_operations --write`.")
    assert len(published) > 100, "suspect the contract read"


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
                   for method in item if method in HTTP_METHODS)
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
    assert len(recorded) == 0, (
        f"{len(recorded)} G17 debts, and the family reached zero in #373. "
        f"Adding one is refused by the ledger ratchet without a seeding "
        f"authorisation; this catches the case where the authorisation was "
        f"written anyway.")


def test_each_excused_route_is_reachable_only_through_the_ledger(shipped, tmp_path):
    """#209's grip on a dead call: its constant exists because its entry does.

    Each debt has exactly one `UNPUBLISHED_` constant, and that constant exists
    because the entry does. Delete the entry — which is what paying the debt
    looks like — and the constant goes with it, so the method that owed it
    stops resolving in the same commit rather than three slices later. That is
    what made #373 possible as ONE commit and impossible as three.

    ⚠ **THE SHIPPED-TREE ARM IS TWO EMPTY SETS NOW, AND TWO EMPTY SETS AGREE
    WITH EACH OTHER WHATEVER THE READER IS DOING.** Left as it was, this test
    would have gone from checking a correspondence to checking nothing, without
    a line changing and without going red — the exact shape `gates/README.md`
    records as a check that cannot fail. So the correspondence is asserted
    where it still has content, over a synthetic repository with a debt in it,
    and the shipped-tree arm is kept for the one thing it can still say: that
    the two sides are empty TOGETHER. A constant hand-written into the
    generated registry with no entry behind it fails that, which is the
    direction the byte-comparison gate reports as a diff rather than as a
    meaning.
    """
    coverage, _ = shipped
    unpublished = {name for name, entry in coverage.entries.items()
                   if not entry.is_published}
    assert unpublished == set() == {registry_module.unpublished_name(found)
                                    for _, found in coverage.excused}

    a_repository_with_one_debt(tmp_path)
    with_a_debt = load_coverage(tmp_path)

    named = {name for name, entry in with_a_debt.entries.items()
             if not entry.is_published}
    assert named == {registry_module.unpublished_name(found)
                     for _, found in with_a_debt.excused}, (
        "the constant a debt renders and the debt the gate excuses have come "
        "apart, so paying one would no longer take the other with it")
    assert all(name.startswith(registry_module.UNPUBLISHED_PREFIX)
               for name in named), (
        "a route the contract does not publish must be visibly named as one at "
        "the call site — that is the whole reason these constants are ugly")


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


def test_the_gate_owes_nothing_and_the_family_is_declared_empty():
    """G17 OWES NOTHING, and the emptiness is declared rather than implied.

    ⚠ **THIS TEST REPLACES THE OWNERSHIP CHECK AT ITS OWN ADDRESS, INVERTED.**
    Until #373 it read the `owner_slice` of every G17 entry and required it to
    be `slice_4` — the slice where the surface those calls reach stops
    existing. The three entries are paid and gone, and the *same* assertion
    would now pass over an empty set while proving nothing: `set() <=
    {"slice_4"}` is true of a ledger with no G17 entries and true of a ledger
    that lost the gate entirely. Relaxing into that is how a control goes
    vacuous without announcing it, so the claim is replaced by the one that is
    now load-bearing — the family is EMPTY — rather than kept and weakened.

    The `expected` these entries carried was never a name to rename onto: there
    is no correct route to point at, because the operations those methods
    wanted were never published. The debt is discharged by the call going away,
    which is what #373 did, in one commit, because the constants are generated
    from the entries.

    `test_model_naming.py`'s `LEDGERED_VIOLATIONS` holds the same shape for G11
    and G12 next door: a paid family stays visible as an empty one, so its
    absence is a declaration rather than a silence.
    """
    ledger = yaml.safe_load((REPO_ROOT / LEDGER_PATH).read_text("utf-8"))
    owed = [entry["site"] for entry in ledger["entries"]
            if entry["gate"] == "G17"]
    assert owed == [], (
        f"G17 carries {len(owed)} entries again: {sorted(owed)}. The family "
        f"was emptied in #373 and a call to a route nothing publishes now "
        f"needs a seeding authorisation, which is a decision somebody signs "
        f"rather than a debt this ledger quietly absorbs.")

    # Vacuity guard: the assertion above is satisfied by a ledger with no G17
    # entries AND by a ledger this reader failed to parse at all. Reading a
    # sibling family that is NOT empty separates the two — it fails on an
    # unparsed document and passes only where entries really were read.
    assert any(entry["gate"] == "G7" for entry in ledger["entries"]), (
        "no G7 entry was read either, so the emptiness above is a statement "
        "about this reader rather than about the ledger")


def test_no_hand_written_call_resolves_to_a_route_the_contract_omits(shipped):
    """The general property: nothing in the shell reaches an unpublished route.

    ⚠ **THE CLAIM IS THE PROPERTY, NOT THREE NAMED ABSENCES.** Asserting that
    the three methods #373 deleted are gone would be satisfied by a fourth
    arriving under a different name, and would go stale the day somebody read
    it as the whole rule. The three conjuncts below are about the SHAPE of the
    surface, so a call that has not been written yet is already covered:

    - **no call is excused** — the join reports nothing the ledger had to cover;
    - **no constant names an unpublished route** — the registry is rendered from
      the contract alone, because the only other source it reads is the G17
      family and that family is empty;
    - **the graceless prefix does not appear in the hand shell at all** — not in
      a call, not in a docstring, not in a comment. A stray one that failed to
      resolve would be caught by the forward test as a missing constant; this
      catches the vocabulary coming back before it reaches a call.

    Its non-vacuity is not argued: the control below builds a repository where
    the same three conjuncts are FALSE, through the same entry point.
    """
    coverage, _ = shipped

    assert coverage.excused == (), (
        "\n".join(f"{site} -> {found}" for site, found in coverage.excused)
        + "\n\na hand-written call is reaching a route the contract does not "
          "publish. Since #373 that is a defect rather than a recorded debt.")

    named = sorted(name for name, entry in coverage.entries.items()
                   if not entry.is_published)
    assert named == [], (
        f"the registry declares {named}, so it was rendered from something "
        f"other than the contract. The only other source it reads is the "
        f"ledger's G17 family, which is empty.")

    spelled = modules_spelling_the_unpublished_prefix(REPO_ROOT)
    assert spelled == [], (
        f"{spelled} spell `{registry_module.UNPUBLISHED_PREFIX}` and the hand "
        f"shell has no unpublished route left to name. The constants are "
        f"deliberately graceless so that one reappearing is read by a person; "
        f"this is that reader.")


def test_the_book_surface_survives_and_resolves(shipped):
    """#155 §8.6: the shell is not deleted — only its dead calls are.

    **What this adds, and it is one thing.** That the metering client STILL
    DECLARES its book methods. Every other test here would pass over a shell
    with nothing left in it: "every call resolves" is vacuously true of no
    calls, and `test_the_walker_visited_the_whole_hand_written_surface` guards
    only a floor across all five modules, which six deletions in one file would
    not breach. A named SET is what makes one method leaving red, and says
    which one.

    That each of them resolves to a PUBLISHED operation comes with the set for
    free rather than needing its own line: `coverage.rows` holds one row per
    published operation, so a site reachable through `wrapped_by` has already
    matched one. The whole-shell version of that claim belongs to
    `test_every_hand_written_call_targets_a_published_operation`, which reports
    the faults; asserting it again here would be a second encoding of one gate.

    ⚠ **THE ACCEPTANCE CRITERION'S COUNT IS STALE AND IS NOT COPIED.** It says
    "seven surviving call sites", taken from the spec against `d940e7f`: three
    on the book surface and four markup methods. Both halves moved inside this
    same slice — #368 split the container into a Pricing Book and a cost book,
    taking the three to six, and #369 deleted the four. Seven was true when it
    was written and is not a fact about this tree, so the subject here is the
    six that exist, named.
    """
    coverage, _ = shipped

    # `coverage.rows` is one row per PUBLISHED operation, so a site appearing
    # in any row's `wrapped_by` has, by construction, resolved to an operation
    # the contract carries. The set below therefore makes both halves of the
    # claim at once, and the "resolves to something published" half needs no
    # separate assertion — restating it here would be a second encoding of
    # what the forward test already reports faults for.
    reached = {site.split("::", 1)[1]
               for row in coverage.rows for site in row.wrapped_by
               if site.startswith(f"{SHELL_ROOT}/metering.py::")}

    assert SURVIVING_BOOK_CALLS <= reached, (
        f"{sorted(SURVIVING_BOOK_CALLS - reached)} no longer resolves to a "
        f"published operation. #155 §8.1 puts the SDK's breaking release after "
        f"slice 8 as one coordinated event; a method leaving before then is a "
        f"surface break nobody signed.")


# ---------------------------------------------------------------------------
# 2. #155 §8.5's six cases, in its order
# ---------------------------------------------------------------------------

def test_case_1_a_nonexistent_route_fails(tmp_path):
    """Both ways it can now be reached, because #209 split the mistake in two.

    A wrapper can no longer *write* a nonexistent route — there is nowhere at a
    call site to put one. So the case survives as its two halves: a wrapper
    naming an operation nothing declares, and a registry declaring an operation
    nothing publishes. Asserting only the first would leave the file that
    replaced the literals unchecked, which is where the literals went.
    """
    named = rejection(tmp_path / "wrapper", modules={
        "things.py": client_module("*ops.THINGS_NOWHERE")})
    assert codes.NO_SUCH_OPERATION_CONSTANT in named.codes()
    assert any("THINGS_NOWHERE" in message for message
               in messages(named, codes.NO_SUCH_OPERATION_CONSTANT))

    invented = registry_source() + (
        f"\nTHINGS_NOWHERE = Operation('things_nowhere', 'get',"
        f" '{ROOT}/nowhere')\n")
    declared = rejection(tmp_path / "registry", registry=invented, modules={
        "things.py": client_module("*ops.THINGS_NOWHERE")})
    assert codes.REGISTRY_ENTRY_UNKNOWN in declared.codes()
    assert any("/nowhere" in message for message
               in messages(declared, codes.REGISTRY_ENTRY_UNKNOWN))


def test_case_2_a_valid_path_with_the_wrong_method_fails(tmp_path):
    """ADR-0007 §4's own example. The path exists; the method does not.

    #209 moved where this can happen without weakening it. A call site cannot
    spell a method any more, so the one remaining way to reach a valid path
    under a method nothing publishes is a registry entry that says so — and the
    check lives there. A rule that declared its own violation unreachable would
    be a rule nothing enforces, which is the failure this whole programme is
    about.

    The message must name the method that IS published, because this is the
    failure a reader is likeliest to misread as "the route is wrong".
    """
    wrong = registry_source((THING_LIST,)).replace(
        f"'get', '{ROOT}/things'", f"'post', '{ROOT}/things'")
    invalid = rejection(tmp_path, operations=(THING_LIST,), registry=wrong,
                        modules={"things.py": client_module(call("things_list"))})

    faults = messages(invalid, codes.REGISTRY_ENTRY_WRONG)
    assert len(faults) == 1, invalid.errors
    assert f"POST {ROOT}/things" in faults[0], "what the registry says"
    assert f"GET {ROOT}/things" in faults[0], "what the contract publishes"


def test_case_3_a_renamed_operation_with_a_stale_wrapper_fails(tmp_path):
    """The wrapper is untouched; the contract moved under it.

    Built as a genuine before-and-after so the rename is what breaks it. A
    control that only asserted the "after" would be case 1 again wearing a
    different name, and would still pass if the gate had never resolved the
    call in the first place.

    This is the case #209 exists for, and it is now caught one step earlier:
    the constant is renamed with the operation, so a wrapper that did not move
    names something that is not there, rather than sending a stale path to a
    real server.
    """
    before = tmp_path / "before"
    after = tmp_path / "after"
    wrapper = {"things.py": client_module(call("things_list"))}

    coverage = accepted(before, operations=(THING_LIST,), modules=wrapper)
    assert disposition_of(coverage, "things_list").disposition == WRAPPED

    renamed = ("get", f"{ROOT}/things", "things_index")
    invalid = rejection(after, operations=(renamed,), modules=wrapper)
    assert codes.NO_SUCH_OPERATION_CONSTANT in invalid.codes()
    assert any("THINGS_INDEX" in message for message
               in messages(invalid, codes.NO_SUCH_OPERATION_CONSTANT)), (
        "the message must name what it was renamed to; a bare 'no such "
        "constant' leaves an author diffing two long identifiers by eye")


def test_case_3b_a_path_that_moves_under_a_stable_operation_is_followed(tmp_path):
    """The other half of case 3, and the behaviour #209 deliberately CHANGED.

    Before the registry, a wrapper carried the path, so moving a route in the
    contract broke the wrapper — case 3 above, in its original form. Now the
    wrapper carries the `operationId`, so the same move is FOLLOWED: the
    constant is regenerated with the new path and the method calls the right
    route without being touched. That is the improvement, not an oversight, and
    it is asserted here because a behaviour nobody wrote down is a behaviour
    that gets 'fixed' by the next person to notice it.

    What still catches a move the author did not intend is the documentation:
    a docstring naming the old path no longer resolves, so the method that
    quietly changed target says so in the same run. Both halves are asserted,
    because the second is the whole reason the first is safe.
    """
    moved = ("get", f"{ROOT}/widgets", "things_list")
    wrapper = client_module(call("things_list"))

    coverage = accepted(tmp_path / "followed", operations=(moved,),
                        modules={"things.py": wrapper})
    row = disposition_of(coverage, "things_list")
    assert row.disposition == WRAPPED and row.path == f"{ROOT}/widgets", (
        "the untouched wrapper must now reach the moved route")

    documented = client_module(
        call("things_list"),
        extra=f'\n\ndef documented():\n'
              f'    """Wraps GET {ROOT}/things, where it used to live."""\n'
              f'    return None\n')
    invalid = rejection(tmp_path / "stale-prose", operations=(moved,),
                        modules={"things.py": documented})
    assert codes.STALE_DOCUMENTED_ROUTE in invalid.codes(), (
        "a move the author did not intend still surfaces, through the prose "
        "that names where the route used to be")


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
        modules={"things.py": client_module(call("things_list"))})

    assert disposition_of(coverage, "things_list").disposition == WRAPPED
    assert disposition_of(coverage, "things_read").disposition == GENERATED_ONLY
    assert disposition_of(coverage, "things_write").disposition == NOT_YET_WRAPPED
    assert coverage.unwrapped == 2

    text = render(coverage)
    for operation_id in ("things_read", "things_write"):
        assert f"operation_id: {operation_id}" in text, (
            f"{operation_id} is unwrapped and vanished from the manifest — "
            f"a gap nobody can see is not a declared gap")

    # An unwrapped operation is still NAMED. The registry is the contract's
    # vocabulary, not a record of what happens to be called today, so the next
    # wrapper has a constant to reach for rather than a path to invent.
    assert constant("things_write") in coverage.entries


def test_case_6_a_correctly_mapped_wrapper_passes(tmp_path):
    """Both call shapes, since a parameterised route is 39 of the real ones."""
    coverage = accepted(tmp_path, modules={
        "things.py": client_module(
            call("things_list"),
            call("things_read", "thing_id"),
        )})

    assert disposition_of(coverage, "things_list").disposition == WRAPPED
    assert disposition_of(coverage, "things_read").wrapped_by == (
        f"{SHELL_ROOT}/things.py::ThingsClient.call_1",)
    assert coverage.unwrapped == 0


# ---------------------------------------------------------------------------
# 3. The rules this gate adds beyond the six
# ---------------------------------------------------------------------------

def test_a_route_literal_at_a_call_site_is_refused(tmp_path):
    """The shape all 81 calls had before #209, now a violation.

    Without this the refactor could come undone one method at a time, and each
    undoing would look like ordinary code.
    """
    invalid = rejection(tmp_path, operations=(THING_LIST,), modules={
        "things.py": client_module(f'"get", {literal(f"{ROOT}/things")}')})
    assert codes.CALL_NOT_AN_OPERATION in invalid.codes()


def test_an_interpolated_route_at_a_call_site_is_refused(tmp_path):
    """And the f-string shape, which is how the parameterised ones read."""
    invalid = rejection(tmp_path, modules={
        "things.py": client_module(
            f'"get", {interpolated(f"{ROOT}/things/{{}}")}')})
    assert codes.CALL_NOT_AN_OPERATION in invalid.codes()


def test_a_route_spelled_outside_a_call_is_refused(tmp_path):
    """The conjunct that makes the rule honest.

    Without it the gate reads only `_request`-shaped calls, and
    `self._http.get("/api/v1/...")` is a route it never sees — a hole an author
    could fall into without meaning to, and step through on purpose.
    """
    invalid = rejection(tmp_path, modules={"things.py": client_module(
        extra=f'\n\ndef sneak(client):\n'
              f'    return client._http.get("{ROOT}/things")\n')})
    assert codes.STRAY_ROUTE_LITERAL in invalid.codes()


def test_a_module_that_reaches_no_registry_cannot_resolve_anything(tmp_path):
    """And the message says which import is missing.

    A gate whose failure means "you did it wrong" costs an author a search;
    one that names the line to add costs them a paste.
    """
    invalid = rejection(tmp_path, modules={
        "things.py": client_module(call("things_list"), imports=False)})
    faults = messages(invalid, codes.CALL_NOT_AN_OPERATION)
    assert faults and any("_operations as ops" in message for message in faults)


def test_a_computed_target_is_refused_rather_than_skipped(tmp_path):
    """A call this gate cannot read is not a call it can vouch for.

    Skipping it would make the gate optional: anyone who assembled a route from
    a variable would be exempt, and the exemption would be invisible.
    """
    invalid = rejection(tmp_path, modules={"things.py": client_module(
        extra='\n\nclass Sneaky:\n'
              '    def _request(self, method, path, **kwargs): ...\n\n'
              '    def go(self, route):\n'
              '        return self._request("get", route)\n')})
    assert codes.CALL_NOT_AN_OPERATION in invalid.codes()


def test_a_keyword_spelled_route_is_refused_too(tmp_path):
    """`_request(method="get", path=...)` was readable before #209 and is a
    violation now — the same route, spelled to dodge the positional reader."""
    invalid = rejection(tmp_path, operations=(THING_LIST,), modules={
        "things.py": client_module(
            extra=f'\n\nclass Keyword:\n'
                  f'    def _request(self, method, path, **kwargs): ...\n\n'
                  f'    def go(self):\n'
                  f'        return self._request(method="get", '
                  f'path="{ROOT}/things")\n')})
    assert codes.CALL_NOT_AN_OPERATION in invalid.codes()


def test_too_few_values_for_a_parameterised_route_is_refused(tmp_path):
    """A property an f-string could not have had at all.

    `f"/things/{a}"` interpolated whatever it was handed and produced a
    plausible, wrong path; a registry entry knows how many positions it has.
    """
    invalid = rejection(tmp_path, modules={
        "things.py": client_module(call("things_read"))})
    faults = messages(invalid, codes.PARAMETER_COUNT_WRONG)
    assert faults and "1" in faults[0]


def test_too_many_values_for_a_parameterised_route_is_refused(tmp_path):
    invalid = rejection(tmp_path, modules={
        "things.py": client_module(call("things_read", "thing_id", "other_id"))})
    assert codes.PARAMETER_COUNT_WRONG in invalid.codes()


def test_values_passed_to_a_route_that_takes_none_are_refused(tmp_path):
    invalid = rejection(tmp_path, modules={
        "things.py": client_module(call("things_list", "thing_id"))})
    assert codes.PARAMETER_COUNT_WRONG in invalid.codes()


def test_a_stale_route_in_a_docstring_is_refused(tmp_path):
    """#155 §8.3 says a rename may not leave a stale string behind, and a
    docstring is a string.

    The SDK's methods document the routes they call, deliberately, as public
    documentation — so the answer is not to delete them but to hold them to the
    contract. The rule caught nothing when it landed (of 53 documented routes,
    48 resolved exactly, 4 named a family and 1 was ledger-excused) and nothing
    since: re-measured after #373, 59 documented routes, 55 exact, 4 naming a
    family and none excused. It is here for the rename that fixes a call and
    forgets the prose.
    """
    invalid = rejection(tmp_path, operations=(THING_LIST,), modules={
        "things.py": client_module(
            call("things_list"),
            extra=f'\n\ndef documented():\n'
                  f'    """Wraps GET {ROOT}/things/gone, which moved."""\n'
                  f'    return None\n')})
    faults = messages(invalid, codes.STALE_DOCUMENTED_ROUTE)
    assert faults and f"{ROOT}/things/gone" in faults[0]


def test_a_docstring_naming_a_real_route_is_prose_and_not_a_call(tmp_path):
    """The other side of that rule, and the reason it needs one.

    Every real client method documents the route it calls. Treating those as
    unaccounted routes would make the gate unusable on the day it shipped —
    which is how a gate ends up with an exclusion list nobody can read.
    """
    coverage = accepted(tmp_path, operations=(THING_LIST,), modules={
        "things.py": client_module(
            call("things_list"),
            extra=f'\n\ndef documented():\n'
                  f'    """Wraps GET {ROOT}/things, and calls nothing."""\n'
                  f'    return None\n')})
    assert coverage.unwrapped == 0


def test_a_docstring_naming_a_family_of_routes_is_allowed(tmp_path):
    """`/api/v1/things/` in a class docstring says what the client is FOR.

    Accepted as the start of something published, so it still goes stale if the
    whole family moves — which is the only thing that could make it wrong.
    """
    coverage = accepted(tmp_path, operations=(THING_LIST,), modules={
        "things.py": client_module(
            call("things_list"),
            extra=f'\n\nclass Family:\n'
                  f'    """The client for {ROOT}/things/."""\n')})
    assert coverage.unwrapped == 0


def test_a_docstring_naming_an_excused_route_is_allowed(tmp_path):
    """A dead call documents what it calls, until its slice deletes both at
    once. A gate that refused the prose but excused the call would force the
    documentation to lie about a method that still exists.

    ⚠ No real method is in this shape any more — #373 deleted the three that
    were, with their entries and their docstrings in the same commit, which is
    what "both at once" meant. This control keeps the arm honest for the next
    seeding rather than describing a live case."""
    site, found = a_repository_with_one_debt(
        tmp_path,
        extra=f'\n\ndef documented():\n'
              f'    """Wraps GET {A_DEBT_ROUTE}, which nothing publishes."""\n'
              f'    return None\n')
    assert load_coverage(tmp_path).excused == ((site, found),)


def test_the_generated_docstring_describes_only_the_sections_the_file_has():
    """#373's repair, asserted rather than asserted-about.

    The generated registry's docstring used to carry a paragraph saying, in the
    present tense, that three methods call its `UNPUBLISHED_` constants. That
    went false when the methods were deleted — in a file nobody may edit by
    hand, so there was no way to correct it in place. The paragraph is now
    rendered only when there are unpublished entries to describe.

    Selling that as "the class of defect is removed" is worth nothing without a
    control that names it, because the failing direction is a paragraph that
    should be absent and is not — an absence again. Both directions are driven
    here through the real renderer, off the same helper the synthetic
    repositories are built with.

    The docstring is isolated from the constants before asserting: the prefix
    appears in both, so a search over the whole file would pass on a module
    whose docstring said nothing at all.
    """
    def module_docstring(source):
        head, marker, _ = source.partition("from ubb._operation import")
        assert marker, "the rendered registry no longer imports its own type"
        return head

    prefix = registry_module.UNPUBLISHED_PREFIX

    with_a_debt = registry_source(ledger=excusing((A_DEBT_SITE, A_DEBT_FOUND)))
    assert prefix in module_docstring(with_a_debt), (
        "the registry rendered an unpublished section and said nothing about "
        "it, so a reader meets the ugly constants with no explanation")
    assert prefix in with_a_debt.split("from ubb._operation import", 1)[1], (
        "the docstring promised a section the file does not carry")

    without = registry_source()
    assert prefix not in module_docstring(without), (
        "the registry has no unpublished entries and its docstring describes "
        "them anyway — the exact sentence #373 could not correct in place, "
        "because this file is generated")
    assert prefix not in without, (
        "a registry with no debts rendered an unpublished constant")


def test_the_shipped_trees_three_absences_are_each_reachable(tmp_path):
    """The positive control for the property #373 left behind.

    `test_no_hand_written_call_resolves_to_a_route_the_contract_omits` asserts
    three things about the shipped tree, and every one of them is an ABSENCE.
    An absence passes on a tree whose gate stopped working exactly as it passes
    on a tree that is clean, so the shipped assertion is only worth what a
    demonstration that each conjunct CAN be false is worth. This is that
    demonstration, over a repository built to make all three false at once.

    Each conjunct is driven the way the shipped one is driven, which is not the
    same mechanism for all three: the first two come out of `load_coverage`,
    the entry point CI calls, and the third is a property of the shell's SOURCE
    and so runs `modules_spelling_the_unpublished_prefix` — the identical
    function the shipped assertion calls, shared for that reason. A control
    that re-implemented the search would only prove two copies agree.

    It is deliberately not three tests. The claim is that the three conjuncts
    are jointly satisfiable in the failing direction, which is what a fourth
    dead method arriving would look like; splitting it would let two survive a
    refactor of the third and still read as coverage.
    """
    site, found = a_repository_with_one_debt(tmp_path)
    coverage = load_coverage(tmp_path)

    assert coverage.excused == ((site, found),), (
        "conjunct 1 is unfalsifiable: a call to a route nothing publishes was "
        "not reported as excused even with the ledger carrying it")
    assert [one for one, entry in coverage.entries.items()
            if not entry.is_published] == [a_debt_constant()], (
        "conjunct 2 is unfalsifiable: the ledger's entry rendered no "
        "unpublished constant into the registry")
    assert modules_spelling_the_unpublished_prefix(tmp_path) == [
        f"{SHELL_ROOT}/things.py"], (
        "conjunct 3 is unfalsifiable: the shared reader found no module "
        "spelling the prefix in a shell that reaches an unpublished route")


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

    assert codes.UNSCANNED_PACKAGE in must_refuse(tmp_path).codes()


def test_a_missing_registry_fails_rather_than_reporting_a_clean_surface(tmp_path):
    """Every call resolves through it; reading zero operations out of a missing
    file must not look like a surface with nothing wrong."""
    write_repository(tmp_path, modules={
        "things.py": client_module(call("things_list"))})
    (tmp_path / REGISTRY_PATH).unlink()
    assert codes.REGISTRY_MISSING in must_refuse(tmp_path).codes()


def test_a_registry_missing_an_operation_is_refused(tmp_path):
    """A published operation nothing can name is unreachable through the SDK.

    Not implied by the zero-diff gate: a renderer that dropped a family would
    drop it from both sides of that comparison and stay green.
    """
    invalid = rejection(
        tmp_path, operations=(THING_LIST, THING_READ),
        registry=registry_source((THING_LIST,)),
        modules={"things.py": client_module(call("things_list"))})
    faults = messages(invalid, codes.REGISTRY_INCOMPLETE)
    assert faults and "things_read" in faults[0], (
        "the message must name the operation, which is what a reader needs to "
        "find it in the contract")


def test_a_registry_entry_that_is_not_an_operation_is_refused(tmp_path):
    """The registry holds operations and nothing else.

    A name bound to anything the reader cannot resolve would be a name the gate
    cannot check and a wrapper can still import — the blind spot, moved.
    """
    invalid = rejection(
        tmp_path, registry=registry_source() + "\nSNEAKY = 'get', '/api/v1/x'\n",
        modules={"things.py": client_module(call("things_list"))})
    assert codes.REGISTRY_UNREADABLE in invalid.codes()


def test_the_registry_renders_the_same_bytes_twice(tmp_path):
    """Determinism, because a zero-diff gate over an unstable renderer fails at
    random — and a gate that cries wolf gets disabled rather than obeyed."""
    coverage = accepted(tmp_path, modules={
        "things.py": client_module(call("things_list"),
                                   call("things_read", "thing_id"))})
    first = registry_module.render(coverage.entries)
    assert first == registry_module.render(coverage.entries)
    assert first.endswith("\n")

    committed = (REPO_ROOT / REGISTRY_PATH).read_text(encoding="utf-8")
    for text, what in ((first, "the rendered registry"),
                       (committed, "the committed registry")):
        widest = max(len(line) for line in text.splitlines())
        assert widest <= registry_module.WIDEST_LINE, (
            f"{what} has a {widest}-character line and the renderer's limit is "
            f"{registry_module.WIDEST_LINE}; a generated file nobody may "
            f"hand-edit is still a file people read")


def test_a_long_operation_is_wrapped_one_argument_to_a_line():
    """The renderer's third layout, which the shipped contract never reaches.

    Every real operation fits one of the first two. That makes this branch the
    one nothing would notice breaking — so it is exercised deliberately rather
    than left to the day a longer path arrives and the artifact stops parsing.
    """
    name = "A" * 60
    entry = registry_module.Entry(name, "a" * 60, "get", f"{ROOT}/" + "b" * 60)
    text = registry_module.render({name: entry})

    assert f"{name} = Operation(\n" in text, "it must break after the opening"
    assert max(len(line) for line in text.splitlines()) <= (
        registry_module.WIDEST_LINE + len(entry.path)), "no runaway line"
    compile(text, REGISTRY_PATH, "exec")     # and it is still Python


def test_a_missing_registry_is_a_different_fault_from_a_stale_one(tmp_path):
    """"No differences found" must never be what a deleted file looks like."""
    write_repository(tmp_path, modules={"things.py": client_module()})
    coverage = load_coverage(tmp_path)
    (tmp_path / REGISTRY_PATH).unlink()
    missing, _ = compare_registry(coverage.entries, tmp_path)
    assert missing is not None and missing.code == codes.REGISTRY_MISSING


def test_an_excused_call_that_changed_its_route_is_no_longer_excused(tmp_path):
    """#203's correction, applied here.

    Keyed on the site alone, a dead method rewritten to call a DIFFERENT
    nonexistent route would stay excused by an entry describing the old one,
    and the ledger would look like it was doing its job. The key carries the
    route, so the excuse stops covering it.
    """
    site = f"{SHELL_ROOT}/things.py::ThingsClient.call_0"
    gone, elsewhere = f"GET {ROOT}/gone", f"GET {ROOT}/somewhere-else"
    excuse = excusing((site, gone))

    coverage = accepted(tmp_path / "matching", ledger=excuse, modules={
        "things.py": client_module(
            f"*ops.{registry_module.unpublished_name(gone)}")})
    assert coverage.excused == ((site, gone),)

    # The route moved and the ledger did not. The registry generated from that
    # ledger has no constant for the new one, so the wrapper cannot even name
    # it — and the entry describing the old one is reported as spent.
    moved = excusing((site, elsewhere))
    invalid = rejection(tmp_path / "moved", ledger=moved, modules={
        "things.py": client_module(
            f"*ops.{registry_module.unpublished_name(gone)}")})
    reported = invalid.codes()
    assert codes.NO_SUCH_OPERATION_CONSTANT in reported, (
        "the constant for the old route is gone with its entry")
    assert codes.EXCUSE_NOT_A_VIOLATION in reported, (
        "and the entry describing the new one excuses a call nobody makes")


def test_an_excuse_for_a_call_that_now_resolves_is_reported(tmp_path):
    """Paying a debt and deleting its entry are one act."""
    invalid = rejection(
        tmp_path,
        operations=(THING_LIST,),
        ledger=excusing((f"{SHELL_ROOT}/things.py::ThingsClient.call_0",
                         f"GET {ROOT}/things")),
        modules={"things.py": client_module(call("things_list"))})
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
    assert codes.GENERATED_CLIENT_EMPTY in must_refuse(tmp_path).codes()


def test_a_missing_contract_fails_rather_than_reporting_a_clean_surface(tmp_path):
    """Reading zero operations must never look like agreement."""
    write_repository(tmp_path, modules={"things.py": client_module()})
    (tmp_path / SPEC_PATH).unlink()
    assert codes.SPEC_MISSING in must_refuse(tmp_path).codes()


def test_a_missing_hand_shell_fails_rather_than_reporting_a_clean_surface(tmp_path):
    """And neither must walking zero modules."""
    write_repository(tmp_path, modules={"things.py": client_module()})
    for name in ("things.py", "_operations.py"):
        (tmp_path / SHELL_ROOT / name).unlink()
    assert codes.SHELL_EMPTY in must_refuse(tmp_path).codes()


def test_the_manifest_renders_the_same_bytes_twice(tmp_path):
    """Determinism, for the same reason as the registry's."""
    coverage = accepted(tmp_path, modules={
        "things.py": client_module(call("things_list"),
                                   call("things_read", "thing_id"))})
    assert render(coverage) == render(coverage)
    assert render(coverage).endswith("\n")


def test_a_missing_manifest_is_a_different_fault_from_a_stale_one(tmp_path):
    """"No differences found" must never be what a deleted manifest looks like."""
    coverage = accepted(tmp_path, modules={"things.py": client_module()})
    missing, _ = compare(coverage, tmp_path)
    assert missing is not None and missing.code == codes.MANIFEST_MISSING


# ---------------------------------------------------------------------------
# 4. The ratchet: no operation becomes unwrapped without a signature
# ---------------------------------------------------------------------------

def manifest_document(unwrapped=(), wrapped=()):
    """A manifest naming exactly which operations are unwrapped.

    The comparison is over identities, not over `summary.unwrapped`, so these
    controls have to name operations. That is the point of the shape: `wrap
    three, publish two` is the case a count cannot see.
    """
    rows = [{"operation_id": name, "method": "GET", "path": f"/api/v1/{name}",
             "disposition": GENERATED_ONLY} for name in unwrapped]
    rows += [{"operation_id": name, "method": "GET", "path": f"/api/v1/{name}",
              "disposition": WRAPPED, "wrapped_by": ["x.py::C.m"]}
             for name in wrapped]
    return {"version": 1,
            "summary": {"operations": len(rows), "unwrapped": len(unwrapped)},
            "operations": rows}


def authorisations(*entries):
    return {"version": 1, "authorisations": [
        {"id": identifier, "issue": 204, "operations_added": count,
         "reason": "a synthetic authorisation."}
        for identifier, count in entries]}


def test_a_new_gap_with_no_authorisation_is_refused():
    comparison = ratchet_compare(manifest_document(("a", "b")),
                                 manifest_document(("a", "b", "c")),
                                 authorisations(), authorisations())
    assert not comparison.ok
    assert comparison.faults[0].code == codes.UNWRAPPED_ROSE
    assert "c" in comparison.faults[0].message, "the message must name the gap"


def test_a_new_gap_licensed_by_a_new_authorisation_is_allowed():
    comparison = ratchet_compare(manifest_document(("a", "b")),
                                 manifest_document(("a", "b", "c")),
                                 authorisations(), authorisations(("new", 1)))
    assert comparison.ok, [str(fault) for fault in comparison.faults]
    assert comparison.opened == ("c",)


def test_wrapping_more_than_you_open_still_needs_a_signature():
    """The hole a net count cannot see, and the reason this compares identities.

    Wrap three operations and publish two unwrapped ones and the net is −1: no
    rise, no signature, two new gaps merged unreviewed — and an author who
    wrote an authorisation anyway would have had it refused as inert. Comparing
    the SETS makes this two additions, whatever the total does.
    """
    comparison = ratchet_compare(
        manifest_document(unwrapped=("a", "b", "c")),
        manifest_document(unwrapped=("d", "e"), wrapped=("a", "b", "c")),
        authorisations(), authorisations())
    assert not comparison.ok
    assert comparison.faults[0].code == codes.UNWRAPPED_ROSE
    assert comparison.opened == ("d", "e")
    assert comparison.closed == ("a", "b", "c")


def test_an_authorisation_carried_over_from_the_base_licenses_nothing():
    """Otherwise the file is standing permission wearing an audit trail's clothes."""
    old = authorisations(("already-there", 5))
    comparison = ratchet_compare(manifest_document(("a",)),
                                 manifest_document(("a", "b")), old, old)
    assert not comparison.ok
    assert comparison.faults[0].code == codes.UNWRAPPED_ROSE


def test_an_authorisation_that_miscounts_is_refused():
    """A reviewer approves a quantity, not an intention."""
    comparison = ratchet_compare(manifest_document(("a",)),
                                 manifest_document(("a", "b")),
                                 authorisations(), authorisations(("new", 4)))
    assert not comparison.ok
    assert comparison.faults[0].code == codes.AUTHORISATION_COUNT_WRONG


def test_an_authorisation_that_licenses_nothing_is_refused():
    """An override that overrides nothing is the shape of a check that cannot fail."""
    comparison = ratchet_compare(manifest_document(("a",)),
                                 manifest_document(("a",)),
                                 authorisations(), authorisations(("new", 2)))
    assert not comparison.ok
    assert comparison.faults[0].code == codes.AUTHORISATION_INERT


def test_closing_gaps_needs_no_authorisation_at_all():
    """Nothing here demands the count shrink, and nothing penalises it either."""
    comparison = ratchet_compare(manifest_document(("a", "b", "c")),
                                 manifest_document(unwrapped=("a",),
                                                   wrapped=("b", "c")),
                                 authorisations(), authorisations())
    assert comparison.ok
    assert comparison.rise == 0 and comparison.closed == ("b", "c")


def test_a_base_with_no_manifest_treats_every_gap_as_new():
    """A branch taken before this ticket landed genuinely has no manifest, and
    every unwrapped operation in the proposal genuinely is new — which is what
    makes this pull request's own authorisation load-bearing."""
    comparison = ratchet_compare({}, manifest_document(("a", "b")),
                                 {}, authorisations(("seed", 2)))
    assert comparison.ok
    assert comparison.opened == ("a", "b")


@pytest.fixture
def repository(tmp_path):
    """A real git repository with a manifest committed on `main`.

    Real git, because resolving the base ref is the one part a pure comparison
    cannot reach — and it is the part that decides whether the gate runs.
    """
    git(tmp_path, "init", "-b", "main", str(tmp_path))
    git(tmp_path, "config", "user.email", "ci@example.invalid")
    git(tmp_path, "config", "user.name", "CI")
    _commit(tmp_path, manifest_document(("a", "b")), authorisations(),
            "as it stands")
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


def test_a_branch_that_opens_a_gap_fails_against_its_base(repository):
    git(repository, "checkout", "-b", "feature")
    _commit(repository, manifest_document(("a", "b", "c")), authorisations(),
            "one more gap")
    comparison = ratchet_run(repository, "main")
    assert not comparison.ok
    assert comparison.faults[0].code == codes.UNWRAPPED_ROSE


def test_a_branch_that_opens_one_with_a_signature_passes(repository):
    git(repository, "checkout", "-b", "feature")
    _commit(repository, manifest_document(("a", "b", "c")),
            authorisations(("new", 1)), "one more gap, signed for")
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


def test_the_regeneration_step_covers_the_registry_as_well_as_the_manifest():
    """One `--write` produces both generated artifacts, and CI's dirty-worktree
    check sees both. If the registry were written by a command nobody runs, a
    stale one could merge and every wrapper would follow it."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/ci.yml").read_text("utf-8"))
    steps = workflow["jobs"]["contracts"]["steps"]
    step = next(one for one in steps
                if "python -m tools.sdk_operations --write" in str(one.get("run", "")))
    assert "git status --porcelain" in step["run"], (
        "the zero-diff check is what makes --write a gate rather than a fixer")


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
