"""The structured source path: what one is, how it renders, and what UBB advises.

A declared quantity has to say **where the number comes from** in a supplier's
response. The obvious way to store that is the expression a developer would
write — ``response.usage.input_tokens`` — and it is wrong twice over. It is
Python source in a database column, and the Code Builder emits more than one
language; and it fixes the *access syntax* into a value that is supposed to be
about the *field names*.

So a path is **canonical segments** — ``["usage_metadata", "prompt_token_count"]``
— and this module owns the whole of what that means: the grammar
(:func:`path_errors`), the rendering (:func:`render`) and the advice
(:func:`advisories`). One module, because those three are one decision seen from
three sides, and splitting them is how the grammar and the renderer come to
disagree about what a segment is.

**The two rules that govern rendering** (#193 §C9, #156 §5.1):

* **The renderer may change access syntax.** Segments become attribute access or
  subscript access as the target language requires. Both are the same path.
* **The renderer must never translate a field name.** Google's REST response
  carries ``usageMetadata.promptTokenCount`` and its Python SDK object carries
  ``usage_metadata.prompt_token_count`` — same number, same supplier, different
  names. Rendering one into the other is supplier-shape knowledge, and
  performing it would make UBB's catalogue commercially load-bearing by the back
  door. A path that cannot be rendered into a target is REFUSED, never mangled
  to fit: emitting something that looks right is worse than emitting nothing.

**And the advisory is advice.** :func:`advisories` says a path looks
inconsistent with the shape it is declared against. It never edits a segment,
never returns a corrected path, and nothing in this module gives it a way to:
the quiet rewrite of a tenant's own mapping is the failure being designed out,
so advice is the entire product.
"""
import re

from core.vocabulary import (
    SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1,
    SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
    SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1,
)

#: Attribute access — ``response.usage_metadata.prompt_token_count``. Available
#: only where every segment is spellable as an identifier in the target
#: language, which is a property of the SUPPLIER's key rather than of UBB.
ACCESS_ATTRIBUTE = "attribute"

#: Subscript access — ``response["usage_metadata"]["prompt_token_count"]``. The
#: universal one: a mapping key can be any string, so this style can express
#: every path this module admits.
ACCESS_SUBSCRIPT = "subscript"

ACCESS_STYLES = (ACCESS_ATTRIBUTE, ACCESS_SUBSCRIPT)

#: The default name of the thing the path is read from. A parameter with a
#: default rather than a constant baked into the output, because what the
#: supplier's response is bound to is the emitting target's business and not
#: this module's.
DEFAULT_ROOT = "response"

#: What makes a stored value an EXPRESSION rather than a key. A segment is one
#: key, so anything that composes, calls or quotes is refused.
#:
#: Deliberately a list of what an expression is made of, and NOT an identifier
#: pattern. `x-request-id` is a real JSON key and `Content-Type` is a real
#: header; a charset UBB invented would be UBB deciding what a supplier is
#: allowed to call its own fields, which is the same objection that made the
#: catalogue's keys plain character fields rather than slugs.
EXPRESSION_CHARACTERS = tuple(".[]()\"'`,{}$")

#: An identifier, for the one question this module asks about a segment's
#: spelling: can a target language reach it by attribute access at all? Not a
#: rule about what a segment may BE — see above — only about what can be
#: rendered without inventing a name.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Two field-naming conventions, which is as many as the trap needs: one
#: supplier's wire format and its own SDK spell the same field differently, and
#: a path written against one and declared against the other reads the wrong
#: number or no number at all.
CONVENTION_SNAKE = "snake_case"
CONVENTION_LOWER_CAMEL = "lowerCamelCase"

#: Which convention each response shape UBB RECOGNISES names its fields in.
#:
#: Keyed on the generated names rather than on their spellings, so this table
#: cannot drift from the registry — and covered by a test that every recognised
#: shape appears, so a shape UBB learns cannot quietly become one it has nothing
#: to say about. `custom` is absent by construction: it names no shape UBB
#: knows, which is exactly when UBB validates nothing.
SHAPE_CONVENTIONS = {
    SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1: CONVENTION_LOWER_CAMEL,
    SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1: CONVENTION_SNAKE,
    SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1: CONVENTION_SNAKE,
}


class SourcePathNotRenderable(Exception):
    """This path cannot be expressed in this access style without renaming it.

    Raised rather than worked around, because every way round it is a rename:
    dropping the hyphen, camel-casing the segment, or guessing at an accessor
    the supplier might also provide. #156 §5.4 — the builder states that no
    compatible mapping exists and asks for one, and does not emit
    plausible-looking code.

    Not a :class:`~core.exceptions.UBBError`: this is a fact about a rendering
    target rather than a refused domain operation, and the caller that meets it
    is the emitter choosing a style, which has another style available.
    """


# ---------------------------------------------------------------------------
# The grammar
# ---------------------------------------------------------------------------

def path_errors(segments):
    """Why ``segments`` is not a structured path, as messages, or ``()``.

    Messages rather than an exception, because the caller is a model's
    ``clean()`` which collects several fields' complaints before raising one
    error. A path is a **sequence of keys**; the two ways to get it wrong are
    to store something that is not a sequence of strings, and to store a code
    expression in one of them.
    """
    if isinstance(segments, (str, bytes)) or not isinstance(segments, (list, tuple)):
        return (f"is {type(segments).__name__} rather than a list of segments. "
                f"A source path is structured data — "
                f"{['usage_metadata', 'prompt_token_count']} — never an "
                f"expression, because the builder emits more than one language "
                f"and a stored expression is portable to none of them.",)

    errors = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, str):
            errors.append(f"segment {index} is {type(segment).__name__}; every "
                          f"segment is a key, spelled as the supplier spells it")
            continue
        if not segment.strip():
            errors.append(f"segment {index} is empty; a path that reads nothing "
                          f"is a path with a step missing rather than a step "
                          f"that reads the whole response")
            continue
        found = [character for character in EXPRESSION_CHARACTERS
                 if character in segment]
        if found or segment != segment.strip():
            errors.append(
                f"segment {index} ({segment!r}) is an expression, not a key: it "
                f"carries {''.join(found) or 'whitespace'}. Split it — "
                f"`a.b` is two segments, and `a[\"b\"]` is the same two")
    return tuple(errors)


# ---------------------------------------------------------------------------
# The rendering
# ---------------------------------------------------------------------------

def render(segments, access, root=DEFAULT_ROOT):
    """``segments`` as one access expression, in ``access`` style.

    The whole of "the renderer may change syntax and never names": every
    segment appears in the output exactly as it was declared, and the only
    thing ``access`` chooses is the punctuation between them.
    """
    if access not in ACCESS_STYLES:
        raise ValueError(f"{access!r} is not an access style; the styles are "
                         f"{', '.join(ACCESS_STYLES)}")
    if access == ACCESS_SUBSCRIPT:
        return root + "".join(f'["{segment}"]' for segment in segments)

    unreachable = [segment for segment in segments
                   if not _IDENTIFIER.match(segment)]
    if unreachable:
        raise SourcePathNotRenderable(
            f"{unreachable} cannot be reached by attribute access in this "
            f"target, and UBB does not rename a supplier's own field to make it "
            f"fit. Emit this path as {ACCESS_SUBSCRIPT} access instead.")
    return ".".join([root, *segments])


# ---------------------------------------------------------------------------
# The advice
# ---------------------------------------------------------------------------

def advisories(shape_id, segments):
    """What looks inconsistent about ``segments`` under ``shape_id``. Advice only.

    Empty for a shape UBB does not recognise — including ``custom``, where the
    tenant has declared a wrapper of their own and UBB has said outright that it
    validates nothing — and empty for a segment whose convention cannot be told
    apart, which is most single-word keys and all of them by design: an advisory
    that fired on ``usage`` would be raised until it was switched off.

    Nothing here returns a corrected segment, and that is the point rather than
    an omission. UBB's catalogue must not become commercially load-bearing by
    the back door, and the quiet rewrite is the exact mechanism by which it
    would.
    """
    expected = SHAPE_CONVENTIONS.get(shape_id)
    if expected is None or not isinstance(segments, (list, tuple)):
        return ()

    found = []
    for segment in segments:
        if not isinstance(segment, str):
            continue
        convention = _convention_of(segment)
        if convention is not None and convention != expected:
            found.append(
                f"`{segment}` is {convention}, and {shape_id} names its fields "
                f"in {expected}. UBB does not translate field names, so this "
                f"path will be emitted exactly as it is declared — check it "
                f"against the client you are integrating, or declare the shape "
                f"the path is actually written against.")
    return tuple(found)


def _convention_of(segment):
    """``segment``'s naming convention, or ``None`` where it has no opinion.

    A single lowercase word is both conventions at once, which is why the
    answer is three-valued: the alternative is to call it snake_case and then
    warn about every ``usage`` declared against a camelCase shape.
    """
    has_underscore = "_" in segment.strip("_")
    has_upper = any(character.isupper() for character in segment)
    if has_underscore and not has_upper:
        return CONVENTION_SNAKE
    if has_upper and not has_underscore:
        return CONVENTION_LOWER_CAMEL
    return None
