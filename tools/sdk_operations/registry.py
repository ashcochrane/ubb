"""The one registry: the contract's operations, rendered as names the SDK uses.

#155 §8.3 gives two ways to stop a route rename leaving a stale string behind
in the SDK — prohibit path literals in the hand-written layer, or confine them
to **one mechanically checked registry**. This module is that registry's
generator, and it takes both routes at once: `ubb-sdk/ubb/_operations.py` is the
only file under `ubb-sdk/ubb/` allowed to spell a path, and it is generated, so
nobody spells one there either.

## What it is generated from, and why that is two files

**`openapi/v1.json`** publishes the operations, and each becomes a constant
named for its `operationId` — the identifier ADR-0007 §4 prefers over the
method-and-path pair. Rename an operation in the contract and its constant is
renamed with it, so every wrapper still referring to the old name stops
resolving. That is the whole mechanism: a stale reference cannot be a *string*
any more, so it cannot go unnoticed.

**`gates/migration-ledger.yaml`** carries the three calls to routes that exist
in no spec and no router (#204). They must keep working until slice 4 deletes
the methods, and they cannot come from the contract, because the contract is
exactly what does not have them. They come from the ledger instead — which
means the day a debt is paid and its entry deleted, the constant disappears and
the method that owed it stops resolving. Paying a debt and deleting its entry
were already one act; now they are also one edit.

Their names are deliberately unlovely::

    UNPUBLISHED_PUT_METERING_PRICING_RATE_CARDS

Nobody reads that at a call site and thinks the line is fine. The name is
derived from the ledger's `found` — the method and the collapsed path, which is
the identity the gate excuses — rather than from the entry's `id`, so an editor
retitling an entry cannot silently rename a constant, and two debts cannot
share a name without this module saying so.

## Why every published operation, not only the 78 that are called

Generating only the called ones would make the registry a function of the hand
shell, and the hand shell a function of the registry. Nothing would break
immediately; it would simply become impossible to say which was the source. The
rule here is the simpler one — *the contract, rendered as names* — and the 56
constants no wrapper uses yet are the vocabulary the next wrapper is written
in, not dead weight.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from tools.sdk_operations import errors as codes
from tools.sdk_operations.errors import SurfaceError
from tools.sdk_operations.spec import SPEC_PATH, template

#: The generated registry, relative to the git root.
REGISTRY_PATH = "ubb-sdk/ubb/_operations.py"

#: The hand-written type the registry's constants are instances of. The
#: generated file's import is derived from this path rather than spelled again,
#: so moving the module cannot leave the artifact importing a name that is not
#: there — which no test would catch, because the gate reads source and never
#: imports the SDK.
OPERATION_TYPE_PATH = "ubb-sdk/ubb/_operation.py"
OPERATION_TYPE_IMPORT = OPERATION_TYPE_PATH[len("ubb-sdk/"):-len(".py")].replace("/", ".")

#: The ledger, which supplies the routes the contract does not publish.
LEDGER_PATH = "gates/migration-ledger.yaml"

#: The name the constructor is spelled with, in the generated file and in the
#: reader below. One constant so the two cannot drift apart.
CONSTRUCTOR = "Operation"

#: What marks a constant as a route the contract does not publish.
UNPUBLISHED_PREFIX = "UNPUBLISHED_"

#: Where a rendered assignment stops fitting on one line. Only affects layout,
#: but it must be a constant: the comparison is over bytes, so a width that
#: varied by machine would make the zero-diff gate fail at random.
LINE_BUDGET = 88

_BANNER = (
    f"# @generated from {SPEC_PATH} and {LEDGER_PATH} — do not edit by hand.\n"
    "# Regenerate with `python -m tools.sdk_operations --write`.\n"
)

_DOCSTRING = '''"""Every operation this SDK can reach, named by the contract that publishes it.

The single place in `ubb-sdk/ubb/` where a versioned path is spelled (#209,
#155 §8.3). A hand-written method references a constant here rather than
carrying a path string of its own, so renaming an operation in the contract
renames its constant and every stale reference stops resolving — which is
checked by `tools/sdk_operations`, in CI, before anything is called.

Two call shapes, decided by the path rather than by preference::

    self._request(*ops.API_V1_TENANT_ENDPOINTS_GET_TENANT_CONFIG)
    self._request(*ops.API_V1_PLAN_ENDPOINTS_UPDATE_PLAN(key), json=body)

A route with no parameters unpacks; a route with parameters is called with one
value per position, in the order the path spells them. Getting that wrong is a
`TypeError` from :class:`ubb._operation.Operation` and a red gate before that.

Constants prefixed `UNPUBLISHED_` name routes the contract does NOT publish.
They exist because three methods call them and the migration ledger excuses
those calls until slice 4 removes the methods. They are generated from the
ledger, so a debt cannot be quietly paid: delete the entry and the constant
goes with it.
"""'''

_PUBLISHED_HEADING = f"""
# --- published operations ----------------------------------------------------
#
# One per operation in {SPEC_PATH}, named for its `operationId`.
# Sorted by name, so a contract that gains an operation produces one insertion
# rather than a reshuffle nobody can review.
"""

_UNPUBLISHED_HEADING = f"""
# --- routes the contract does not publish ------------------------------------
#
# The debts {LEDGER_PATH} carries against G17: routes that exist in no spec and
# no router, called by methods slice 4 removes. Each name is derived from the
# `found` the ledger excuses, so the constant and the excuse cannot drift.
"""


@dataclass(frozen=True)
class Entry:
    """One constant in the registry: what it is called, and what it reaches."""

    name: str                # `API_V1_PLAN_ENDPOINTS_GET_PLAN`
    operation_id: str | None  # `None` for a route the ledger excuses
    method: str              # `get` — lowercase, because it names the httpx verb
    path: str                # `/api/v1/plans/{plan_key}`

    @property
    def identity(self):
        """``(METHOD, template)`` — the key the contract is matched on."""
        return self.method.upper(), template(self.path)

    @property
    def arity(self):
        """How many values filling this path takes.

        Counted off the collapsed template rather than with a second brace
        scanner, so this agrees with `ubb/_operation.py` by construction: both
        derive from the same collapse the gate matches identities on.
        """
        return self.identity[1].count("{}")

    @property
    def is_published(self):
        return self.operation_id is not None

    def __str__(self):
        return f"{self.method.upper()} {self.path}"


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def constant_name(operation_id):
    """The constant a published operation is reached by."""
    return operation_id.upper()


def unpublished_name(found):
    """The constant a ledger-excused route is reached by.

    ``found`` is the ledger's own `METHOD /path/with/{}/collapsed`. The name
    keeps the method and every literal segment and drops the parameter
    positions, which is enough to tell the three debts apart and short enough
    to read — while still being long and graceless enough that nobody mistakes
    the call site for ordinary code.
    """
    method, _, path = found.partition(" ")
    segments = [segment for segment in path.split("/")
                if segment and not segment.startswith("{")]
    words = "_".join(segments).replace("-", "_").replace(".", "_")
    return f"{UNPUBLISHED_PREFIX}{method.upper()}_{_strip_version(words)}"


def _strip_version(words):
    """Drop the `api_v1` every path begins with; it distinguishes nothing."""
    for prefix in ("api_v1_", "api_v1"):
        if words.startswith(prefix):
            return words[len(prefix):].upper()
    return words.upper()


# ---------------------------------------------------------------------------
# What the registry SHOULD hold, given the contract and the ledger
# ---------------------------------------------------------------------------

def expected_entries(operations, debts, errors):
    """``{name: Entry}`` for the contract's operations plus the ledger's debts.

    ``debts`` is ``{(site, found): entry id}`` as
    :func:`tools.sdk_operations.coverage._excused_invalid_calls` reads it. Two
    debts on the same route produce one constant, which is correct: they are
    two methods calling one nonexistent route.
    """
    entries, claimed = {}, {}
    for operation in sorted(operations.values(), key=lambda one: one.operation_id):
        name = constant_name(operation.operation_id)
        if not name.isidentifier():
            errors.append(SurfaceError(
                codes.OPERATION_ID_NOT_A_NAME, f"{SPEC_PATH}: {operation}",
                f"`{operation.operation_id}` does not become a Python name. "
                f"The registry reaches every operation by one, so an "
                f"operationId that cannot be spelled as a constant is an "
                f"operation the SDK cannot name."))
            continue
        if name in claimed:
            errors.append(SurfaceError(
                codes.REGISTRY_NAME_COLLISION, f"{SPEC_PATH}: {operation}",
                f"`{name}` already names {claimed[name]}. Two operations under "
                f"one constant would let a wrapper for either resolve against "
                f"the other, which is the confusion this registry removes."))
            continue
        claimed[name] = str(operation)
        entries[name] = Entry(name, operation.operation_id,
                              operation.method.lower(), operation.path)

    for found in sorted({found for _, found in debts}):
        name = unpublished_name(found)
        method, _, path = found.partition(" ")
        if name in claimed and claimed[name] != found:
            errors.append(SurfaceError(
                codes.REGISTRY_NAME_COLLISION, f"{LEDGER_PATH}: {found}",
                f"`{name}` already names {claimed[name]}. A debt cannot share "
                f"a constant with anything else — the call site would be "
                f"excused for reaching something it does not reach."))
            continue
        claimed[name] = found
        entries[name] = Entry(name, None, method.lower(), path)
    return entries


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(entries):
    """The registry module's full text for these entries."""
    published = [entry for entry in entries.values() if entry.is_published]
    unpublished = [entry for entry in entries.values() if not entry.is_published]

    lines = [_BANNER + _DOCSTRING, "",
             f"from {OPERATION_TYPE_IMPORT} import {CONSTRUCTOR}", ""]
    lines.append(_PUBLISHED_HEADING.strip("\n"))
    lines.append("")
    lines += _assignments(published)
    if unpublished:
        lines.append("")
        lines.append(_UNPUBLISHED_HEADING.strip("\n"))
        lines.append("")
        lines += _assignments(unpublished)
    return "\n".join(lines) + "\n"


def _assignments(entries):
    """One assignment per entry, wrapped by width and by nothing else.

    Three layouts, in order of preference, and which one applies is a pure
    function of the text — never of the machine, the terminal or the order the
    entries arrived in. The comparison in :func:`compare` is over bytes, so a
    layout that depended on anything else would make the zero-diff gate fail at
    random, and a gate that cries wolf gets disabled rather than obeyed.
    """
    lines = []
    for entry in sorted(entries, key=lambda one: one.name):
        identifier = ("None" if entry.operation_id is None
                      else _quote(entry.operation_id))
        arguments = [identifier, _quote(entry.method), _quote(entry.path)]
        opening = f"{entry.name} = {CONSTRUCTOR}("
        joined = ", ".join(arguments)

        if len(opening) + len(joined) + 1 <= LINE_BUDGET:
            lines.append(f"{opening}{joined})")
        elif len(joined) + 5 <= LINE_BUDGET:
            lines += [opening, f"    {joined})"]
        else:
            lines.append(opening)
            lines += [f"    {argument}," for argument in arguments[:-1]]
            lines.append(f"    {arguments[-1]})")
    return lines


def _quote(text):
    """A single-quoted literal, matching `tools/vocabulary`'s generated output.

    Never `repr`: a path containing an apostrophe would silently switch quote
    style and change the file's bytes for a reason no reviewer could see. There
    are none today, and a path that gained one would be refused by the reader
    below rather than rendered wrong.
    """
    return "'" + text + "'"


# ---------------------------------------------------------------------------
# Reading the committed registry back
# ---------------------------------------------------------------------------

def load(repo_root, errors):
    """``{name: Entry}`` as the committed registry actually declares them.

    Statically, with :mod:`ast`. Read rather than assumed-equal-to-`render`
    for the same reason the whole gate reads source: what the SDK imports is
    the committed file, and a check that compared the renderer with itself
    would pass on a registry nobody could import. The byte comparison in
    :func:`compare` catches a hand edit; this catches what that edit MEANT, and
    reports it against the operation rather than as a diff.
    """
    path = Path(repo_root) / REGISTRY_PATH
    if not path.is_file():
        errors.append(SurfaceError(
            codes.REGISTRY_MISSING, REGISTRY_PATH,
            "the operation registry is not there. Every hand-written call "
            "names an operation in it, so without it there is nothing for a "
            "call to resolve against. Run "
            "`python -m tools.sdk_operations --write`."))
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as broken:
        errors.append(SurfaceError(codes.REGISTRY_UNREADABLE, REGISTRY_PATH,
                                   f"the registry does not parse: {broken}"))
        return {}

    entries = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        entry = _entry(target.id, node.value, errors)
        if entry is not None:
            entries[entry.name] = entry

    if not entries:
        errors.append(SurfaceError(
            codes.REGISTRY_UNREADABLE, REGISTRY_PATH,
            "the registry declares no operations. Every call in the hand shell "
            "would fail to resolve at once, which describes a broken read "
            "rather than an SDK that reaches nothing."))
    return entries


def _entry(name, value, errors):
    """One :class:`Entry` from `NAME = Operation(...)`, or ``None`` with a reason."""
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id == CONSTRUCTOR):
        errors.append(SurfaceError(
            codes.REGISTRY_UNREADABLE, f"{REGISTRY_PATH}: {name}",
            f"`{name}` is assigned something other than a "
            f"`{CONSTRUCTOR}(...)`. Every name in this file is an operation a "
            f"wrapper may reach; one that is not would be a name the gate "
            f"cannot resolve and the SDK can still import."))
        return None

    arguments = [_constant(argument) for argument in value.args]
    if len(arguments) != 3 or any(
            argument is _UNREADABLE for argument in arguments):
        errors.append(SurfaceError(
            codes.REGISTRY_UNREADABLE, f"{REGISTRY_PATH}: {name}",
            f"`{name}` is not `{CONSTRUCTOR}(operation_id, method, path)` with "
            f"three literals. The registry is generated; an entry that "
            f"computes any part of itself is a hand edit."))
        return None

    operation_id, method, path = arguments
    return Entry(name, operation_id, method, path)


_UNREADABLE = object()


def _constant(node):
    if isinstance(node, ast.Constant) and (node.value is None
                                           or isinstance(node.value, str)):
        return node.value
    return _UNREADABLE


# ---------------------------------------------------------------------------
# The zero-diff gate
# ---------------------------------------------------------------------------

def compare(entries, repo_root):
    """``(fault or None, rendered bytes)`` for the committed registry.

    Byte for byte, and for the reason `manifest.py` gives: decoding would fold
    CRLF into LF and call a Windows working copy current, so this tool would
    report "up to date" about a file git reports as modified.
    """
    rendered = render(entries).encode("utf-8")
    path = Path(repo_root) / REGISTRY_PATH
    if not path.is_file():
        return SurfaceError(
            codes.REGISTRY_MISSING, REGISTRY_PATH,
            "the operation registry is not committed. Run "
            "`python -m tools.sdk_operations --write`."), rendered
    if path.read_bytes() != rendered:
        return SurfaceError(
            codes.REGISTRY_DIFFERS, REGISTRY_PATH,
            "the committed registry is not what the contract and the ledger "
            "produce. An operation added, renamed or removed since it was last "
            "generated will show here — and so will a hand edit, which is what "
            "the banner forbids: run "
            "`python -m tools.sdk_operations --write` and commit the result."
        ), rendered
    return None, rendered


def write(entries, repo_root):
    """Regenerate the registry if it is stale; return whether it was rewritten."""
    stale, rendered = compare(entries, repo_root)
    if stale is None:
        return False
    path = Path(repo_root) / REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered)
    return True
