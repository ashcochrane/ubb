"""Every request the hand-written SDK makes, read out of its source.

Statically, with :mod:`ast`, and never by importing the SDK or running it. That
is not a convenience — it is the whole reason this gate can exist in the
contract suite, which installs two packages and has no `httpx` and no Django.
It is also the correction to the failure this gate was written for: three
methods called routes that existed in no spec and no router and stayed green
for months, *because their tests patched the HTTP client* and the mock
faithfully reproduced the mistake. Source cannot be mocked.

## What counts as the hand-written surface

``ubb-sdk/ubb/*.py`` — the modules directly under the package, and nothing
below them. The one sub-package, ``_core/``, is the generated client: it rides
G16's regeneration gate, its 134 operation modules each spell a route by
construction, and re-checking them here would compare the generator against
itself.

That rule is stated as *"top level only"* rather than as a list of exclusions,
so it cannot rot. A NEW sub-package appearing under ``ubb/`` — hand-written
ergonomics moved into a folder, say — is neither walked nor generated, so it is
refused by name (:data:`~tools.sdk_operations.errors.UNSCANNED_PACKAGE`) rather
than silently escaping the gate. An exclusion nobody can see is how the sweep
that shipped `continue-on-error` looked from the board.

One module at that top level is not walked as hand-written source:
``_operations.py``, the generated registry. It is read instead by
:mod:`tools.sdk_operations.registry`, against the contract that generates it.
It is the one file allowed to spell a path, which is what makes the rule below
sayable at all.

## What counts as a call, after #209

A request through the shell's transport helper — ``_request`` or
``_request_once`` — whose target is a **constant in the registry**:

    self._request(*ops.API_V1_TENANT_ENDPOINTS_GET_TENANT_CONFIG)
    self._request(*ops.API_V1_PLAN_ENDPOINTS_UPDATE_PLAN(key), json=body)

Both shapes resolve the same way: the constant supplies the method and the
path, and this module never reads either from the call. That inverts what the
gate does. Before #209 a call spelled its own route and the gate checked the
spelling against the contract; now a call *names* an operation and there is no
spelling left to get wrong — what remains checkable is whether the name exists
(:data:`~tools.sdk_operations.errors.NO_SUCH_OPERATION_CONSTANT`, which is what
a rename leaves behind) and whether it is filled with the right number of
values (:data:`~tools.sdk_operations.errors.PARAMETER_COUNT_WRONG`, which an
f-string could not have caught at all — it interpolated whatever it was given
and produced a plausible, wrong path).

Two conjuncts keep that honest, and without them the rule would be advice:

1. **A request naming its target any other way is refused.** A literal, a
   variable, an f-string, a path assembled from fragments — all
   :data:`~tools.sdk_operations.errors.CALL_NOT_AN_OPERATION`. There is no
   longer a legal way to write a path at a call site, so there is no longer a
   way to write a wrong one.
2. **Every route literal in the hand shell is refused outright.** Otherwise
   ``self._http.get("/api/v1/...")`` is a shape this module would not recognise
   and would therefore report as clean. The walker cannot be walked around
   without the diff saying so.

## Prose, which is the one place a path may still be written

A bare string expression statement is a docstring, and the SDK's docstrings
name the routes their methods call — deliberately, as public documentation. A
docstring is the only string in a Python module that is evaluated and
discarded, which is what makes that rule mechanical rather than a judgement.

But #209's claim is that a route rename cannot leave a stale string behind, and
a docstring is a string. So they are not merely exempted: every route named in
one is collected here and checked against the contract by
:mod:`tools.sdk_operations.coverage`. Documentation is allowed to name a route;
it is not allowed to name one that does not exist.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from tools.sdk_operations import errors as codes
from tools.sdk_operations.errors import SurfaceError
from tools.sdk_operations.registry import REGISTRY_PATH

#: The package holding the hand-written ergonomic surface.
SHELL_ROOT = "ubb-sdk/ubb"

#: The generated client, gated by G16 and deliberately not walked here.
GENERATED_PACKAGE = "_core"

#: The generated registry, read by `registry.py` rather than walked as source.
#: Derived from its path so the two cannot name different files.
REGISTRY_MODULE = REGISTRY_PATH.rsplit("/", 1)[-1]

#: The module the registry's constants live in, as an import names it.
REGISTRY_IMPORT = REGISTRY_PATH[len("ubb-sdk/"):-len(".py")].replace("/", ".")

#: The attribute names that carry a request. Both live in every product client
#: (`_request` retries, `_request_once` does not), and both take the same two
#: leading arguments.
REQUEST_HELPERS = ("_request", "_request_once")

#: The substring that makes a string literal a route rather than prose.
#: Version-specific on purpose, and :func:`tools.sdk_operations.coverage.assess`
#: proves every published path still begins with it — so a contract that moves
#: off this root turns the board red rather than quietly narrowing the sweep.
ROUTE_MARKER = "/api/v1"


@dataclass(frozen=True)
class CallSite:
    """One request the hand shell makes.

    ``constant`` is the registry name the call reached for; everything else is
    read off the registry entry that name resolves to, never off the call. A
    call site therefore cannot disagree with its operation about the method or
    the path — the disagreement #209 removed — and what it can still get wrong
    is which operation it named, and how many values it filled.
    """

    module: str          # `ubb-sdk/ubb/metering.py`
    qualname: str        # `MeteringClient.update_rate_card`
    line: int
    constant: str        # `API_V1_METERING_ENDPOINTS_RECORD_USAGE`
    method: str          # `PUT`
    route: str           # `/api/v1/metering/pricing/rate-cards/{card_id}`
    template: str        # `/api/v1/metering/pricing/rate-cards/{}`

    @property
    def site(self):
        """How the migration ledger and the coverage manifest name this call.

        The declaring method, not the line: a call that moves down its file is
        the same call, and an entry that had to be re-typed on every edit would
        be re-typed carelessly.
        """
        return f"{self.module}::{self.qualname}"

    @property
    def identity(self):
        """``(METHOD, template)`` — what it is matched against."""
        return self.method, self.template

    def __str__(self):
        return f"{self.method} {self.route}"


@dataclass(frozen=True)
class DocumentedRoute:
    """A route named in a docstring, and where to find it."""

    module: str
    line: int
    text: str            # `/api/v1/metering/usage`, as written

    @property
    def location(self):
        return f"{self.module}:{self.line}"


def load_call_sites(repo_root, entries):
    """Every request the hand-written surface makes, and everything wrong with it.

    Returns ``(call sites, documented routes, errors)``. ``entries`` is the
    committed registry as :func:`tools.sdk_operations.registry.load` read it —
    a call resolves through it or does not resolve at all.

    A call this module cannot resolve produces an error and no call site: it is
    not evidence of a working call, and treating it as absent would let an
    unreadable call pass for no call at all.
    """
    errors = []
    root = Path(repo_root) / SHELL_ROOT
    if not root.is_dir():
        errors.append(SurfaceError(
            codes.SHELL_MISSING, SHELL_ROOT,
            "the hand-written SDK package is not there. Reading zero calls out "
            "of a missing directory is what a green board looks like when the "
            "gate has stopped seeing its subject."))
        return (), (), errors

    _check_for_unscanned_packages(root, errors)

    sites, documented = [], []
    modules = sorted(path for path in root.glob("*.py")
                     if path.name != REGISTRY_MODULE)
    for path in modules:
        module = f"{SHELL_ROOT}/{path.name}"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as broken:
            errors.append(SurfaceError(codes.SHELL_UNREADABLE, module,
                                       f"the module does not parse: {broken}"))
            continue
        found, prose = _walk_module(tree, module, entries, errors)
        sites += found
        documented += prose

    if not modules:
        errors.append(SurfaceError(
            codes.SHELL_EMPTY, SHELL_ROOT,
            "the hand-written SDK package holds no modules. There is nothing "
            "to check, which is a broken read rather than a clean surface."))
    return tuple(sites), tuple(documented), errors


def _check_for_unscanned_packages(root, errors):
    """Refuse a sub-package that is neither walked nor generated."""
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in (GENERATED_PACKAGE, "__pycache__"):
            continue
        errors.append(SurfaceError(
            codes.UNSCANNED_PACKAGE, f"{SHELL_ROOT}/{entry.name}",
            f"a sub-package this gate does not walk. Only `{GENERATED_PACKAGE}` "
            f"is exempt, because it is generated and G16 regenerates it. If "
            f"`{entry.name}` is hand-written it must be walked; if it is "
            f"generated it needs its own regeneration gate. Either way the "
            f"decision belongs in a diff, not in this gate's blind spot."))


# ---------------------------------------------------------------------------
# Walking one module
# ---------------------------------------------------------------------------

def _walk_module(tree, module, entries, errors):
    """``(call sites, documented routes)``, reporting every route spelled here.

    The sweep is simpler than it was before #209 and stronger for it. A call
    argument is no longer allowed to BE a route, so there is no set of
    "resolved" literals to subtract: every route literal outside a docstring is
    stray, without exception and without a list.
    """
    aliases = _registry_aliases(tree)
    prose = _docstring_nodes(tree)
    fragments = _joined_string_fragments(tree)

    sites = []
    for node, qualname in _calls(tree):
        site = _call_site(node, module, qualname, aliases, entries, errors)
        if site is not None:
            sites.append(site)

    documented = []
    for node in ast.walk(tree):
        text = _route_text(node)
        if text is None or id(node) in fragments:
            continue
        if id(node) in prose:
            documented += [DocumentedRoute(module, node.lineno, one)
                           for one in _route_tokens(node.value)]
            continue
        errors.append(SurfaceError(
            codes.STRAY_ROUTE_LITERAL, f"{module}:{node.lineno}",
            f"`{text}` is a route spelled in the hand-written layer. Since "
            f"#209 the only file under {SHELL_ROOT}/ that may spell a path is "
            f"the generated registry, `{REGISTRY_PATH}` — a method names an "
            f"operation in it instead. A route reachable any other way is "
            f"exactly the blind spot the three dead rate-card calls lived in."))
    return sites, documented


def _registry_aliases(tree):
    """The names this module reaches the registry by.

    Read from the imports rather than assumed to be `ops`, so the gate resolves
    what the module actually wrote. A module that makes requests without
    importing the registry has no alias, every call in it fails to resolve, and
    the reason it gives names the missing import.
    """
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                full = f"{node.module}.{alias.name}" if node.module else alias.name
                if full == REGISTRY_IMPORT:
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == REGISTRY_IMPORT and alias.asname:
                    aliases.add(alias.asname)
    return aliases


def _docstring_nodes(tree):
    """Every string that is a bare expression statement — a docstring.

    Not ``ast.get_docstring``: that finds only the *first* statement of a
    module, class or function, and a string sitting anywhere else is equally
    evaluated and discarded. The looser rule is the true one, and it is the
    rule a reader can apply by eye.
    """
    return {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}


def _joined_string_fragments(tree):
    """The pieces of an f-string, which its parent already accounts for."""
    return {id(part) for node in ast.walk(tree)
            if isinstance(node, ast.JoinedStr) for part in node.values}


def _calls(tree, qualname=()):
    """Every request call in ``tree``, paired with the method that declares it.

    Recursive rather than :func:`ast.walk` because the qualified name is the
    path taken to reach a node, and a flat walk has thrown that away.
    """
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from _calls(node, qualname + (node.name,))
            continue
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in REQUEST_HELPERS):
            yield node, ".".join(qualname) or "<module>"
        yield from _calls(node, qualname)


def _call_site(node, module, qualname, aliases, entries, errors):
    """One :class:`CallSite`, or ``None`` with the reason it could not be read."""
    where = f"{module}:{node.lineno}"
    described = f"{qualname}()"

    target = _operation_reference(node, aliases)
    if target is None:
        if not node.args and not node.keywords:
            errors.append(SurfaceError(
                codes.CALL_MALFORMED, where,
                f"the request in {described} names no target at all. A call "
                f"this gate cannot read is not a call it can vouch for."))
            return None
        errors.append(SurfaceError(
            codes.CALL_NOT_AN_OPERATION, where,
            f"the request in {described} does not name an operation. Since "
            f"#209 a call spells its target as a constant from "
            f"`{REGISTRY_PATH}` — `*ops.SOME_OPERATION` where the route takes "
            f"no parameters, `*ops.SOME_OPERATION(value)` where it does — and "
            f"a path written any other way is a second copy of the contract "
            f"that nothing keeps current."
            + _missing_import_hint(aliases)))
        return None

    constant, arguments = target
    if entries is None:
        # The registry did not read, and `registry.load` has already said so.
        # Reporting all 81 calls as naming an undeclared constant would bury
        # the one error that explains them, and an author would go looking for
        # eighty-one problems to discover they had one.
        return None

    entry = entries.get(constant)
    if entry is None:
        errors.append(SurfaceError(
            codes.NO_SUCH_OPERATION_CONSTANT, where,
            f"{described} names `{constant}`, which the registry does not "
            f"declare. This is what an operation renamed in the contract "
            f"leaves behind: the constant moved with it and the wrapper did "
            f"not. {_near_names(constant, entries)}"))
        return None

    if arguments is not None and len(arguments) != entry.arity:
        errors.append(SurfaceError(
            codes.PARAMETER_COUNT_WRONG, where,
            f"{described} fills `{constant}` with {len(arguments)} value(s) "
            f"and `{entry.path}` takes {entry.arity}. An f-string interpolated "
            f"whatever it was handed and produced a plausible wrong path; a "
            f"registry entry counts."))
        return None
    if arguments is None and entry.arity:
        errors.append(SurfaceError(
            codes.PARAMETER_COUNT_WRONG, where,
            f"{described} unpacks `{constant}`, whose path `{entry.path}` "
            f"takes {entry.arity} value(s). Unpacked, it would put the "
            f"placeholder on the wire verbatim — call it instead: "
            f"`*ops.{constant}(...)`."))
        return None

    return CallSite(module=module, qualname=qualname, line=node.lineno,
                    constant=constant, method=entry.method.upper(),
                    route=entry.path, template=entry.identity[1])


def _operation_reference(node, aliases):
    """``(constant, arguments or None)`` for ``*ops.NAME`` / ``*ops.NAME(...)``.

    ``None`` for the argument list means the constant was unpacked rather than
    called, which is legal exactly when its path takes no values. Returns
    ``None`` entirely when the call does not name an operation at all.
    """
    if len(node.args) != 1 or not isinstance(node.args[0], ast.Starred):
        return None
    value = node.args[0].value

    if isinstance(value, ast.Call):
        constant = _attribute_name(value.func, aliases)
        return (constant, value.args) if constant else None
    constant = _attribute_name(value, aliases)
    return (constant, None) if constant else None


def _attribute_name(node, aliases):
    """`ops.THING` -> `THING`, when `ops` is how this module reached the registry."""
    if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id in aliases):
        return node.attr
    return None


def _missing_import_hint(aliases):
    if aliases:
        return ""
    return (f" This module imports no registry at all: add "
            f"`from ubb import {REGISTRY_IMPORT.split('.')[-1]} as ops`.")


#: How much of a constant two names must share before one is worth suggesting
#: as the other's replacement. Four characters, because an operation renamed
#: within its own family (`..._LIST` to `..._INDEX`) may share very little, and
#: the search takes the LONGEST prefix that matches anything — so a low floor
#: costs nothing when a long one would have done.
NEAREST_PREFIX = 4


def _near_names(constant, entries):
    """The declared constants closest to the one that was named.

    A bare "no such constant" makes an author diff two long identifiers by eye.
    Naming the ones sharing its longest prefix turns a rename into a sentence,
    which is the commonest reason this fires.
    """
    for length in range(len(constant), NEAREST_PREFIX - 1, -1):
        near = sorted(name for name in entries
                      if name.startswith(constant[:length]) and name != constant)
        if near:
            return ("The registry declares " + ", ".join(f"`{one}`" for one in near[:3])
                    + " — one of those is likely what it was renamed to.")
    return "No declared constant resembles it."


def _route_text(node):
    """The route this node spells, or ``None`` if it does not spell one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if ROUTE_MARKER in node.value else None
    if isinstance(node, ast.JoinedStr):
        text = "".join(part.value for part in node.values
                       if isinstance(part, ast.Constant)
                       and isinstance(part.value, str))
        return text if ROUTE_MARKER in text else None
    return None


#: What ends a route token in prose. A docstring writes a route inside a
#: sentence, so the token runs until whitespace or punctuation that cannot be
#: part of a path — which is every character except these.
_ROUTE_CHARACTERS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-/{}")


def _route_tokens(text):
    """Every route mentioned in a piece of prose, as written.

    A trailing `.` is a full stop rather than a path segment, and a trailing
    `/` is how a docstring names a whole family (`/api/v1/metering/`), which
    :mod:`tools.sdk_operations.coverage` resolves as a prefix. Both are kept
    exactly as written and judged there; this function only finds them.
    """
    tokens, index = [], text.find(ROUTE_MARKER)
    while index != -1:
        end = index
        while end < len(text) and text[end] in _ROUTE_CHARACTERS:
            end += 1
        tokens.append(text[index:end])
        index = text.find(ROUTE_MARKER, end)
    return tokens
