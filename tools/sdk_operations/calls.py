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

## What counts as a call

Two things, and the second is what makes the first honest:

1. **A request through the shell's transport helper** — ``_request`` or
   ``_request_once``, whose first two arguments are the HTTP method and the
   path. This is the shape every one of the 81 calls takes today.
2. **Every route literal, wherever it is spelled.** A gate that reads only
   shape 1 is evaded by writing ``self._http.get("/api/v1/...")`` — a shape
   this module would not recognise and would therefore report as clean. So any
   string mentioning the API root that is *not* one of those resolved call
   arguments is refused outright. The walker cannot be walked around without
   the diff saying so.

Prose is excluded from (2) on one rule: a bare string expression statement is a
docstring, and the SDK's docstrings name the routes their methods call —
deliberately, as public documentation. A docstring is the only string in a
Python module that is evaluated and discarded.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from tools.sdk_operations import errors as codes
from tools.sdk_operations.errors import SurfaceError

#: The package holding the hand-written ergonomic surface.
SHELL_ROOT = "ubb-sdk/ubb"

#: The generated client, gated by G16 and deliberately not walked here.
GENERATED_PACKAGE = "_core"

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

    ``route`` is the path as written, parameter names and all; ``template`` is
    that path with each interpolation collapsed to ``{}``, which is what
    matches a published operation. Both are kept: the template decides, and the
    route is what a reader needs to find the line.
    """

    module: str          # `ubb-sdk/ubb/metering.py`
    qualname: str        # `MeteringClient.update_rate_card`
    line: int
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


def load_call_sites(repo_root):
    """Every request the hand-written surface makes, and everything wrong with it.

    Returns ``(call sites, errors)``. A call this module cannot resolve
    statically produces an error and no call site: it is not evidence of a
    working call, and treating it as absent would let an unreadable call pass
    for no call at all.
    """
    errors = []
    root = Path(repo_root) / SHELL_ROOT
    if not root.is_dir():
        errors.append(SurfaceError(
            codes.SHELL_MISSING, SHELL_ROOT,
            "the hand-written SDK package is not there. Reading zero calls out "
            "of a missing directory is what a green board looks like when the "
            "gate has stopped seeing its subject."))
        return (), errors

    _check_for_unscanned_packages(root, errors)

    sites = []
    modules = sorted(path for path in root.glob("*.py"))
    for path in modules:
        module = f"{SHELL_ROOT}/{path.name}"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as broken:
            errors.append(SurfaceError(codes.SHELL_UNREADABLE, module,
                                       f"the module does not parse: {broken}"))
            continue
        sites += _walk_module(tree, module, errors)

    if not modules:
        errors.append(SurfaceError(
            codes.SHELL_EMPTY, SHELL_ROOT,
            "the hand-written SDK package holds no modules. There is nothing "
            "to check, which is a broken read rather than a clean surface."))
    return tuple(sites), errors


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

def _walk_module(tree, module, errors):
    """The call sites in one module, and the route literals that are not calls."""
    prose = _docstring_nodes(tree)
    fragments = _joined_string_fragments(tree)

    sites, resolved_paths = [], set()
    for node, qualname in _calls(tree):
        site = _call_site(node, module, qualname, errors)
        for argument in _path_arguments(node):
            resolved_paths.add(id(argument))
        if site is not None:
            sites.append(site)

    accounted = prose | fragments | resolved_paths
    for node in ast.walk(tree):
        if id(node) in accounted:
            continue
        text = _route_text(node)
        if text is None:
            continue
        errors.append(SurfaceError(
            codes.STRAY_ROUTE_LITERAL, f"{module}:{node.lineno}",
            f"`{text}` is a route spelled outside any request this gate reads. "
            f"Every call must go through one of {', '.join(REQUEST_HELPERS)} "
            f"so its method and path can be resolved against the contract; a "
            f"route reachable any other way is exactly the blind spot the "
            f"three dead rate-card calls lived in."))
    return sites


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


def _path_arguments(node):
    """The nodes a request call uses as its path — however it was spelled."""
    arguments = []
    if len(node.args) > 1:
        arguments.append(node.args[1])
    arguments += [keyword.value for keyword in node.keywords
                  if keyword.arg == "path"]
    return arguments


def _call_site(node, module, qualname, errors):
    """One :class:`CallSite`, or ``None`` with the reason it could not be read."""
    where = f"{module}:{node.lineno}"
    described = f"{qualname}()"

    method_node = _argument(node, 0, "method")
    path_nodes = _path_arguments(node)
    if not path_nodes:
        errors.append(SurfaceError(
            codes.CALL_MALFORMED, where,
            f"the request in {described} names no path. A call this gate "
            f"cannot read is not a call it can vouch for."))
        return None

    method = _literal_method(method_node)
    route = _literal_route(path_nodes[0])
    if method is None or route is None:
        unreadable = "method" if method is None else "path"
        errors.append(SurfaceError(
            codes.CALL_NOT_LITERAL, where,
            f"the request in {described} computes its {unreadable} rather than "
            f"spelling it. This gate resolves a call by reading its source; a "
            f"computed route cannot be resolved, and passing it would make the "
            f"gate optional for anyone who writes one."))
        return None

    written, collapsed = route
    return CallSite(module=module, qualname=qualname, line=node.lineno,
                    method=method, route=written, template=collapsed)


def _argument(node, position, name):
    """A positional-or-keyword argument, whichever way the caller spelled it."""
    if len(node.args) > position:
        return node.args[position]
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _literal_method(node):
    """`"post"` -> `POST`; anything computed -> ``None``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.upper()
    return None


def _literal_route(node):
    """``(route as written, route with interpolations collapsed)``, or ``None``.

    An f-string is read as a template: its constant pieces are the route, and
    each interpolation is one parameter position. What is interpolated does not
    matter — the shape does, and the shape is what a published path declares.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, node.value
    if isinstance(node, ast.JoinedStr):
        written, collapsed = [], []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                written.append(part.value)
                collapsed.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                written.append("{" + _interpolated_name(part) + "}")
                collapsed.append("{}")
            else:
                return None
        return "".join(written), "".join(collapsed)
    return None


def _interpolated_name(part):
    """What an f-string interpolates, for the human-readable route.

    A bare name is printed as itself; anything else is printed as `…`, because
    the route is for reading and an expression rendered into it would be
    mistaken for a parameter name.
    """
    return part.value.id if isinstance(part.value, ast.Name) else "..."


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
