"""The two-way check: every call reaches an operation, every operation has a disposition.

ADR-0007 §4 asks for two separate properties and this module settles both from
the same join, because they are the same table read in two directions.

**Forward.** Every hand-written call resolves to a published operation, matched
on the complete identity — method AND normalised path. Three calls do not, and
they are the reason this gate exists: `/api/v1/metering/pricing/rate-cards/…`
in three shapes that exist in no spec and no router, green in CI for months.
They are excused by name from `gates/migration-ledger.yaml`, which only shrinks
and reaches zero before the cutover.

**Reverse.** Every published operation carries a disposition, and all three are
**derived from evidence** rather than declared:

| Disposition | The evidence |
|---|---|
| `wrapped` | a hand-written call resolves to it |
| `generated_only` | no hand-written call, but `ubb/_core` has its module |
| `not_yet_wrapped` | no hand-written call and no generated module either |

Deriving them is the whole point. A hand-maintained classification would be a
second copy of a fact the tree already states, and "do the two copies agree?"
is the question this programme exists to stop asking — a declared
`generated_only` is either redundant with the generated module or wrong about
it. What a human cannot derive is whether an *increase* was intended, and that
is exactly what :mod:`tools.sdk_operations.ratchet` requires a signature for.

`not_yet_wrapped` is empty today and is not dead vocabulary. The pinned
generator produces one module per operation, and G16 proves the committed
`_core` is what it produces — but G16 compares the generator against itself, so
an operation the generator silently *skips* is missing from both sides and G16
stays green. This row is what would notice. It is the same shape as
`.gitignore`'s unanchored `lib/` dropping twenty-two modules for weeks, which
#158 §16 records; a count that has always been zero is worth keeping precisely
because the day it is not, nothing else is looking.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from tools.sdk_operations import errors as codes
from tools.sdk_operations.calls import (
    GENERATED_PACKAGE, ROUTE_MARKER, SHELL_ROOT, load_call_sites,
)
from tools.sdk_operations.errors import SurfaceError, SurfaceInvalid
from tools.sdk_operations.spec import SPEC_PATH, load_operations

#: The three dispositions, from ADR-0007 §4. They are restated here rather than
#: taken from `domain-vocabulary/` on the same rule that puts the gate statuses
#: in `gates/schema.yaml`: the registry holds the tenant-facing product
#: vocabulary, and this is repository bookkeeping about a build artifact.
WRAPPED = "wrapped"
GENERATED_ONLY = "generated_only"
NOT_YET_WRAPPED = "not_yet_wrapped"

DISPOSITIONS = (WRAPPED, GENERATED_ONLY, NOT_YET_WRAPPED)

#: Where the generated client's per-operation modules live. Searched
#: recursively rather than pinned to `api/default/`, because the generator lays
#: them out by tag: adding one tag to the spec would move every module and a
#: pinned directory would report the whole surface unreachable overnight.
GENERATED_API_ROOT = f"{SHELL_ROOT}/{GENERATED_PACKAGE}/api"

#: The gate whose debts the migration ledger carries for the forward direction.
FORWARD_GATE = "G17"

LEDGER_PATH = "gates/migration-ledger.yaml"


@dataclass(frozen=True)
class Row:
    """One published operation, and what the SDK does about it."""

    operation_id: str
    method: str
    path: str
    disposition: str
    wrapped_by: tuple = ()

    @property
    def is_wrapped(self):
        return self.disposition == WRAPPED


@dataclass(frozen=True)
class Coverage:
    """The whole join: one row per published operation, plus what was excused."""

    rows: tuple
    excused: tuple          # the invalid calls the ledger currently carries

    def counts(self):
        """``{disposition: how many}`` over every disposition, including zeros.

        Every disposition is present whether or not it has rows: a count that
        vanishes when it reaches zero cannot be seen to rise again.
        """
        counts = {disposition: 0 for disposition in DISPOSITIONS}
        for row in self.rows:
            counts[row.disposition] += 1
        return counts

    @property
    def unwrapped(self):
        """How many published operations have no ergonomic wrapper.

        The number ADR-0007 §4 says need not reach zero but may not rise
        unreviewed. Derived from the rows rather than stored beside them, so it
        cannot disagree with the table it summarises.
        """
        return sum(1 for row in self.rows if not row.is_wrapped)


def assess(repo_root):
    """The coverage of the committed contract by the hand-written SDK.

    Returns ``(Coverage, errors)``. Everything wrong is collected rather than
    raised, so one run tells an author the whole story;
    :func:`load_coverage` is the entry point that turns a non-empty list into
    a failure.
    """
    repo_root = Path(repo_root)
    operations, errors = load_operations(repo_root)
    sites, call_errors = load_call_sites(repo_root)
    errors += call_errors

    _check_the_route_marker_still_holds(operations, errors)
    generated = _generated_operation_ids(repo_root, operations, errors)
    excuses = _excused_invalid_calls(repo_root, errors)

    wrappers = {}
    used_excuses = set()
    for site in sites:
        operation = operations.get(site.identity)
        if operation is not None:
            wrappers.setdefault(operation.operation_id, []).append(site.site)
            continue
        excuse = (site.site, f"{site.method} {site.template}")
        if excuse in excuses:
            used_excuses.add(excuse)
            continue
        if not operations:
            # The contract did not read. Reporting all 81 calls as unmatched
            # would bury the one error that explains them, and an author would
            # fix eighty-one things to discover they had one problem.
            continue
        errors.append(SurfaceError(
            codes.NO_SUCH_OPERATION, f"{site.module}:{site.line}",
            f"{site.qualname}() calls `{site}`, which the contract does not "
            f"publish. Either the route is wrong, or the method is: "
            f"{_near_misses(site, operations)}"))

    for excuse in sorted(set(excuses) - used_excuses):
        errors.append(SurfaceError(
            codes.EXCUSE_NOT_A_VIOLATION, f"{LEDGER_PATH}: {excuses[excuse]}",
            f"excuses `{excuse[1]}` at {excuse[0]}, and no such invalid call is "
            f"there any more. Paying a debt and deleting its entry are one act: "
            f"an entry that outlives the violation it records is a suppression "
            f"nothing will ever clear."))

    rows = tuple(
        Row(operation_id=operation.operation_id, method=operation.method,
            path=operation.path,
            disposition=_disposition(operation, wrappers, generated),
            # Deduplicated: a method that calls one operation twice reaches it
            # once, and a name repeated in a generated file is noise a reviewer
            # has to decide is harmless.
            wrapped_by=tuple(sorted(set(wrappers.get(operation.operation_id, ())))))
        for _, operation in sorted(operations.items(),
                                   key=lambda item: item[1].operation_id)
    )
    return Coverage(rows=rows, excused=tuple(sorted(used_excuses))), errors


def load_coverage(repo_root):
    """:func:`assess`, raising :class:`SurfaceInvalid` if anything is wrong.

    The entry point CI, the CLI and every negative control go through, so a
    control exercises the real decision rather than a rehearsal of it.
    """
    coverage, errors = assess(repo_root)
    if errors:
        raise SurfaceInvalid(errors)
    return coverage


def _disposition(operation, wrappers, generated):
    if operation.operation_id in wrappers:
        return WRAPPED
    if operation.operation_id in generated:
        return GENERATED_ONLY
    return NOT_YET_WRAPPED


def _near_misses(site, operations):
    """What the contract does publish at this path, or at this method.

    A bare "no such operation" makes an author diff two strings by eye. Naming
    the other methods on the same path turns the commonest real mistake —
    ADR-0007 §4's `GET /x/{id}` against `POST /x/{id}` — into a sentence.
    """
    same_path = sorted(str(operation) for identity, operation
                       in operations.items() if identity[1] == site.template)
    if same_path:
        return ("the contract publishes " + ", ".join(f"`{one}`" for one in same_path)
                + " at that path, and nothing else.")
    return "the contract publishes nothing at that path under any method."


def _check_the_route_marker_still_holds(operations, errors):
    """Every published path begins with the marker the stray-literal sweep uses.

    :data:`~tools.sdk_operations.calls.ROUTE_MARKER` decides which strings in
    the hand shell are routes. If the contract ever publishes outside that root
    the sweep silently stops seeing a whole family of them — a gate narrowing
    without a diff, which is the failure this programme was built to refuse. So
    the marker's premise is checked rather than assumed.
    """
    outside = sorted(str(operation) for operation in operations.values()
                     if not operation.path.startswith(ROUTE_MARKER))
    if outside:
        errors.append(SurfaceError(
            codes.ROUTE_MARKER_STALE, SPEC_PATH,
            f"{len(outside)} published path(s) do not begin with "
            f"`{ROUTE_MARKER}`, which is what tells a route literal from prose "
            f"in the hand shell: {', '.join(outside[:5])}. Widen the marker in "
            f"`tools/sdk_operations/calls.py` — leaving it would exempt these "
            f"routes from the sweep without saying so."))


def _generated_operation_ids(repo_root, operations, errors):
    """Which operations the generated client has a module for.

    The module's stem is its `operationId`, which is how the generator names
    them. A tree with no modules at all is refused rather than reported as 134
    unreachable operations: that is a broken read, and it would produce a
    manifest that looks like a catastrophe instead of a bug.
    """
    root = repo_root / GENERATED_API_ROOT
    found = {path.stem for path in root.rglob("*.py")
             if path.stem != "__init__"} if root.is_dir() else set()
    if operations and not found:
        errors.append(SurfaceError(
            codes.GENERATED_CLIENT_EMPTY, GENERATED_API_ROOT,
            "the generated client has no operation modules. Every published "
            "operation would be classified `not_yet_wrapped` at once, which "
            "describes a missing directory rather than an SDK with no reach."))
    return found


def _excused_invalid_calls(repo_root, errors):
    """``{(site, "METHOD /template"): entry id}`` for the ledger's G17 debts.

    Read straight from `gates/migration-ledger.yaml` rather than through
    `tools.gates.load_programme`: the ledger's own validity is that compiler's
    job and is already gated in this suite, and coupling the two would make
    this gate report an unrelated manifest fault as an SDK problem.

    The key carries `found` as well as the site, which is #203's correction
    applied here. Keyed on the site alone, a dead method rewritten to call a
    *different* nonexistent route would stay excused by an entry describing the
    old one, and the ledger would look like it was doing its job.
    """
    path = repo_root / LEDGER_PATH
    if not path.is_file():
        return {}
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as broken:
        errors.append(SurfaceError(codes.EXCUSE_UNREADABLE, LEDGER_PATH,
                                   f"the ledger does not parse: {broken}"))
        return {}

    excuses = {}
    for body in (document.get("entries") or []):
        if not isinstance(body, dict) or body.get("gate") != FORWARD_GATE:
            continue
        site, found = body.get("site"), body.get("found")
        if isinstance(site, str) and isinstance(found, str):
            excuses[(site, found)] = body.get("id", "an entry with no id")
    return excuses
