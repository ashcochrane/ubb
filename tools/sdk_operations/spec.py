"""The published operations, read from the committed contract.

``openapi/v1.json`` is the oracle (ADR-002): the single source of truth for the
tenant surface, regenerated offline and gated for drift. This module turns it
into the set of operations the SDK is measured against, keyed the way ADR-0007
§4 requires — **the complete operation identity, method AND path**, because
`GET /x/{id}` is not `POST /x/{id}` and a check that cannot tell them apart is
not a check.

The one transformation worth explaining is :func:`template`. A spec path names
its parameters (`/customers/{customer_id}/balance`); a hand-written f-string
names its *variables*, which are the same positions under different words
(`f"/customers/{external}/balance"`). Comparing the two literally would report
every parameterised route as unmatched, so both sides collapse to the same
shape: `{}` for a parameter, everything else verbatim.

That collapse is only safe if it is injective over the spec, and OpenAPI says it
is — two paths differing solely in parameter *name* are the same path and are
forbidden. :func:`load_operations` proves it rather than trusting it, because
a collision would silently let one operation stand in for another.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from tools.sdk_operations import errors as codes
from tools.sdk_operations.errors import SurfaceError

#: Where the contract lives, relative to the git root.
SPEC_PATH = "openapi/v1.json"

#: The keys of a path item that are operations. OpenAPI puts other things there
#: too — `parameters`, `summary`, `$ref` — and treating one as an operation
#: would invent a route nobody published.
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options",
                "trace")


@dataclass(frozen=True)
class Operation:
    """One published operation: what it is called, and how it is reached."""

    operation_id: str
    method: str
    path: str

    @property
    def template(self):
        """The path with its parameter names collapsed — what a call matches on."""
        return template(self.path)

    @property
    def identity(self):
        """``(METHOD, template)`` — the key ADR-0007 §4 requires."""
        return self.method, self.template

    def __str__(self):
        return f"{self.method} {self.path}"


def template(path):
    """``/customers/{customer_id}/balance`` -> ``/customers/{}/balance``.

    Brace depth is tracked rather than a regular expression matching `{...}`,
    so a parameter whose name itself contains braces cannot end the placeholder
    early and split one position into two.
    """
    out, depth = [], 0
    for character in path:
        if character == "{":
            depth += 1
            if depth == 1:
                out.append("{}")
            continue
        if character == "}":
            if depth:
                depth -= 1
            continue
        if depth == 0:
            out.append(character)
    return "".join(out)


def load_operations(repo_root):
    """``({(METHOD, template): Operation}, errors)`` for the committed contract.

    Never raises: it collects. One entry point —
    :func:`tools.sdk_operations.load_coverage` — decides whether a non-empty
    error list becomes a failure, so a caller that wants the whole story in one
    run can have it.
    """
    errors = []
    operations = _read(Path(repo_root) / SPEC_PATH, errors)
    return operations, errors


def _read(spec_path, errors):
    if not spec_path.is_file():
        errors.append(SurfaceError(
            codes.SPEC_MISSING, SPEC_PATH,
            "the committed contract is not there. It is this gate's oracle; "
            "without it there is nothing to check a call against, and passing "
            "would mean asserting nothing."))
        return {}

    try:
        document = json.loads(spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as broken:
        errors.append(SurfaceError(codes.SPEC_UNREADABLE, SPEC_PATH,
                                   f"the contract does not parse: {broken}"))
        return {}

    paths = document.get("paths") if isinstance(document, dict) else None
    if not isinstance(paths, dict):
        errors.append(SurfaceError(
            codes.SPEC_UNREADABLE, SPEC_PATH,
            "the contract declares no `paths` mapping — this is not an OpenAPI "
            "document, and reading zero operations out of it would make every "
            "call in the SDK unmatched at once."))
        return {}

    operations, seen_ids = {}, {}
    for path, item in sorted(paths.items()):
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            body = item.get(method)
            if not isinstance(body, dict):
                continue
            where = f"{SPEC_PATH}: {method.upper()} {path}"
            operation_id = body.get("operationId")
            if not isinstance(operation_id, str) or not operation_id.strip():
                errors.append(SurfaceError(
                    codes.OPERATION_ID_MISSING, where,
                    "the operation carries no `operationId`. ADR-0007 §4 "
                    "prefers the identifier over the path pair, and a coverage "
                    "manifest cannot name a row that has no name."))
                continue
            if operation_id in seen_ids:
                errors.append(SurfaceError(
                    codes.DUPLICATE_OPERATION_ID, where,
                    f"`{operation_id}` already names {seen_ids[operation_id]}. "
                    f"Two operations under one identifier make the manifest's "
                    f"rows ambiguous about which one they classify."))
                continue
            seen_ids[operation_id] = f"{method.upper()} {path}"

            operation = Operation(operation_id, method.upper(), path)
            if operation.identity in operations:
                other = operations[operation.identity]
                errors.append(SurfaceError(
                    codes.TEMPLATE_COLLISION, where,
                    f"collapses onto `{other}`. Two paths differing only in "
                    f"parameter name are one path, and this gate matches on "
                    f"the collapsed shape — leaving both would let a call to "
                    f"either resolve against the other."))
                continue
            operations[operation.identity] = operation

    if not operations and not errors:
        errors.append(SurfaceError(
            codes.SPEC_EMPTY, SPEC_PATH,
            "the contract publishes no operations. Every SDK call would be "
            "unmatched and every manifest row absent, so this is a broken read "
            "rather than an empty surface."))
    return operations
