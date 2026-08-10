"""What a supplier's reported number means, and the two things never done to it.

A provider hands back ``0.00123``. Somebody converts it to micros. Today that
somebody is a developer writing ``cost * 1e6`` in a repository UBB never sees,
and *"no float enters money arithmetic"* dies silently on the far side of the
boundary. Declaring the **amount representation** is what moves that multiplier
inside something UBB can be held to; this module is the arithmetic it moves
into, written once so the Code Builder emits one conversion rather than one per
target.

**Two refusals, and both are a direction rather than a behaviour.**

* **Over-precision is refused, never rounded.** ``core.money``'s four rounding
  rules govern amounts UBB *computes* — a price line, a percentage, the carry at
  the minor-unit boundary. A reported cost is one UBB *observes*, and there is
  no rule that entitles anyone to reshape an observation. A supplier reporting
  a tenth of a micro has reported something UBB cannot hold, and the honest
  answers are "refuse it" and "hold more precision"; quietly picking the nearest
  micro is neither.
* **A supplier-returned currency that disagrees with the declared one fails.**
  v1 is single-currency with no FX, so there is no correct conversion available
  — a converting implementation would have to invent a rate, and a permissive
  one would relabel euros as dollars. Failing clearly is the only remaining
  option, and it is also the best one.

**Nothing calls this on a recording path, and nothing is meant to.** UBB
receives an integer amount in micros and a canonical currency code; it never
receives the supplier's raw decimal and never repeats the conversion
server-side (#193 §D7). What this module is, is the **executable definition of
what the generated integration must do** — the same standing
:func:`~apps.platform.event_types.source_paths.render` has for the access
expression beside it. ``apps/platform/tests/test_reported_cost_invariants.py``
holds the "never server-side" half to the tree, so it stays true rather than
being asserted here.

Django-free, like ``source_paths`` next door and for the same reason: what it
answers are questions about values, and a value question that needs an app
registry loaded is one that has picked up a dependency it does not use.
"""
from decimal import Decimal, InvalidOperation

from core.exceptions import UBBError
from core.money import MICROS_PER_UNIT, minor_units

#: The largest whole number of micros a money column in this repository can
#: hold: every one of them is a ``BigIntegerField``, which is a signed 64-bit
#: integer. An amount past it is not a rounding question — it is one UBB has
#: nowhere to put — so it is refused by the same function and for the same
#: reason as a fractional micro.
MICROS_LIMIT = 2 ** 63 - 1

#: How far a reported cost's decimal exponent may run once its trailing zeros
#: are gone. Beyond it in either direction the answer is already known — past
#: any money column one way, smaller than a micro the other — and knowing it
#: in advance matters: ``Decimal`` admits an exponent up to 999,999,999, a
#: supplier's JSON can carry one, and ``10 ** 999999999`` is not a refusal, it
#: is an unresponsive process. Comfortably wider than the nineteen digits a
#: money column holds and the six a major unit is divided into, so no amount
#: this rejects was ever convertible.
EXPONENT_LIMIT = 40
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
    AMOUNT_REPRESENTATION_MICROS,
    AMOUNT_REPRESENTATION_MINOR_UNITS,
)


class AmountNotRepresentable(UBBError):
    """This number cannot be held as an exact whole number of micros.

    A refused domain operation rather than a fact about a rendering target,
    which is why this is a :class:`~core.exceptions.UBBError` and
    ``SourcePathNotRenderable`` next door is not: there is no second style to
    fall back to and no other way to express the amount. The caller's two
    repairs — declare a different representation, or ask the supplier for a
    coarser number — are both somebody's commercial decision.
    """


class CurrencyDisagreement(UBBError):
    """The supplier's currency is not the one this declaration is denominated in.

    Never a conversion, and never a preference for one side. Which of the two
    is wrong is unknowable from here: the tenant may have declared the wrong
    currency, or the supplier may have billed in an unexpected one, and both are
    real. What is knowable is that continuing produces a number denominated in
    a currency nobody agreed on.
    """


def to_micros(amount, representation, currency):
    """``amount``, read as ``representation``, as exact whole micros.

    ``currency`` decides what a *minor unit* is and is not decorative — the
    same stance ``core.money`` takes for the same reason. A helper that assumed
    a hundredth would rebuild the bare ``10_000`` that module exists to have
    deleted from twenty sites, and it would be wrong on the first currency UBB
    admits that is not two-decimal.

    The arithmetic is integer arithmetic on the decimal's own digits, and that
    is not fussiness: **every** Decimal operation goes through the ambient
    context, which carries twenty-eight significant digits. A longer amount
    multiplied — or merely ``normalize()``d — would be rounded first and found
    integral afterwards, which is the wrong answer arriving through the very
    check written to catch wrong answers. Nothing below rounds, because nothing
    below is a Decimal operation.

    Trailing zeros are stripped from the digits rather than left to the
    division, and that is the exponent bound's doing: ``1.000`` is one however
    a supplier chose to write it, and padding it out past
    :data:`EXPONENT_LIMIT` must not turn a whole number into a refusal.
    """
    multiplier = _multiplier(representation, currency)
    sign, digits, exponent = _stripped(_as_exact_decimal(amount).as_tuple())
    unsigned = 0
    for digit in digits:
        unsigned = unsigned * 10 + digit

    if abs(exponent) > EXPONENT_LIMIT:
        raise AmountNotRepresentable(
            f"a reported cost with an exponent of {exponent} is not an amount "
            f"of money UBB can hold: it is either far past the largest a money "
            f"column takes or far smaller than one micro. Refused on the "
            f"exponent alone, before the arithmetic, because a decimal may "
            f"legally carry an exponent of hundreds of millions and computing "
            f"that power of ten is not a refusal — it is a process that stops "
            f"answering.")

    if exponent >= 0:
        micros = unsigned * 10 ** exponent * multiplier
    else:
        micros, remainder = divmod(unsigned * multiplier, 10 ** -exponent)
        if remainder:
            raise AmountNotRepresentable(
                f"{_spelled(sign, digits, exponent)} {representation} is "
                f"{_spelled(sign, str(unsigned * multiplier), exponent)} "
                f"micros, which is not a whole number of them. UBB refuses a "
                f"reported cost it cannot hold exactly rather than rounding "
                f"one it only observed: the four rounding rules govern amounts "
                f"UBB computes, and reshaping an observation makes a "
                f"supplier's invoice and UBB's ledger disagree by an amount "
                f"neither of them recorded.")

    if micros > MICROS_LIMIT:
        raise AmountNotRepresentable(
            f"{_spelled(sign, digits, exponent)} {representation} is "
            f"{micros} micros, and the largest a money column holds is "
            f"{MICROS_LIMIT}. Exact and unstorable is still unstorable, and "
            f"it is refused here rather than at the column so that what comes "
            f"back names the supplier's own number.")
    return -micros if sign else micros


def _stripped(tuple_of_decimal):
    """``as_tuple`` with trailing zeros removed from a fractional part.

    On the tuple rather than through ``normalize()``, which is a context-rounded
    operation and would quietly shorten exactly the long amounts this module
    exists to convert correctly. The last digit is kept whatever it is, so zero
    keeps a digit to be.
    """
    sign, digits, exponent = tuple_of_decimal
    digits = list(digits)
    while exponent < 0 and len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    return sign, tuple(digits), exponent


def pin_currency(declared, reported):
    """The currency this cost is denominated in, or a refusal. Never a conversion.

    ``declared`` is the fixed code on the declaration and is empty where the
    currency is read from the supplier's response instead; ``reported`` is what
    the response carried, and is ``None`` where it carried none. Exactly one of
    the two ways of pinning it is declared, which is enforced where the
    declaration is written — this is the runtime half, and it fails closed on
    the case that enforcement cannot reach.

    **Both sides are treated identically, and that is the whole shape of it.**
    Case and padding are folded on each, which is canonicalisation rather than
    conversion: ``USD`` and ``usd`` are one code spelled twice, and a version
    that folded only the supplier's side would report a disagreement between a
    currency and itself. Whichever side ends up naming the code, UBB has to be
    able to hold it — ``minor_units`` is the one place that knows which
    currencies those are, and it raises for the rest rather than inventing an
    exponent. Validating only the path form would leave the fixed form resting
    on ``clean()``, which ADR-0007 §2 is explicit is a courtesy to the ordinary
    path and never the enforcement.
    """
    pinned = (declared or "").strip().lower()
    supplied = (reported or "").strip().lower()
    if not pinned and not supplied:
        raise CurrencyDisagreement(
            "this cost is denominated in no currency: the declaration pins "
            "none and the supplier returned none. `core.money` keeps a "
            "platform default for the sites that have no tenant in scope, and "
            "it is deliberately out of reach here — a reported cost "
            "denominated by a default nobody declared is exactly the silent "
            "reinterpretation this refusal exists to prevent.")
    if pinned and supplied and pinned != supplied:
        raise CurrencyDisagreement(
            f"the supplier reported this cost in '{supplied}' and the "
            f"declaration is denominated in '{pinned}'. UBB fails here "
            f"rather than converting: v1 is single-currency with no exchange "
            f"rates, so there is no correct conversion to perform — and "
            f"reading the amount under the wrong currency would be the worst "
            f"outcome available, because it looks like a number that worked. "
            f"Either the declaration names the wrong currency or the supplier "
            f"billed in an unexpected one, and both are somebody's decision.")
    code = pinned or supplied
    minor_units(code)
    return code


def _multiplier(representation, currency):
    """Micros per one unit of ``representation``.

    A lookup rather than a table, so the three arms stay beside the reasoning:
    micros are already micros, a minor unit is whatever the currency says it is,
    and a major unit is a million of them.
    """
    if representation == AMOUNT_REPRESENTATION_MICROS:
        return 1
    if representation == AMOUNT_REPRESENTATION_MINOR_UNITS:
        return minor_units(currency)
    if representation == AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL:
        return MICROS_PER_UNIT
    raise AmountNotRepresentable(
        f"'{representation}' is not an amount representation, so what this "
        f"number means is undeclared and no conversion of it is defined. UBB "
        f"owns this whole value set.")


def _as_exact_decimal(amount):
    """``amount`` as a Decimal that means exactly what was written, or a refusal.

    A **binary float is refused outright**, and this is the one place in the
    catalogue that is stricter than the quantity beside it. A declared quantity
    reads a float through its shortest round-tripping text, because ``0.1`` in a
    supplier's JSON means a tenth and reading its binary expansion would invent
    precision nobody sent. Money does not get that courtesy: the entire purpose
    of declaring the representation is to keep *"no float enters money
    arithmetic"* true across the boundary, and accepting one here would defeat
    it at the one call site the declaration was written for. Where the
    supplier's response offers an integer or a decimal string, that is what to
    read (#193 §D5).
    """
    # `bool` is a subclass of `int`, so a flag reaching a money argument passes
    # every numeric test there is. Refused by name for that reason and no other.
    if isinstance(amount, bool):
        raise AmountNotRepresentable(
            f"{amount!r} is a flag, not a reported cost.")
    if isinstance(amount, float):
        raise AmountNotRepresentable(
            f"{amount!r} is a binary float and a reported cost is money. "
            f"Declaring what the supplier's number represents is what keeps "
            f"'no float enters money arithmetic' true across this boundary, "
            f"and reading one here would defeat that at the single call site "
            f"the declaration exists for. Read the response's integer or its "
            f"decimal string instead.")
    if amount is None:
        raise AmountNotRepresentable(
            "no cost was reported. An Event Type costed from a number the "
            "supplier reports has not been costed until the number arrives, "
            "and a missing one is not a zero.")
    try:
        exact = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError):
        raise AmountNotRepresentable(
            f"{amount!r} is not a number, so there is no cost here to "
            f"convert.") from None
    if not exact.is_finite():
        raise AmountNotRepresentable(
            f"{amount!r} is not a finite amount of money.")
    return exact


def _spelled(sign, digits, exponent):
    """A decimal, in plain positional notation, without touching the context.

    ``str`` on a small Decimal gives ``1E-9``, and a tenant reading a refusal
    about their own number should be shown their own number — so the digits are
    reassembled through :class:`Decimal`'s exact tuple constructor and formatted
    with ``f``, neither of which is a context-rounded operation. Rebuilding the
    value with arithmetic would round exactly the long amounts this refusal
    exists to report on.
    """
    exact = Decimal((sign, tuple(int(digit) for digit in
                                 (digits if isinstance(digits, str)
                                  else "".join(map(str, digits)))), exponent))
    return format(exact, "f")
