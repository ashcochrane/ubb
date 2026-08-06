"""Put the registry's known values into the committed contract.

A schema node says which concept it carries by naming it — and only naming it:

    status: str = Field(json_schema_extra={"x-ubb-concept": "task_status"})

The values never appear in the platform's source. They arrive here, from the
generated decision document, at spec-export time. That is what makes this
structural rather than textual: a field cannot agree with the registry by
coincidence, because it does not spell anything the registry could disagree
with.

**What each kind becomes**, and this is the whole of ADR-0003's stance
expressed as code:

    open      `x-ubb-known-values`, beside an untouched `type: string`. Never
              an `enum`, because a value UBB has never seen is legal and a
              schema enumerating the set would make UBB learning a new one a
              breaking change to the published contract.
    closed    a real `enum`. UBB owns the whole value set, so the schema may
              say so.
    otherwise refused — see below.

**Five refusals, and none of them is a fallback.** The generator's rule
applies here: refusal over a plausible-looking lie. A marker that cannot be
honoured stops the export with the JSON pointer of the field that caused it,
rather than being quietly dropped — a silently ignored marker is a check that
cannot fail, which is the failure this repository has already shipped three
times.

The one worth stating in full is `not-advertised`. A slice that marks a field
before converting the concept's backend consumer gets a red export, not a
silent no-op: the debt is already an individually identified migration-ledger
entry, and the field's marker is the thing that pays it. So the order is fixed
— convert the consumer, then mark the field — and the export is what enforces
it.
"""

from . import errors as codes
from .document import ENUM
from .errors import KnownValuesRefused

#: The vendor extension a schema node uses to name its concept. It survives
#: into the published document on purpose: it is the concept-to-schema mapping
#: G4 reads, and a mapping the gate had to infer would be a mapping a
#: coincidence could satisfy.
MARKER = "x-ubb-concept"

#: The vendor extension an `open` concept's recognised values appear under.
#: Documentation metadata, never a constraint — the whole point of it not being
#: `enum`.
KNOWN_VALUES_KEY = "x-ubb-known-values"

#: Every extension this applier owns. The gate asserts the committed document
#: carries no other `x-ubb-` key, so a hand-written vendor extension cannot
#: pass itself off as generated metadata.
EXTENSIONS = (MARKER, KNOWN_VALUES_KEY)

#: Where a marked node may declare its string-ness. A plain `str` field renders
#: `type: "string"`; an optional one renders `anyOf`, and refusing that would
#: refuse a nullable field for no reason anybody could defend.
_UNION_KEYS = ("anyOf", "oneOf")


def apply_known_values(document, decisions):
    """A copy of ``document`` with every marked node given its metadata.

    A copy rather than a mutation, so a caller can compare the two — which is
    how the gate proves the committed contract carries exactly what the
    decisions produce, over :func:`strip_known_values` of it.

    NOT idempotent, deliberately: applying twice hits the `already-enumerated`
    refusal, because a node cannot tell a generated `enum` from a hand-written
    one and the refusal is worth more than the convenience. See
    :func:`strip_known_values`.
    """
    return _walk(document, decisions, "")


def strip_known_values(document):
    """A copy of ``document`` with this applier's output removed from every
    marked node — the metadata, and a `closed` concept's generated `enum`.

    The inverse of :func:`apply_known_values`, and it exists for one caller:
    the gate that proves the committed contract is exactly what the decisions
    produce. Applying to an already-applied document would hit the
    `already-enumerated` refusal, because from inside a node there is nothing
    to distinguish a generated `enum` from a hand-written one — which is the
    same reason that refusal is worth having.

    So the gate strips first and compares afterwards, and the refusal stays
    strict for the caller that matters: the spec export, whose input is a
    freshly rendered schema where an `enum` under a marker can only ever be a
    hand-written `Literal[...]`.
    """
    if isinstance(document, list):
        return [strip_known_values(item) for item in document]
    if not isinstance(document, dict):
        return document
    stripped = {key: strip_known_values(value)
                for key, value in document.items()}
    if MARKER not in stripped:
        return stripped
    return {key: value for key, value in stripped.items()
            if key not in ("enum", KNOWN_VALUES_KEY)}


def marked_nodes(document):
    """``((json pointer, node), ...)`` for every node naming a concept.

    The concept-to-schema mapping, read back out of a document. The gate uses
    it over the committed contract; nothing here needs the registry, so a
    mapping this returns is a fact about the document alone.
    """
    found = []
    _collect(document, "", found)
    return tuple(found)


def _collect(node, pointer, found):
    if isinstance(node, dict):
        if isinstance(node.get(MARKER), str):
            found.append((pointer, node))
        for key, value in node.items():
            _collect(value, f"{pointer}/{_escape(key)}", found)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _collect(value, f"{pointer}/{index}", found)


def _walk(node, decisions, pointer):
    if isinstance(node, list):
        return [_walk(item, decisions, f"{pointer}/{index}")
                for index, item in enumerate(node)]
    if not isinstance(node, dict):
        return node

    walked = {key: _walk(value, decisions, f"{pointer}/{_escape(key)}")
              for key, value in node.items()}
    if MARKER not in walked:
        return walked
    return _annotate(walked, decisions, pointer or "/")


def _annotate(node, decisions, pointer):
    """One marked node, or the reason it cannot be annotated honestly."""
    def refuse(code, message):
        raise KnownValuesRefused(code, pointer, message)

    concept = node[MARKER]
    if not isinstance(concept, str) or not concept:
        refuse(codes.MALFORMED_MARKER,
               f"`{MARKER}` names a concept, not {concept!r}")

    decision = decisions.get(concept)
    if decision is None:
        refuse(codes.UNKNOWN_CONCEPT,
               f"`{concept}` is not a concept domain-vocabulary/ declares — "
               f"add it to the registry, or fix the marker")
    if not decision.contributes:
        refuse(codes.CONTRIBUTES_NOTHING,
               f"`{concept}` contributes nothing to the spec: either the "
               f"tenant owns its values, or the registry declares no openapi "
               f"consumer for it. Nothing can be advertised here")
    if not decision.advertised:
        refuse(codes.NOT_ADVERTISED,
               f"`{concept}` is not served by its backend consumer "
               f"({decision.backend_serves}), so the contract may not advertise "
               f"its values yet. Convert the consumer first — the debt is a "
               f"migration-ledger entry under G4")
    if "enum" in node:
        refuse(codes.ALREADY_ENUMERATED,
               f"this node already enumerates `{concept}` by hand. The value "
               f"set is the registry's; type the field as a string and let the "
               f"export supply it")
    if KNOWN_VALUES_KEY in node:
        refuse(codes.ALREADY_ANNOTATED,
               f"this node already carries `{KNOWN_VALUES_KEY}`, which only "
               f"this export may write")
    if not _is_string_shaped(node):
        refuse(codes.NOT_A_STRING,
               f"`{concept}` is a set of string values and this node is not "
               f"string-shaped, so nothing could travel through it")

    key = "enum" if decision.representation == ENUM else KNOWN_VALUES_KEY
    return {**node, key: list(decision.values)}


def _is_string_shaped(node):
    """Is this schema node one a string value could come back through?

    `type: "string"` is the plain case. A nullable or unioned field renders as
    `anyOf`/`oneOf` with a string member, and that is equally honest: the
    values still travel, the schema merely admits `null` beside them.
    """
    if node.get("type") == "string":
        return True
    for key in _UNION_KEYS:
        members = node.get(key)
        if isinstance(members, list) and any(
                isinstance(member, dict) and member.get("type") == "string"
                for member in members):
            return True
    return False


def _escape(key):
    """A JSON pointer segment (RFC 6901), so a path with a `/` in it — every
    OpenAPI path key — points at one node rather than reading as two."""
    return str(key).replace("~", "~0").replace("/", "~1")
