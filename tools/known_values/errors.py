"""Why the committed contract could not be given its known-value metadata.

Codes, not sentences, for ``tools/vocabulary/errors.py``'s reason: a test
asserts on the reason a refusal happened, so rewording a message must never
turn a negative control into a test that passes for the wrong cause.
"""

#: The marker names a concept `domain-vocabulary/` does not declare.
UNKNOWN_CONCEPT = "unknown-concept"

#: The marker names a concept that contributes nothing to the spec — the
#: tenant owns its values, or the registry declares no contract consumer for it.
CONTRIBUTES_NOTHING = "contributes-nothing"

#: The marker names a concept the backend does not yet serve. #208's rule: the
#: spec advertises a value only where the backend already serves it.
NOT_ADVERTISED = "not-advertised"

#: The marked node already carries an `enum` — a hand-written restatement of a
#: value set the registry owns, and for an `open` concept the silent conversion
#: G4 exists to refuse.
ALREADY_ENUMERATED = "already-enumerated"

#: The marked node already carries known-value metadata, so somebody hand-wrote
#: what this applier generates.
ALREADY_ANNOTATED = "already-annotated"

#: The marked node is not a string-shaped schema, so no value set could travel
#: through it honestly.
NOT_A_STRING = "not-a-string"

#: The marker's value is not a concept name at all.
MALFORMED_MARKER = "malformed-marker"

#: The generated document is not the shape this applier reads.
DOCUMENT_INVALID = "document-invalid"

#: A field's own values (`x-ubb-field-values`) are not a non-empty list of
#: distinct strings.
MALFORMED_FIELD_VALUES = "malformed-field-values"

#: A field narrows an `open` concept. Its recognised values are documentation
#: beside a plain string, so there is no `enum` for a field to narrow.
FIELD_VALUES_ON_AN_OPEN_CONCEPT = "field-values-on-an-open-concept"

#: A field names a value its concept does not declare as occurring — a token
#: the registry never declared, or one it withholds. The field may narrow the
#: concept's set, never extend it.
FIELD_VALUE_NOT_OCCURRING = "field-value-not-occurring"

#: A field names every value its concept occurs with, which is the plain
#: marker's job: a second spelling of the whole set is a second authority.
FIELD_VALUES_ARE_THE_WHOLE_SET = "field-values-are-the-whole-set"


class KnownValuesRefused(Exception):
    """The document or a marked schema node cannot be rendered honestly.

    Carries a code and the JSON pointer of the node that caused it, because a
    spec export that fails must say *which field* it failed on — a bare message
    sends the author looking through 165 component schemas by hand.
    """

    def __init__(self, code, location, message):
        self.code = code
        self.location = location
        self.message = message
        super().__init__(f"{location}: {message} [{code}]")
