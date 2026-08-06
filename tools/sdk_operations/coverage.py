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

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tools.sdk_operations import errors as codes
from tools.sdk_operations import registry
from tools.sdk_operations.calls import (
    GENERATED_PACKAGE, ROUTE_MARKER, SHELL_ROOT, load_call_sites,
)
from tools.sdk_operations.errors import SurfaceError, SurfaceInvalid
from tools.sdk_operations.spec import SPEC_PATH, load_operations, template

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
    entries: dict = field(default_factory=dict)   # the registry the contract renders

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
    excuses = _excused_invalid_calls(repo_root, errors)

    # The registry first, because every call resolves through it. `expected` is
    # what the contract and the ledger render; `committed` is what the SDK
    # actually imports, and the calls are resolved against THAT — a gate that
    # resolved against the renderer would pass on a registry nobody could
    # import. Where the two disagree is reported below, per operation.
    expected = registry.expected_entries(operations, excuses, errors)
    committed = registry.load(repo_root, errors)
    _check_the_registry_is_the_contract(committed, expected, errors)

    sites, documented, call_errors = load_call_sites(
        repo_root, committed if committed else None)
    errors += call_errors

    _check_the_route_marker_still_holds(operations, errors)
    _check_documented_routes(documented, operations, excuses, errors)
    generated = _generated_operation_ids(repo_root, operations, errors)

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

    for site, route in sorted(set(excuses) - used_excuses):
        errors.append(SurfaceError(
            codes.EXCUSE_NOT_A_VIOLATION,
            f"{LEDGER_PATH}: {excuses[(site, route)]}",
            f"excuses `{route}` at {site}, and no such invalid call is there "
            f"any more. Paying a debt and deleting its entry are one act: an "
            f"entry that outlives the violation it records is a suppression "
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
    return Coverage(rows=rows, excused=tuple(sorted(used_excuses)),
                    entries=expected), errors


def rebuild_registry(repo_root):
    """Regenerate the operation registry alone; return ``(rewritten, errors)``.

    Separated from :func:`assess` and run BEFORE it, because the registry is
    what every call resolves against and it is generated from the contract and
    the ledger alone — it needs to know nothing about the hand shell. Folded
    into the main pass, a contract change would be unfixable by the command
    that fixes it: the stale registry would fail 81 calls, `--write` would
    refuse to run while calls fail, and the only way out would be to hand-edit
    the file the banner forbids hand-editing.
    """
    repo_root = Path(repo_root)
    operations, errors = load_operations(repo_root)
    excuses = _excused_invalid_calls(repo_root, errors)
    entries = registry.expected_entries(operations, excuses, errors)
    if errors or not entries:
        return False, errors
    return registry.write(entries, repo_root), errors


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


def _check_the_registry_is_the_contract(committed, expected, errors):
    """The committed registry declares exactly what the contract publishes.

    Three ways it can be wrong, and they are separate codes because they are
    separate mistakes with separate fixes: an operation it fails to name, a
    name it declares that nothing publishes, and — the one ADR-0007 §4 is most
    insistent about — a name whose method or path is not its operation's.

    That third case is where #155 §8.5's second required control now lives. A
    valid path under the wrong HTTP method used to be writable at any of 81
    call sites; since #209 a call site cannot spell a method at all, so the one
    place the mistake survives is a hand edit to this file. Which is precisely
    why it is checked here rather than declared unreachable: a rule that
    describes its own violation as impossible is a rule nothing enforces.
    """
    if not committed or not expected:
        return          # already reported, and 134 more errors would bury it

    for name, entry in sorted(expected.items()):
        if name not in committed:
            errors.append(SurfaceError(
                codes.REGISTRY_INCOMPLETE, f"{registry.REGISTRY_PATH}: {name}",
                f"`{entry}` is published as `{entry.operation_id}` and the "
                f"registry does not name it, so no wrapper can reach it. Run "
                f"`python -m tools.sdk_operations --write`."))

    for name, entry in sorted(committed.items()):
        wanted = expected.get(name)
        if wanted is None:
            errors.append(SurfaceError(
                codes.REGISTRY_ENTRY_UNKNOWN, f"{registry.REGISTRY_PATH}: {name}",
                f"declares `{entry}`, which the contract does not publish and "
                f"the ledger does not excuse. A constant nothing stands behind "
                f"is a route literal with a nicer name — the exact thing this "
                f"registry replaced."))
            continue
        if (entry.method, entry.path) != (wanted.method, wanted.path):
            errors.append(SurfaceError(
                codes.REGISTRY_ENTRY_WRONG, f"{registry.REGISTRY_PATH}: {name}",
                f"declares `{entry}` and the contract publishes `{wanted}`. "
                f"Method AND path make an operation (ADR-0007 §4): reading a "
                f"resource is not writing it, and every wrapper naming this "
                f"constant would call the wrong one."))
        elif entry.operation_id != wanted.operation_id:
            errors.append(SurfaceError(
                codes.REGISTRY_ENTRY_WRONG, f"{registry.REGISTRY_PATH}: {name}",
                f"carries `{entry.operation_id}` and the contract calls this "
                f"operation `{wanted.operation_id}`. The identifier is what "
                f"the coverage manifest credits, so a wrong one wraps the "
                f"wrong row."))


def _check_documented_routes(documented, operations, excuses, errors):
    """A docstring may name a route; it may not name one that does not exist.

    #209's claim is that a route rename cannot leave a stale string behind in
    the SDK, and a docstring is a string. Every client method here documents
    the route it calls — deliberately, as public documentation — so the answer
    is not to delete them but to hold them to the contract like everything
    else. When this ticket was written 48 of the 53 documented routes resolved
    exactly, 4 named a family, and one named a route deleted long ago.

    Three ways to be legitimate:

    - **The route itself**, collapsed the way every identity here is collapsed.
    - **A family** — `/api/v1/metering/` in a class docstring saying what the
      client is for. Accepted as a prefix of something published, so it still
      goes stale if the whole family moves.
    - **A route the ledger excuses**, because the three dead calls are
      documented by the methods that make them until slice 4 deletes both.

    The method a docstring writes beside a route is deliberately not checked.
    Prose says `via POST /api/v1/metering/usage`, but it also says things like
    "PUT to update"; parsing English for an HTTP verb would make the rule
    depend on sentence shape, and a gate that is wrong about grammar gets
    turned off rather than obeyed. The path is the part that goes stale on a
    rename, and the path is what is checked.
    """
    if not operations:
        return          # the contract did not read; every route would be stale

    published = {operation.template for operation in operations.values()}
    excused = {template(found.partition(" ")[2]) for _, found in excuses}

    for route in documented:
        collapsed = template(route.text)
        if collapsed in published or collapsed in excused:
            continue
        # A family, by whole segments. `/api/v1/metering/` covers
        # `/api/v1/metering/usage`; a bare character prefix would also let
        # `/api/v1/thing` stand for `/api/v1/things`, which is a typo passing
        # for a generalisation.
        family = collapsed.rstrip("/")
        if any(one == family or one.startswith(family + "/")
               for one in published):
            continue
        errors.append(SurfaceError(
            codes.STALE_DOCUMENTED_ROUTE, route.location,
            f"the documentation names `{route.text}`, which the contract does "
            f"not publish, is not the start of anything it publishes, and the "
            f"ledger does not excuse. A rename that fixed the call and left "
            f"the docstring is still a stale route in the SDK — the failure "
            f"#155 §8.3 names, one layer out."))


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
