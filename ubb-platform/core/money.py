"""Money: the currency's minor unit, and the four rounding rules.

UBB holds money as an exact whole number of **micros** (a millionth of a
currency unit). A currency's **minor unit** — the cent, the penny — is a
different, coarser thing, and it is the only unit Stripe will move. This module
owns the conversion between the two, and the rules for when a division is
allowed to lose a fraction.

Before this module existed, "a currency has a hundred minor units" was written
out twenty times across eleven files as a bare ``10_000``. That is why
``SUPPORTED_CURRENCIES`` admits two-decimal currencies only: not a product
decision, but the cost of changing twenty sites at once
(``tenants/models.py`` CUR-1). With the assumption in one table, admitting yen
becomes a data change here plus a live money test in that currency.

**The currency parameter is not decorative.** v1 is single-currency in
practice, but a helper that dropped the parameter would rebuild exactly the
coupling this module exists to delete. The restriction is meant to become a
choice; today it is a constraint.

The four rules (``docs/plans/2026-07-30-money-model-decision.md`` §5.2):

- **R1** — a computed price line rounds half-up to whole micros, at the moment
  it is computed. That is :func:`round_charge`.
- **R2** — everything downstream is exact. Nothing rounds between R1 and R3.
- **R3** — the minor unit is reached exactly once, at the money boundary, and
  the remainder is *always* carried. That is :func:`to_minor`, which returns
  the remainder rather than hiding it: a caller can still drop it, but only by
  writing the line that does so.
- **R4** — a percentage producing a *charge* rounds half-up
  (:func:`round_charge`); a percentage producing a *ceiling* rounds down
  (:func:`round_ceiling`), so a spend control binds no later than the value the
  tenant declared. That is the one direction a limit must never err.

:func:`assert_aligned` is the boundary assertion those rules imply: proof that
the carry ran before an amount left for Stripe. It is not a conversion — the
conversion is :func:`to_minor` — and it is deliberately not a place to fix an
unaligned amount, because by then the remainder has nowhere to go.
"""

from core.exceptions import MisalignedAmount, UnknownCurrency

# A micro is a millionth of a currency unit; every stored money column is an
# exact whole number of these.
MICROS_PER_UNIT = 1_000_000

# ISO 4217 minor-unit exponent per currency: 2 means the minor unit is a
# hundredth (cents), 0 means the currency has no minor unit (yen), 3 means a
# thousandth (dinars). CUR-1 admits two-decimal currencies only — see the
# module docstring for why, and `test_money.py` for the test that makes
# admitting any other kind a conscious act.
#
# Zero- and three-decimal currencies are NOT merely absent from this table:
# three-decimal ones carry Stripe's own rule that amounts round to the nearest
# ten minor units, and no currency class is trusted until it has been through a
# live Stripe money test in that currency.
_MINOR_UNIT_EXPONENT = {
    "usd": 2, "eur": 2, "gbp": 2, "aud": 2, "cad": 2, "chf": 2,
    "nzd": 2, "sgd": 2, "hkd": 2, "sek": 2, "nok": 2, "dkk": 2,
    "pln": 2, "czk": 2, "mxn": 2, "brl": 2, "inr": 2, "zar": 2,
}

# CUR-1: the currencies a tenant may hold. One table, one place — a currency is
# supported exactly when this module knows its minor unit, which is the whole
# point of keeping the two facts together.
SUPPORTED_CURRENCIES = frozenset(_MINOR_UNIT_EXPONENT)

# The currency to name where no tenant is in scope — request-schema validation
# runs before a tenant is resolved, and a Stripe object's own currency is
# unbounded (a connected account may hold subscriptions in currencies UBB never
# admitted). Sites that use this are honest about assuming the platform default
# rather than silently defaulting inside the helpers.
DEFAULT_CURRENCY = "usd"


def minor_units(currency: str) -> int:
    """Micros in one minor unit of ``currency`` — the multiplier.

    10,000 for a two-decimal currency: a cent is a hundredth of a unit, and a
    unit is a million micros. This is the number the twenty sites used to
    hard-code.

    Raises :class:`~core.exceptions.UnknownCurrency` rather than falling back
    to a default. A call site with no tenant in scope may still choose
    :data:`DEFAULT_CURRENCY`, but it has to name that choice in its own code
    where a reader can see it — the helper will not make it silently.
    """
    try:
        exponent = _MINOR_UNIT_EXPONENT[currency.lower()]
    except (AttributeError, KeyError):
        raise UnknownCurrency(
            f"currency={currency!r} has no known minor unit "
            f"(supported: {', '.join(sorted(SUPPORTED_CURRENCIES))})"
        ) from None
    return MICROS_PER_UNIT // 10 ** exponent


def to_minor(amount_micros: int, currency: str) -> tuple[int, int]:
    """Floor ``amount_micros`` to whole minor units, returning ``(minor, remainder)``.

    R3's floor-with-carry. The remainder comes back rather than being swallowed
    so that dropping it is a visible act at the call site: ``minor, _ =`` says
    plainly that this caller is throwing money away, and reviewers can see it.

    Two invariants hold for every input, negative included:

    - ``minor * minor_units(currency) + remainder == amount_micros`` — exact
      reassembly, so nothing is lost in the conversion itself.
    - ``0 <= remainder < minor_units(currency)`` — the carry is always a real
      sub-minor-unit fraction.
    """
    return divmod(amount_micros, minor_units(currency))


def from_minor(amount: int, currency: str) -> int:
    """Convert a whole number of minor units to micros. Always exact."""
    return amount * minor_units(currency)


def assert_aligned(amount_micros: int, currency: str) -> None:
    """Refuse an amount that is not a whole number of minor units.

    This is an assertion that the carry ran — not a conversion, and not a
    rounding policy. An amount arriving here with a remainder means some
    upstream step skipped :func:`to_minor`, and the remainder now has nowhere
    to be carried to; rounding it away silently is exactly the bug R3 exists to
    prevent. Convert with :func:`to_minor`; assert here.
    """
    _, remainder = to_minor(amount_micros, currency)
    if remainder:
        raise MisalignedAmount(
            f"amount_micros={amount_micros} is not a whole number of "
            f"{currency} minor units (remainder={remainder})"
        )


def round_charge(numerator: int, denominator: int) -> int:
    """Half-up division — R1 and R4's charging direction.

    Used wherever a rate or a percentage produces an amount someone pays: a
    priced line, a markup, a platform fee. Ties go up, which is unbiased
    against the tenant everywhere except an exact half.
    """
    if denominator <= 0:
        raise ValueError(f"denominator must be positive, got {denominator}")
    return (numerator + denominator // 2) // denominator


def round_ceiling(numerator: int, denominator: int) -> int:
    """Floor division — R4's ceiling direction.

    Used wherever a percentage produces a *limit* rather than a charge: a COGS
    ceiling, a spend cap. Rounds down so the limit binds no later than the
    exact value the tenant declared. A ceiling that rounded up would let a job
    burn marginally more than it was told to, which is the one direction a
    spend control must never err.
    """
    if denominator <= 0:
        raise ValueError(f"denominator must be positive, got {denominator}")
    return numerator // denominator
