"""An exact Measurement quantity, written as text (#571, #603).

A `constant` Measurement's value is declared with it (#571), and since #603
every RECORDED quantity crosses the wire, is stored and is costed in it too —
one decimal grammar for both, so a constant's text is the text a recording of
it sends. It is an exact number of either value type: a whole count, or one
carrying a fraction, and either sign. It is held, published and read as TEXT
in ONE canonical form, because every way of holding it as a number loses
something on the way to somebody: a binary float gives 2**53 + 1 back as
...992, a numeric column fixes a scale, and Python's own `Decimal` rounds at
its context's 28 digits the moment anything normalises or adds (and
`quantize()` refuses a result longer than that). No precision cap governs a
Measurement quantity, so none is introduced here.

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
from typing import NamedTuple

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


def is_whole(canonical_text):
    """Whether canonical text is a whole number — in the canonical form,
    exactly "has no point" (the rule `ck_measurement_integer_constant_is_whole`
    states at the database)."""
    return "." not in canonical_text


class ExactParts(NamedTuple):
    """The text's value is ``sign * digits / 10 ** scale``, every part an
    exact Python integer."""

    sign: int
    digits: int
    scale: int


def exact_parts(canonical_text):
    """Canonical text as exact integers, built from its own digits (#603).

    Costing multiplies a quantity by a rate and divides once, by R1, and every
    other way to get the integers for that loses the answer before the rule is
    asked: a float has already rounded, ``Decimal`` arithmetic runs through a
    28-digit context, and ``int(text)`` refuses past CPython's 4,300-digit
    conversion bound. The digits are folded one at a time instead — the
    `event_types/reported_cost.py` pattern — so no length is too long and
    nothing rounds.

    Refuses anything that is not already canonical: costing reads only what
    the recording path stored, and a value in any other form is a defect in
    whoever handed it over, never something to repair here.
    """
    if not isinstance(canonical_text, str) or not _CANONICAL.fullmatch(
            canonical_text):
        raise NotAnExactDecimal(
            f"{canonical_text!r} is not a quantity in its canonical exact "
            f"form; costing reads only what recording stored.")
    sign = -1 if canonical_text.startswith("-") else 1
    whole, _, fraction = canonical_text.removeprefix("-").partition(".")
    digits = 0
    for digit in whole + fraction:
        digits = digits * 10 + (ord(digit) - 48)
    return ExactParts(sign, digits, len(fraction))


def canonical_quantity(value):
    """One recorded quantity in its canonical text, or refuse it (#603).

    Text goes through :func:`canonical`, the one grammar. A Python ``int`` is
    accepted beside it because it is exact by construction — it is the
    service-level door's spelling of a whole number, never a JSON number,
    which the wire refuses before anything reaches here — and its own decimal
    digits are its canonical text. Everything else is refused: a ``bool`` is
    not the number one, a ``float`` has already rounded, and a ``Decimal``
    would hand this function a context's opinion of the value rather than the
    value a caller wrote.
    """
    if isinstance(value, bool):
        raise NotAnExactDecimal(
            f"{value!r} is a flag, not a quantity: a quantity is written as "
            f"a string.")
    if isinstance(value, int):
        return canonical("-" + _digits_of(-value) if value < 0
                         else _digits_of(value))
    return canonical(value)


def canonical_quantities(bag):
    """A measured bag with every value in its canonical text — refusing, by
    name, the first value that is not an exact decimal."""
    if not bag:
        return {}
    canonical_bag = {}
    for name, value in bag.items():
        try:
            canonical_bag[name] = canonical_quantity(value)
        except NotAnExactDecimal as refused:
            raise NotAnExactDecimal(f"measurements.{name}: {refused}") from None
    return canonical_bag


def _digits_of(whole):
    """A non-negative Python ``int``'s decimal digits. ``str(int)`` refuses
    past CPython's 4,300-digit conversion bound, so a longer one is written
    out a digit at a time."""
    if whole < _STR_IS_SAFE_BELOW:
        return str(whole)
    written = []
    while whole:
        whole, digit = divmod(whole, 10)
        written.append(chr(48 + digit))
    return "".join(reversed(written))


_CANONICAL = re.compile(CANONICAL)


def is_canonical(value):
    """Whether ``value`` is text already in the one canonical form — what a
    reader of stored text asks before trusting it, never a way to make it."""
    return isinstance(value, str) and _CANONICAL.fullmatch(value) is not None

_STR_IS_SAFE_BELOW = 10 ** 4000
