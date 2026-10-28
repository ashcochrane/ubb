"""A field that returns only some of its closed concept's values (R10-W5).

The registry owns a closed concept's canonical tokens (ADR-0008 §2), and the
spec export writes them as the field's `enum`. Most fields can return every
value their concept occurs with. Some cannot: the business rollup states its
revenue under one basis only, and an end customer's own revenue summary never
meets the grouped question whose grain it could not answer. A public field
advertises what it can actually return and nothing more (the owner's review of
#621), because every value an `enum` names is a branch a generated client
writes for a response that never comes.

So the FIELD owns where it sits within its concept, and the registry still owns
the tokens:

    basis: RevenueBasis          # the marker alone: every value it occurs with
    MarginRevenueBasis = a_field_of("revenue_basis", MARGIN_REVENUE_BASIS)
    basis: MarginRevenueBasis    # this value of it, and no other

- The values are the registry's generated constants (``core/vocabulary.py``),
  never spelled here, so a field cannot name a token the registry does not.
- The schema keeps its concept marker, ``x-ubb-concept``, so the vocabulary
  tooling still knows which concept the field carries; ``x-ubb-field-values``
  beside it lists the values this field can return. The spec export
  (``tools/known_values/apply.py``) refuses a value the concept does not occur
  with and a list that is the whole set, and writes the field's `enum` from
  the registry, in the registry's order. It is not a one-value concept: there
  is still exactly one authority for the tokens.
- A ``Literal`` of the same values types the field, so the response boundary
  refuses a value outside them rather than publishing it.
"""
from typing import Annotated, Literal

from pydantic import Field

#: The concept marker every closed-concept field carries
#: (``tools/known_values/apply.py`` ``MARKER``).
CONCEPT_KEY = "x-ubb-concept"

#: The values this field can return, beside the marker
#: (``tools/known_values/apply.py`` ``FIELD_VALUES_KEY``).
FIELD_VALUES_KEY = "x-ubb-field-values"


def a_field_of(concept, *values):
    """A string field carrying ``concept`` that can return only ``values``.

    The schema pydantic renders for the ``Literal`` is replaced by a plain
    string with the two extensions: an `enum` under the marker is the
    hand-written restatement the export refuses, and the export writes the
    real one from the registry.
    """
    if not values or len(set(values)) != len(values):
        raise ValueError(
            f"a field of {concept!r} names the distinct values it can return, "
            f"not {values!r}")

    def stamped(schema):
        schema.pop("enum", None)
        schema.pop("const", None)
        schema["type"] = "string"
        schema[CONCEPT_KEY] = concept
        schema[FIELD_VALUES_KEY] = list(values)

    return Annotated[Literal[values], Field(json_schema_extra=stamped)]
