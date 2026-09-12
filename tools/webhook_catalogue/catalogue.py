"""Read the live webhook catalogue, without importing it.

The catalogue is the set of payload dataclasses in the platform's
``events/schemas.py``: each frozen class IS the contract for one deliverable
event, and ``events/catalog.py`` derives its tuple from them, so the classes are
where the names actually live.

This module reads that file with :mod:`ast` and never imports it. Two reasons,
and only one of them is convenience:

- the contract suite has no Django, no settings and no database, deliberately
  (``tests/contracts/test_contract_suite_is_enforced.py`` makes that a checked
  rule rather than a habit), and the module's package pulls in all three;
- source cannot be mocked. #204's forward gate is written the same way for the
  same reason: the three dead SDK calls were green for months *because* their
  tests patched the transport, so the mock reproduced the mistake.
"""

import ast
from dataclasses import dataclass

from . import errors as E
from .errors import CatalogueError

#: The class attribute each payload dataclass sets to its event name.
EVENT_TYPE_ATTRIBUTE = "EVENT_TYPE"


@dataclass(frozen=True, order=True)
class Event:
    """One event the platform publishes, as the catalogue declares it."""
    #: The event name — `<owner>.<transition>` when it obeys ADR-0006 §5.
    name: str
    #: The declaring payload class, which is this event's identity in the
    #: migration ledger: `<path>::<ClassName>`.
    declaring_class: str

    def site(self, path):
        return f"{path}::{self.declaring_class}"


def read_catalogue(repo_root, path, *, module=None, constants=None):
    """Every event declared in ``path``, and every reason it could not be read.

    Returns ``(events, errors)``. A file that is missing, unparseable or empty
    yields no events and one error saying which — never an empty catalogue that
    silently satisfies every rule stated over it.

    An ``EVENT_TYPE`` is read two ways and no other. A non-empty string literal
    is the name itself. A bare name is resolved only when the file imports it
    from ``module`` — the generated vocabulary — and ``constants`` (generated
    name → declared value, the registry's own rendering) knows it; since #464
    every live payload class takes its name that way. A name imported from
    the module that the registry renders nothing under is refused by its own
    code rather than skipped, because a class holding a name by reference can
    only ever hold a declared value, and a reader that let one through would
    let the by-reference payment publish anything at all. Everything else — a
    computed expression, a name from any other module, a name from nowhere —
    is a name this gate cannot read, and says so.
    """
    constants = constants or {}
    source_file = repo_root / path
    try:
        # `utf-8-sig` tolerates a byte-order mark, which Python's own tokenizer
        # strips and a walker decoding the bytes itself would otherwise choke on.
        tree = ast.parse(source_file.read_text(encoding="utf-8-sig"),
                         filename=str(source_file))
    except (OSError, SyntaxError, UnicodeDecodeError) as problem:
        # There is deliberately no separate "the file is missing" code. The
        # registry already refuses a declared consumer whose path is not in the
        # repository, so a deleted catalogue is reported as a broken ORACLE
        # before this function is reached — and a second copy of that rule here
        # would be a branch nothing could ever take, which is the same shape as
        # a check that cannot fail.
        return (), [CatalogueError(
            E.CATALOGUE_UNREADABLE, path, f"it could not be read: {problem}")]

    # Local name → generated name, for every `from <module> import X [as Y]`
    # at any depth. Only the generated module's names are bound: a constant
    # spelled right but imported from anywhere else stays unreadable.
    imported = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.ImportFrom) and module is not None
                and node.level == 0 and node.module == module):
            for alias in node.names:
                imported[alias.asname or alias.name] = alias.name

    events = []
    errors = []
    seen = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name)
                       and target.id == EVENT_TYPE_ATTRIBUTE
                       for target in statement.targets):
                continue
            location = f"{path}::{node.name}"
            value = statement.value
            if (isinstance(value, ast.Constant)
                    and isinstance(value.value, str) and value.value):
                name = value.value
            elif isinstance(value, ast.Name) and value.id in imported:
                generated = imported[value.id]
                if generated not in constants:
                    errors.append(CatalogueError(
                        E.EVENT_TYPE_NOT_A_DECLARED_CONSTANT, location,
                        f"{EVENT_TYPE_ATTRIBUTE} is `{generated}` from "
                        f"{module}, and the registry renders no declared "
                        f"webhook_event_type value under that name — a name "
                        f"held by reference can only be a declared value"))
                    continue
                name = constants[generated]
            else:
                errors.append(CatalogueError(
                    E.EVENT_TYPE_NOT_LITERAL, location,
                    f"{EVENT_TYPE_ATTRIBUTE} is neither a non-empty string "
                    f"literal nor a name imported from {module}, so this gate "
                    f"cannot read the name it publishes"))
                continue
            if name in seen:
                errors.append(CatalogueError(
                    E.DUPLICATE_EVENT_TYPE, location,
                    f"`{name}` is already declared by {seen[name]} — one event "
                    f"name, one payload contract"))
                continue
            seen[name] = node.name
            events.append(Event(name=name, declaring_class=node.name))

    if not events and not errors:
        errors.append(CatalogueError(
            E.CATALOGUE_EMPTY, path,
            f"it parsed and declares no {EVENT_TYPE_ATTRIBUTE} at all — a gate "
            f"over an empty catalogue passes every rule stated over it"))

    return tuple(sorted(events)), errors
