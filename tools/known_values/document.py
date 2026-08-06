"""The generated decision document: what the spec may say about each concept.

`openapi/known-values.json` is one row per registry concept, and each row is a
**decision** rather than a copy of the registry:

    representation   what the spec would carry for this concept, by its KIND —
                     an `open` concept's recognised values as documentation
                     metadata, a `closed` one's as a real `enum`, and nothing
                     at all where the tenant owns the values or the registry
                     declares no contract consumer.
    advertised       whether the spec carries it TODAY, which is a different
                     question and the one #208 exists to answer: the spec
                     advertises a value only where the backend already serves
                     it. Emitting the final values on a field that still
                     returns the retired one would put a falsehood into the
                     published contract, which is worse than saying nothing
                     because a consumer can act on it.
    backend_serves   how much of the concept the backend holds by reference,
                     as `<held> of <total> values`. This is what makes an
                     unadvertised row falsifiable rather than a shrug, and it
                     is the extent the migration ledger records.

The document is data with no language in it, so the Django spec export can read
it without PyYAML, without the registry compiler and without leaving the
platform's dependency set — while the decision itself is taken once, in the
Django-free tool, where the consumer census can be consulted.

**Why the values are absent unless advertised.** A row that carried them
anyway would be a loaded gun: every later reader of this file would have the
final value set in hand and one boolean between it and the published contract.
Absent means absent.
"""

from dataclasses import dataclass

from .errors import DOCUMENT_INVALID, KnownValuesRefused

#: A `closed` concept: exactly these values, so the spec may say `enum`.
ENUM = "enum"

#: An `open` concept: recognised values as documentation metadata, never an
#: `enum` array. ADR-0003 — a value UBB has never seen is legal, and a schema
#: that enumerated the set would make UBB learning a new one a breaking change.
KNOWN_VALUES = "known_values"

#: The concept contributes nothing to the spec. Two causes, deliberately one
#: representation: the tenant owns the values (map #137 constraint 5), or the
#: registry declares no `openapi` consumer, so the registry itself says this
#: concept does not appear in the contract.
NOTHING = "none"

REPRESENTATIONS = (ENUM, KNOWN_VALUES, NOTHING)

#: The surface whose consumers decide whether a value may be advertised. Named
#: once here because two places ask it — the renderer and the gate.
BACKEND = "backend"

#: The surface a concept must declare a consumer on before the spec may carry
#: anything for it at all.
CONTRACT = "openapi"

BANNER = ("from domain-vocabulary/ — do not edit by hand. Regenerate with "
          "`python -m tools.vocabulary --write`.")

VERSION = 1

# Document keys. Module constants rather than literals scattered through the
# renderer, the applier and the gate, because all three read the same document
# and a typo in one of them would look exactly like a concept nobody decided.
GENERATED_KEY = "@generated"
VERSION_KEY = "version"
CONCEPTS_KEY = "concepts"
KIND_KEY = "kind"
REPRESENTATION_KEY = "representation"
ADVERTISED_KEY = "advertised"
SERVES_KEY = "backend_serves"
VALUES_KEY = "values"


@dataclass(frozen=True)
class Decision:
    """One concept's row, as the applier and the gate read it.

    A record rather than the raw mapping so that a missing key is a fault at
    the boundary rather than a ``None`` that travels three functions before it
    means anything — and frozen, because a decision the applier could edit
    mid-walk would make one document mean two things.
    """
    concept: str
    kind: str
    representation: str
    advertised: bool
    backend_serves: str | None
    values: tuple | None

    @property
    def contributes(self):
        """Does this concept put anything in the spec at all, ever?"""
        return self.representation != NOTHING


def decide(concept, census):
    """One concept's :class:`Decision`, from the registry and the census.

    The whole of #208's rule lives here, in one function, over two inputs:

    - the concept's KIND decides the representation, which is why an `open`
      concept can never become an `enum` by accident — nothing downstream reads
      the kind again;
    - the CENSUS decides whether it is advertised, through
      :meth:`tools.consumers.Census.serves`. That predicate is #227's and is
      consumed rather than rebuilt here; two implementations of one predicate
      is the shape that already bit #203.

    A census that could not answer — no declared backend consumer, or a fault
    that stopped the walk — yields ``advertised=False``. A broken census may
    therefore WITHHOLD metadata and can never invent it, which is the only
    direction of error that keeps a published contract honest.
    """
    representation = _representation(concept)
    verdicts = [v for v in census.verdicts
                if v.concept == concept.name and v.surface == BACKEND]

    advertised = bool(
        representation != NOTHING and verdicts
        and census.serves(concept.name, BACKEND))

    return Decision(
        concept=concept.name,
        kind=concept.kind,
        representation=representation,
        advertised=advertised,
        backend_serves=_extent(concept, verdicts),
        values=tuple(concept.declared_values) if advertised else None,
    )


def _representation(concept):
    """What the spec would carry for this concept, by its kind.

    `tenant_defined` and `free_text` declare no values by construction, so
    there is nothing to represent. A concept the registry gives no `openapi`
    consumer is equally silent, and that is the registry's own statement that
    the concept does not appear in the contract — not an omission this
    generator gets to second-guess.
    """
    if not concept.declared_values:
        return NOTHING
    if not any(c.surface == CONTRACT for c in concept.consumers):
        return NOTHING
    return KNOWN_VALUES if concept.known_values else ENUM


def _extent(concept, verdicts):
    """``"<held> of <total> values"``, or ``None`` where nothing is measurable.

    Held is the INTERSECTION across the declared backend consumers, because
    that is what :meth:`Census.serves` means when a concept has more than one:
    a value one consumer imports and another restates is not held by the
    backend. Reporting the union would make the number disagree with the
    verdict beside it.
    """
    if not concept.declared_values or not verdicts:
        return None
    held = set.intersection(*(set(v.held) for v in verdicts))
    return f"{len(held)} of {len(concept.declared_values)} values"


def build(registry, census):
    """The whole document, as plain JSON-serialisable data.

    EVERY concept appears, including the ones that contribute nothing. A reader
    must be able to tell "this concept declares no values UBB owns" from "the
    generator lost it", and the second is the failure worth catching — the same
    reason the generated Python and TypeScript artifacts carry a section for a
    `tenant_defined` concept saying exactly that.
    """
    concepts = {}
    for name, concept in sorted(registry.concepts.items()):
        decision = decide(concept, census)
        row = {
            KIND_KEY: decision.kind,
            REPRESENTATION_KEY: decision.representation,
            ADVERTISED_KEY: decision.advertised,
            SERVES_KEY: decision.backend_serves,
        }
        if decision.values is not None:
            row[VALUES_KEY] = list(decision.values)
        concepts[name] = row
    return {
        GENERATED_KEY: BANNER,
        VERSION_KEY: VERSION,
        CONCEPTS_KEY: concepts,
    }


def read(document):
    """``{concept: Decision}`` from a parsed document, or say why it is unusable.

    Validated rather than trusted. The applier runs inside the spec export, and
    a malformed row reaching it would either crash somewhere unhelpful or —
    worse — read as "not advertised" and silently strip metadata the contract
    should have carried.
    """
    def refuse(location, message):
        raise KnownValuesRefused(DOCUMENT_INVALID, location, message)

    if not isinstance(document, dict):
        refuse(CONCEPTS_KEY, "the document is a JSON object")
    if document.get(VERSION_KEY) != VERSION:
        refuse(VERSION_KEY,
               f"this applier reads version {VERSION}, the document declares "
               f"{document.get(VERSION_KEY)!r}")
    concepts = document.get(CONCEPTS_KEY)
    if not isinstance(concepts, dict) or not concepts:
        refuse(CONCEPTS_KEY, "`concepts` is a non-empty object of concept name "
                             "to decision")

    decisions = {}
    for name, row in concepts.items():
        location = f"{CONCEPTS_KEY}/{name}"
        if not isinstance(row, dict):
            refuse(location, "a decision is a JSON object")
        representation = row.get(REPRESENTATION_KEY)
        if representation not in REPRESENTATIONS:
            refuse(location, f"`{REPRESENTATION_KEY}` is one of "
                             f"{', '.join(REPRESENTATIONS)}")
        advertised = row.get(ADVERTISED_KEY)
        if not isinstance(advertised, bool):
            refuse(location, f"`{ADVERTISED_KEY}` is a boolean")
        values = row.get(VALUES_KEY)
        if advertised and (not isinstance(values, list) or not values
                           or not all(isinstance(v, str) for v in values)):
            refuse(location, f"an advertised concept carries its `{VALUES_KEY}` "
                             f"as a non-empty list of strings")
        if not advertised and VALUES_KEY in row:
            refuse(location, f"an unadvertised concept carries no `{VALUES_KEY}` "
                             f"— absent means absent, so nothing downstream has "
                             f"the value set in hand")
        decisions[name] = Decision(
            concept=name,
            kind=row.get(KIND_KEY),
            representation=representation,
            advertised=advertised,
            backend_serves=row.get(SERVES_KEY),
            values=tuple(values) if advertised else None,
        )
    return decisions
