"""A declared exact decimal, written as text (#571).

A `constant` Measurement's value is declared with it, and it is an exact
number of either value type: a whole count, or one carrying a fraction. It is
held, published and read as TEXT in ONE canonical form, because every way of
holding it as a number loses something on the way to somebody: a binary float
gives 2**53 + 1 back as ...992, a numeric column fixes a scale, and Python's
own `Decimal` rounds at its context's 28 digits the moment anything normalises,
quantizes or adds. No precision limit governs a Measurement quantity, so none
is introduced here.

**The text is not evidence that the value is a string.** The declared
`value_type` gives the semantics; a renderer that emits the value emits a
correctly typed exact literal for its target.

Two grammars, and the one function between them:

* :data:`ACCEPTED` — what a caller may write. Base 10, an optional leading
  ``-``, ASCII digits, and an optional fractional part with a digit on each
  side of the point. No exponent, no ``+``, no whitespace, separators or
  locale formatting. It is JSON's number syntax with the exponent removed and
  leading zeros admitted; like JSON it refuses ``.5`` and ``5.``.
* :data:`CANONICAL` — the one form stored and published. :data:`ACCEPTED`
  with no unnecessary leading zero, no trailing fractional zero, no trailing
  point, and ``0`` for every spelling of zero, ``-0`` included.

The grammar is checked by a full match over ASCII ``[0-9]``, never by asking
``Decimal`` whether the text is a number: ``Decimal`` reads surrounding
whitespace, underscores, any script's digits, ``NaN``, ``Infinity`` and
exponents, and every one of those would pass. The canonical form is then made
by editing the text, so the value is never a number on the way.
"""
import re

#: What a caller may write, unanchored. Anchor it with :func:`anchored`
#: wherever it is published or enforced outside :func:`canonical`.
ACCEPTED = r"-?[0-9]+(\.[0-9]+)?"

#: The one form stored and published, unanchored.
CANONICAL = r"0|-?(0\.[0-9]*[1-9]|[1-9][0-9]*(\.[0-9]*[1-9])?)"

_ACCEPTED = re.compile(ACCEPTED)


def anchored(grammar):
    """``grammar`` as a whole-string pattern for a reader that searches.

    JSON Schema's ``pattern`` and PostgreSQL's ``~`` both match anywhere in
    the text, so a grammar published or checked there must say where it
    starts and stops. Python's side never needs it: :func:`canonical` asks
    for a full match.
    """
    return f"^({grammar})$"


class NotAnExactDecimal(ValueError):
    """The text is not an exact decimal as :data:`ACCEPTED` reads one."""


def canonical(text):
    """``text`` in its one canonical form, or refuse it. Never rounds.

    ``01.500`` is ``1.5``, ``12.0`` is ``12`` and ``-0.000`` is ``0``. Whether
    a fraction is admissible is not decided here — that is the declared value
    type's, read by the Measurement's own ``validate_value``.
    """
    if not isinstance(text, str):
        raise NotAnExactDecimal(
            f"{text!r} is not text. A declared exact decimal is written as a "
            f"string, so that no binary float carries it on the way.")
    if not _ACCEPTED.fullmatch(text):
        raise NotAnExactDecimal(
            f"{text!r} is not an exact decimal as UBB reads one: base-10 "
            f"digits with an optional leading '-' and an optional fractional "
            f"part, with a digit on each side of the point. No exponent, no "
            f"'+', and no spaces, separators or locale formatting.")
    negative = text.startswith("-")
    whole, _, fraction = text.removeprefix("-").partition(".")
    whole = whole.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    written = f"{whole}.{fraction}" if fraction else whole
    if written == "0":
        return "0"
    return f"-{written}" if negative else written
