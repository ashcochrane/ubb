"""Synthetic SDKs and contracts, for putting the gate through its real entry point.

Every control here builds a whole small repository on disk — a contract, a hand
shell, a generated client, and where it matters a migration ledger — and reads
it with :func:`tools.sdk_operations.assess`, the same function CI and the CLI
call. Nothing patches the walker, the resolver or the renderer.

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
"""

import json

#: The prefix every synthetic route shares with the real ones, so a control
#: exercises the same `ROUTE_MARKER` rule the shipped contract does.
ROOT = "/api/v1"

#: A published operation, as the helpers pass them around.
THING_LIST = ("get", f"{ROOT}/things", "things_list")
THING_READ = ("get", f"{ROOT}/things/{{thing_id}}", "things_read")
THING_WRITE = ("post", f"{ROOT}/things/{{thing_id}}", "things_write")

DEFAULT_OPERATIONS = (THING_LIST, THING_READ)


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


def client_module(*requests, class_name="ThingsClient", extra=""):
    """A hand-written client whose methods make exactly ``requests``.

    Each request is ``(http method, path expression)``, where the path
    expression is Python source — ``'"/api/v1/things"'`` for a literal,
    ``'f"/api/v1/things/{thing_id}"'`` for an interpolated one. Passing source
    rather than a string is what lets a control express the cases that are
    *about* how the path was written: an f-string, a variable, a concatenation.
    """
    lines = [
        '"""A synthetic hand-written client."""',
        "",
        "",
        f"class {class_name}:",
        "    def _request(self, method, path, **kwargs):",
        "        raise NotImplementedError",
        "",
    ]
    for index, (method, expression) in enumerate(requests):
        lines += [
            f"    def call_{index}(self, thing_id='', other_id=''):",
            f'        """Calls {method.upper()} something."""',
            f'        return self._request("{method}", {expression})',
            "",
        ]
    return "\n".join(lines) + extra


def literal(path):
    """A path expression for a plain string literal."""
    return json.dumps(path)


def interpolated(path, name="thing_id"):
    """A path expression for an f-string, with ``{}`` filled by ``name``."""
    return 'f"' + path.replace("{}", "{" + name + "}") + '"'


def write_repository(tmp_path, *, operations=DEFAULT_OPERATIONS, modules=None,
                     generated=None, ledger=None, manifest=None):
    """Write a whole synthetic repository under ``tmp_path``; return the root.

    ``generated`` is which operation ids the generated client has a module for;
    it defaults to all of them, which is what the real tree looks like. Passing
    a subset is how a control reaches `not_yet_wrapped`.

    ``manifest`` writes a committed coverage manifest verbatim — the only way
    to express "the committed manifest disagrees with the tree", which is what
    the zero-diff gate exists to catch.
    """
    (tmp_path / "openapi").mkdir(parents=True, exist_ok=True)
    (tmp_path / "openapi" / "v1.json").write_text(
        json.dumps(spec(operations), indent=2), encoding="utf-8")

    shell = tmp_path / "ubb-sdk" / "ubb"
    shell.mkdir(parents=True, exist_ok=True)
    for name, source in (modules or {}).items():
        (shell / name).write_text(source, encoding="utf-8")

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
            ledger if isinstance(ledger, str) else _yaml(ledger),
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


def _yaml(document):
    """A tiny dumper, so the helpers do not depend on emitter settings.

    Only the two shapes ``excusing`` produces — a mapping of scalars and a list
    of flat mappings — because a general dumper here would be a second
    implementation of PyYAML nobody asked for.
    """
    lines = []
    for key, value in document.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                first = True
                for name, field in item.items():
                    prefix = "  - " if first else "    "
                    lines.append(f"{prefix}{name}: {json.dumps(field)}")
                    first = False
        else:
            lines.append(f"{key}: {json.dumps(value)}")
    return "\n".join(lines) + "\n"
