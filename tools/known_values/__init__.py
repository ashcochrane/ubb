"""The published contract's known-value metadata (#208, ADR-0008 §2).

The committed spec starts telling API consumers which values UBB knows about —
**without closing a single open enum**. ADR-0003's open-enum stance is not
reversed here and is not weakened: an `open` concept keeps `type: string` and
exposes its recognised values as documentation metadata under a vendor
extension, never as an `enum` array. Forcing the spec into being the vocabulary
oracle would turn every new status into a breaking-gate event, which is exactly
what that stance exists to prevent.

Two halves, and the split is what lets the platform take part at all:

    document.py   the DECISION, taken in the Django-free tool where the
                  consumer census can be consulted, and committed as
                  `openapi/known-values.json` — a generated artifact riding the
                  same zero-diff ratchet as every other one.
    apply.py      the APPLICATION, a pure transformation over an OpenAPI
                  document that the spec export calls. No YAML, no registry
                  compiler, no Django, so it runs on both sides of the fence.

    from tools.known_values import apply_known_values, read_decisions
    schema = apply_known_values(schema, read_decisions(path))

**The rule that keeps this honest**, and the reason a decision document exists
rather than a direct read of the registry: *the spec advertises a value only
where the backend already serves it*. Emitting the final customer-billing
values on a field that today returns the retired one would put a falsehood into
the published contract — worse than saying nothing, because a consumer can act
on it. Every concept that is not yet served is a migration-ledger entry owned
by the slice that renames it, and the metadata appears in that slice.
"""

import json
from pathlib import Path

from .apply import (
    EXTENSIONS,
    KNOWN_VALUES_KEY,
    MARKER,
    apply_known_values,
    marked_nodes,
    strip_known_values,
)
from .document import (
    BACKEND,
    CONTRACT,
    ENUM,
    KNOWN_VALUES,
    NOTHING,
    VALUES_KEY,
    Decision,
    build,
    decide,
    read,
)
from .errors import KnownValuesRefused


def read_decisions(path):
    """``{concept: Decision}`` from the committed document at ``path``.

    The one loader, so the spec export, the gate and any later reader parse the
    same bytes the same way. A document that is not the shape this applier
    reads raises rather than degrading to "nothing is advertised" — which would
    strip the contract's metadata silently, and silently is how a gate stops
    being one.
    """
    return read(json.loads(Path(path).read_text(encoding="utf-8")))


__all__ = [
    "BACKEND",
    "CONTRACT",
    "ENUM",
    "EXTENSIONS",
    "KNOWN_VALUES",
    "KNOWN_VALUES_KEY",
    "MARKER",
    "NOTHING",
    "VALUES_KEY",
    "Decision",
    "KnownValuesRefused",
    "apply_known_values",
    "build",
    "decide",
    "marked_nodes",
    "read",
    "read_decisions",
    "strip_known_values",
]
