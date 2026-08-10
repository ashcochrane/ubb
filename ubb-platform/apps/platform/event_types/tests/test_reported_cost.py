"""The two operations a reported supplier cost needs, and their two refusals (#266).

Values rather than rows, so no database: what is under test is arithmetic and a
comparison, and both are the thing the Code Builder emits into a tenant's own
repository. Emitting them wrong is a cost that is wrong in production and right
in every test UBB runs, which is why the refusals are pinned here rather than
described.

Two claims, and each is a *direction* rather than a behaviour:

* **An amount that cannot be represented exactly in micros is REFUSED, never
  rounded.** The four rounding rules in ``core.money`` govern amounts UBB
  computes; this is one it observes, and reshaping an observed number silently
  is how a supplier's invoice and UBB's stop disagreeing.
* **A supplier-returned currency that disagrees with the declared one FAILS,
  never converts.** v1 is single-currency with no FX, so there is no correct
  conversion available and the silent reinterpretation is the worst outcome on
  the table.
"""
from decimal import Decimal

import pytest

from apps.platform.event_types.reported_cost import (
    AmountNotRepresentable,
    CurrencyDisagreement,
    pin_currency,
    to_micros,
)
from core.exceptions import UnknownCurrency
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
    AMOUNT_REPRESENTATION_MICROS,
    AMOUNT_REPRESENTATION_MINOR_UNITS,
    AMOUNT_REPRESENTATION_VALUES,
)

USD = "usd"


class TestWhatTheNumberMeans:
    """The declaration is what makes one supplier's `1230` the same money as
    another's `0.00123`. Without it somebody writes the multiplier by hand in a
    repository UBB never sees, which is where "no float enters money arithmetic"
    used to die."""

    def test_a_major_unit_decimal_becomes_micros(self):
        assert to_micros(Decimal("0.00123"),
                         AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL, USD) == 1230

    def test_a_minor_unit_becomes_micros_through_the_currency(self):
        """A cent is ten thousand micros *because the currency says so*.

        The currency parameter is not decorative here for the same reason
        ``core.money`` says it is not decorative there: a helper that assumed a
        hundredth would rebuild the hard-coded `10_000` that module exists to
        have deleted.
        """
        assert to_micros(Decimal("12.5"),
                         AMOUNT_REPRESENTATION_MINOR_UNITS, USD) == 125_000

    def test_micros_are_already_micros(self):
        assert to_micros(1230, AMOUNT_REPRESENTATION_MICROS, USD) == 1230

    def test_zero_is_a_cost(self):
        """A supplier reporting nothing charged is not a supplier reporting
        nothing. A falsy amount that fell out of the arithmetic would be the
        second of those two facts wearing the first's clothes."""
        assert to_micros(Decimal("0.000000"),
                         AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL, USD) == 0

    def test_a_decimal_string_is_read_as_the_decimal_it_spells(self):
        """The preferred wire form: where a supplier's response offers an
        integer or a decimal string, that beats a binary float."""
        assert to_micros("0.1", AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
                         USD) == 100_000

    def test_trailing_zeros_are_not_precision(self):
        """`1.000000000` is one, however a supplier chose to pad it."""
        assert to_micros(Decimal("1.000000000"),
                         AMOUNT_REPRESENTATION_MICROS, USD) == 1

    def test_a_negative_reported_cost_survives_the_conversion(self):
        """A supplier credit is a real thing that arrives on a real response,
        and this module is not the place that decides whether UBB accepts one.
        Refusing the sign here would make that decision invisibly."""
        assert to_micros(Decimal("-0.5"),
                         AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
                         USD) == -500_000

    def test_an_exact_conversion_survives_absurd_length(self):
        """Thirty-four significant digits, exactly representable.

        Decimal's default context carries twenty-eight, so an implementation
        that multiplied through the ambient context would round this and then
        find the rounded product perfectly integral — a wrong answer arriving
        through the very check meant to catch wrong answers.
        """
        amount = Decimal("1234567890123456789012345678.901234")
        assert to_micros(amount, AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
                         USD) == 1234567890123456789012345678901234


class TestOverPrecisionIsRefusedNeverRounded:
    """The rule this module exists for."""

    def test_a_seventh_decimal_place_is_refused(self):
        with pytest.raises(AmountNotRepresentable) as refused:
            to_micros(Decimal("0.0000001"),
                      AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL, USD)

        assert "0.0000001" in str(refused.value)

    def test_a_fractional_micro_is_refused(self):
        with pytest.raises(AmountNotRepresentable):
            to_micros(Decimal("1.5"), AMOUNT_REPRESENTATION_MICROS, USD)

    def test_a_fifth_decimal_place_of_a_minor_unit_is_refused(self):
        """A cent is ten thousand micros, so four places is the boundary."""
        assert to_micros(Decimal("1.0001"),
                         AMOUNT_REPRESENTATION_MINOR_UNITS, USD) == 10_001
        with pytest.raises(AmountNotRepresentable):
            to_micros(Decimal("1.00001"),
                      AMOUNT_REPRESENTATION_MINOR_UNITS, USD)

    def test_an_amount_smaller_than_a_micro_is_refused_rather_than_zeroed(self):
        """The rounding that would be easiest to miss, because its result looks
        like a supplier that charged nothing."""
        with pytest.raises(AmountNotRepresentable):
            to_micros(Decimal("1E-9"),
                      AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL, USD)

    def test_the_refusal_spells_the_amount_out(self):
        """`1E-9` is what `str` gives for a small Decimal, and a tenant reading
        a refusal about their own number should see their own number."""
        with pytest.raises(AmountNotRepresentable) as refused:
            to_micros(Decimal("1E-9"),
                      AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL, USD)

        assert "0.000000001" in str(refused.value)
        assert "1E-9" not in str(refused.value)


class TestWhatIsNotANumber:
    """Refused by name, because each of these has a way of passing a numeric
    test while meaning something else."""

    def test_a_binary_float_is_refused(self):
        """`0.1` is not a tenth in binary, and money arithmetic is the one place
        that difference is not academic. The declaration exists so the builder
        reads the supplier's own text; a float has already lost it."""
        with pytest.raises(AmountNotRepresentable) as refused:
            to_micros(0.1, AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL, USD)

        assert "float" in str(refused.value)

    def test_a_boolean_is_refused(self):
        """`True` is an `int` in Python and passes every numeric test there is."""
        with pytest.raises(AmountNotRepresentable):
            to_micros(True, AMOUNT_REPRESENTATION_MICROS, USD)

    def test_nothing_reported_is_refused(self):
        with pytest.raises(AmountNotRepresentable):
            to_micros(None, AMOUNT_REPRESENTATION_MICROS, USD)

    def test_prose_is_refused(self):
        with pytest.raises(AmountNotRepresentable):
            to_micros("free", AMOUNT_REPRESENTATION_MICROS, USD)

    def test_an_infinity_is_refused(self):
        with pytest.raises(AmountNotRepresentable):
            to_micros(Decimal("Infinity"), AMOUNT_REPRESENTATION_MICROS, USD)

    def test_a_representation_ubb_does_not_own_is_refused(self):
        with pytest.raises(AmountNotRepresentable) as refused:
            to_micros(1, "hundredths_of_a_farthing", USD)

        assert "hundredths_of_a_farthing" in str(refused.value)

    def test_every_declared_representation_converts(self):
        """The vacuity guard for the three tests above it: a fourth
        representation the registry learns is one this module has nothing to say
        about, and it would arrive on a field whose database constraint admits
        it."""
        for representation in sorted(AMOUNT_REPRESENTATION_VALUES):
            assert to_micros(1, representation, USD) > 0


class TestTheCurrencyIsPinnedAndDisagreementFails:
    """v1 is single-currency with no FX. There is no correct conversion to
    perform, so the only two available outcomes are the declared currency and a
    clear failure — and this returns one or raises the other."""

    def test_a_supplier_returning_the_declared_currency_agrees(self):
        assert pin_currency(USD, "usd") == USD

    def test_a_supplier_returning_no_currency_leaves_the_declared_one_standing(self):
        assert pin_currency(USD, None) == USD

    def test_case_and_padding_are_not_disagreement(self):
        """A supplier spelling the ISO code in capitals has not returned a
        different currency. Folding a code's case is canonicalisation; changing
        an amount's meaning is conversion, and only the second is refused."""
        assert pin_currency(USD, " USD ") == USD

    def test_disagreement_is_refused_and_nothing_is_converted(self):
        with pytest.raises(CurrencyDisagreement) as refused:
            pin_currency(USD, "eur")

        message = str(refused.value)
        assert "eur" in message and USD in message

    def test_a_supplier_returned_currency_alone_is_the_pinned_one(self):
        """The second sanctioned way to pin it: no fixed code, a structured path
        instead. There is nothing to disagree with, so the supplier's own answer
        stands."""
        assert pin_currency("", "gbp") == "gbp"

    def test_a_supplier_returned_currency_ubb_cannot_hold_is_refused(self):
        """The failure the path form has and the fixed form does not: nobody
        declared this one, so nothing checked it until now. A currency with no
        known minor unit cannot reach Stripe, and inventing an exponent for it
        is the conversion this whole function refuses to make."""
        with pytest.raises(UnknownCurrency):
            pin_currency("", "jpy")

    def test_no_currency_at_all_is_refused_rather_than_defaulted(self):
        """``core.money`` keeps a platform default for the sites that have no
        tenant in scope, and it is deliberately not reachable from here: a
        reported cost denominated by a default nobody declared is the silent
        reinterpretation this rule is against."""
        with pytest.raises(CurrencyDisagreement):
            pin_currency("", None)
