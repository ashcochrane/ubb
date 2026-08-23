"""Synthetic SDKs and contracts, for putting the gate through its real entry point.

Every control here builds a whole small repository on disk — a contract, an
operation registry, a hand shell, a generated client, and where it matters a
migration ledger — and reads it with :func:`tools.sdk_operations.assess`, the
same function CI and the CLI call. Nothing patches the walker, the resolver or
the renderer.

That is not a style preference in this file above all others. The defect this
gate exists to catch survived for months *because its tests patched the HTTP
client*: the mock faithfully reproduced the mistake instead of contradicting
it, and three methods calling routes that existed nowhere stayed green. A
control that mocked the resolver would be the same test, one level up.

The synthetic repositories are small — two or three operations — because the
rules under test are about identity and evidence, not about scale. What checks
the gate against the *real* 134 operations and 81 calls is
``test_sdk_operations.py``'s shipped-tree section, which asserts on the tree
itself rather than on a copy of it.

## The registry, and why it is written by default

Since #209 a wrapper names an operation rather than spelling a path, so a
synthetic repository without a registry is one where nothing can resolve. It is
therefore generated here from the same ``operations`` the contract is built
from — which is what makes ``registry=`` interesting when a control passes it:
that is the only way to express "the committed registry disagrees with the
contract", and three of the gate's rules exist for exactly that case.
"""

import json
from pathlib import Path

import yaml

from tools.sdk_operations import registry as registry_module
from tools.sdk_operations.calls import REGISTRY_MODULE, SHELL_ROOT

#: The prefix every synthetic route shares with the real ones, so a control
#: exercises the same `ROUTE_MARKER` rule the shipped contract does.
ROOT = "/api/v1"

#: A published operation, as the helpers pass them around.
THING_LIST = ("get", f"{ROOT}/things", "things_list")
THING_READ = ("get", f"{ROOT}/things/{{thing_id}}", "things_read")
THING_WRITE = ("post", f"{ROOT}/things/{{thing_id}}", "things_write")

DEFAULT_OPERATIONS = (THING_LIST, THING_READ)

#: How a hand-written module reaches the registry. Taken from the tool rather
#: than spelled here, so a control's synthetic module writes the same import
#: the real modules do and the gate's own advice names.
REGISTRY_IMPORT = registry_module.REGISTRY_IMPORT_LINE


def spec(operations=DEFAULT_OPERATIONS):
    """A minimal OpenAPI document publishing exactly ``operations``."""
    paths = {}
    for method, path, operation_id in operations:
        paths.setdefault(path, {})[method] = {
            "operationId": operation_id,
            "summary": f"{method.upper()} {path}",
            "responses": {"200": {"description": "OK"}},
        }
    return {"openapi": "3.1.0", "info": {"title": "synthetic", "version": "1"},
            "paths": paths}


def constant(operation_id):
    """The registry name a published operation is reached by."""
    return registry_module.constant_name(operation_id)


def call(operation_id, *arguments):
    """The source of a request's single argument: an operation reference.

    ``call("things_list")`` unpacks a route that takes nothing;
    ``call("things_read", "thing_id")`` fills one that takes a value. The
    arguments are Python source, so a control can pass an expression as easily
    as a name.
    """
    reference = f"*ops.{constant(operation_id)}"
    return f"{reference}({', '.join(arguments)})" if arguments else reference


def registry_source(operations=DEFAULT_OPERATIONS, ledger=None):
    """The registry these operations and this ledger render.

    Built from the same renderer the tool uses, so a synthetic repository is
    byte-identical to what ``--write`` would produce in it — which is what lets
    a control write one deliberately wrong and mean it.
    """
    entries = {}
    for method, path, operation_id in operations:
        name = constant(operation_id)
        entries[name] = registry_module.Entry(name, operation_id, method, path)
    for entry in (ledger or {}).get("entries", ()):
        if not isinstance(entry, dict) or entry.get("gate") != "G17":
            continue
        found = entry["found"]
        method, path = registry_module.parse_found(found)
        name = registry_module.unpublished_name(found)
        entries[name] = registry_module.Entry(name, None, method, path)
    return registry_module.render(entries)


def client_module(*targets, class_name="ThingsClient", extra="",
                  imports=True):
    """A hand-written client whose methods make exactly ``targets``.

    Each target is the source of the request's argument — normally
    :func:`call`'s output, but any Python source, which is what lets a control
    express the cases that are *about* how a call names its target: a literal,
    a variable, a keyword, an operation filled with the wrong number of values.

    ``imports=False`` omits the registry import, for the one control about a
    module that makes requests without reaching a registry at all.
    """
    lines = ['"""A synthetic hand-written client."""', ""]
    if imports:
        lines.append(REGISTRY_IMPORT)
    lines += ["", f"class {class_name}:",
              "    def _request(self, method, path, **kwargs):",
              "        raise NotImplementedError", ""]
    for index, target in enumerate(targets):
        lines += [
            f"    def call_{index}(self, thing_id='', other_id=''):",
            '        """Calls something."""',
            f"        return self._request({target})",
            "",
        ]
    return "\n".join(lines) + extra


def literal(path):
    """A path expression for a plain string literal — now always a violation."""
    return json.dumps(path)


def interpolated(path, name="thing_id"):
    """An f-string path expression, with ``{}`` filled by ``name``.

    Kept because the rule that refuses one is worth a control of its own: this
    is the shape 39 of the real call sites had before #209, so the gate has to
    keep refusing it or the refactor could quietly come undone.
    """
    return 'f"' + path.replace("{}", "{" + name + "}") + '"'


def write_repository(tmp_path, *, operations=DEFAULT_OPERATIONS, modules=None,
                     generated=None, ledger=None, manifest=None, registry=None):
    """Write a whole synthetic repository under ``tmp_path``; return the root.

    ``generated`` is which operation ids the generated client has a module for;
    it defaults to all of them, which is what the real tree looks like. Passing
    a subset is how a control reaches `not_yet_wrapped`.

    ``manifest`` and ``registry`` write those artifacts verbatim — the only way
    to express "the committed copy disagrees with the tree", which is what the
    two zero-diff gates exist to catch.
    """
    (tmp_path / "openapi").mkdir(parents=True, exist_ok=True)
    (tmp_path / "openapi" / "v1.json").write_text(
        json.dumps(spec(operations), indent=2), encoding="utf-8")

    shell = tmp_path / "ubb-sdk" / "ubb"
    shell.mkdir(parents=True, exist_ok=True)
    for name, source in (modules or {}).items():
        (shell / name).write_text(source, encoding="utf-8")

    (shell / "_operations.py").write_text(
        registry if registry is not None
        else registry_source(operations, ledger), encoding="utf-8")

    api = shell / "_core" / "api" / "default"
    api.mkdir(parents=True, exist_ok=True)
    identifiers = ([operation_id for _, _, operation_id in operations]
                   if generated is None else list(generated))
    for operation_id in identifiers:
        (api / f"{operation_id}.py").write_text(
            "# a synthetic generated operation module\n", encoding="utf-8")

    if ledger is not None:
        (tmp_path / "gates").mkdir(parents=True, exist_ok=True)
        (tmp_path / "gates" / "migration-ledger.yaml").write_text(
            ledger if isinstance(ledger, str)
            else yaml.safe_dump(ledger, sort_keys=False),
            encoding="utf-8")

    if manifest is not None:
        (tmp_path / "ubb-sdk" / "operation-coverage.yaml").write_text(
            manifest, encoding="utf-8")

    return tmp_path


def excusing(*entries):
    """A migration ledger excusing exactly ``(site, found)`` pairs under G17."""
    return {
        "version": 1,
        "entries": [
            {"id": f"g17-synthetic-{index}", "gate": "G17", "site": site,
             "expected": "no call", "found": found, "owner_slice": "slice_4",
             "reason": "a synthetic debt."}
            for index, (site, found) in enumerate(entries)
        ],
    }


#: One synthetic debt, spelled once. `docs/conventions/testing.md` puts shared
#: setup in a helper module, and this shape had reached three copies across
#: `test_sdk_operations.py` before #373 extracted it: a site, a route nothing
#: publishes, and the constant name the ledger renders for it.
#:
#: It matters more than ordinary setup duplication. The G17 family is EMPTY on
#: the shipped tree, so every control that still has content about an excused
#: call is a synthetic one — this is the only place a debt exists at all, and
#: three hand-copies of it could drift into three different debts while each
#: read as "the" case.
A_DEBT_SITE = f"{SHELL_ROOT}/things.py::ThingsClient.call_0"
A_DEBT_ROUTE = f"{ROOT}/gone"
A_DEBT_FOUND = f"GET {A_DEBT_ROUTE}"


def a_debt_constant():
    """The constant name the registry renders for :data:`A_DEBT_FOUND`.

    Derived through the real `unpublished_name` rather than written out, so a
    control cannot disagree with the renderer about what the call site should
    say — which is the same reason the production registry derives it from the
    ledger's `found` instead of from the entry's id.
    """
    return registry_module.unpublished_name(A_DEBT_FOUND)


def a_repository_with_one_debt(tmp_path, *, extra="", operations=None):
    """A synthetic repository whose shell makes one call nothing publishes.

    Returns the ``(site, found)`` pair the gate must report as excused, so a
    caller asserts against what this built rather than against a literal it
    repeated. ``extra`` appends source to the module, which is how the
    docstring arm adds prose naming the same dead route.
    """
    write_repository(
        tmp_path,
        operations=(THING_LIST,) if operations is None else operations,
        ledger=excusing((A_DEBT_SITE, A_DEBT_FOUND)),
        modules={"things.py": client_module(f"*ops.{a_debt_constant()}",
                                            extra=extra)})
    return A_DEBT_SITE, A_DEBT_FOUND


def modules_spelling_the_unpublished_prefix(repo_root):
    """HAND-WRITTEN shell modules whose source spells ``UNPUBLISHED_``.

    The one part of "no call reaches an unpublished route" that is a property
    of the text rather than of the join: a constant that failed to resolve is
    already a fault code, but the graceless prefix appearing in a docstring or
    a comment is not, and it is how the vocabulary comes back before it reaches
    a call. Shared so the shipped-tree assertion and the control that makes it
    fail run the SAME read — a control with its own copy of the search would
    prove only that two copies agree.

    ⚠ **THE GENERATED REGISTRY IS EXCLUDED, AND LEAVING IT IN WAS A REAL BUG
    THAT ONLY AN EMPTY LEDGER HID.** `ubb/_operations.py` is where an
    `UNPUBLISHED_` constant is SUPPOSED to be spelled — it is generated from
    the ledger and is the only file allowed to name a route at all. With G17
    empty the file spells nothing, so a reader that included it passed anyway;
    the day a seeding authorisation legitimately re-added a debt, the shipped
    assertion would have gone red blaming the generated file for doing its job.
    The control that drives this function against a repository WITH a debt is
    what found that, which is the whole reason the control exists.

    Excluded by `REGISTRY_MODULE`, the same constant `load_call_sites` skips
    when it walks the shell, so the two cannot disagree about which file is
    generated.
    """
    prefix = registry_module.UNPUBLISHED_PREFIX
    root = Path(repo_root) / SHELL_ROOT
    return sorted(path.relative_to(repo_root).as_posix()
                  for path in root.glob("*.py")
                  if path.name != REGISTRY_MODULE
                  and prefix in path.read_text(encoding="utf-8"))
