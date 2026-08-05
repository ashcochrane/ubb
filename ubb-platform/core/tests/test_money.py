"""Unit tests for core.money — the minor unit and the four rounding rules.

These pin *invariants*, not golden values. A golden value would only re-state
the arithmetic; an invariant survives a currency being admitted, and fails the
moment a caller drops a remainder or a ceiling rounds the wrong way.

The one deliberate exception is
``TestSupportedCurrencies::test_every_admitted_currency_is_two_decimal``, which
pins today's table so that admitting a zero-decimal currency has to be a
conscious edit to this file rather than a silent behaviour change across the
twenty sites that used to hard-code the multiplier.
"""
import pytest

from core.money import (
    DEFAULT_CURRENCY,
    MICROS_PER_UNIT,
    SUPPORTED_CURRENCIES,
    MisalignedAmount,
    UnknownCurrency,
    assert_aligned,
    from_minor,
    minor_units,
    round_ceiling,
    round_charge,
    to_minor,
)

# A spread that covers zero, sub-minor-unit dust, exact boundaries, one-micro
# either side of a boundary, and a value far larger than any real invoice.
AMOUNTS = [
    0, 1, 9_999, 10_000, 10_001, 19_999, 1_000_000, 1_234_567,
    999_999_999_999, 9_223_372_036_854_775_000,
]


class TestMinorUnits:
    def test_returns_micros_per_minor_unit(self):
        # The multiplier the twenty sites used to hard-code.
        assert minor_units("usd") == 10_000

    def test_is_case_insensitive(self):
        assert minor_units("USD") == minor_units("usd") == minor_units("Usd")

    def test_unknown_currency_is_refused(self):
        with pytest.raises(UnknownCurrency):
            minor_units("jpy")

    def test_empty_currency_is_refused(self):
        # No silent fallback: a caller with no currency in hand must say which
        # one it means, or the bug hides until a second currency is admitted.
        for missing in ("", None):
            with pytest.raises(UnknownCurrency):
                minor_units(missing)

    def test_derives_from_the_exponent_table(self, monkeypatch):
        """Admitting a currency is a data change — this is the ticket's claim.

        A zero-decimal currency's minor unit IS the whole unit, so one minor
        unit is a million micros. Nothing but the table decides that.
        """
        from core import money

        monkeypatch.setitem(money._MINOR_UNIT_EXPONENT, "jpy", 0)
        assert minor_units("jpy") == MICROS_PER_UNIT

        monkeypatch.setitem(money._MINOR_UNIT_EXPONENT, "kwd", 3)
        assert minor_units("kwd") == 1_000


class TestToMinor:
    @pytest.mark.parametrize("amount", AMOUNTS)
    def test_reassembly_is_exact(self, amount):
        """minor * multiplier + remainder == the amount we started with.

        This is R3: the remainder is carried, never lost. A conversion that
        cannot be reassembled has dropped money.
        """
        minor, remainder = to_minor(amount, "usd")
        assert minor * minor_units("usd") + remainder == amount

    @pytest.mark.parametrize("amount", AMOUNTS)
    def test_remainder_is_always_in_range(self, amount):
        """0 <= remainder < one minor unit — anything else is a carry bug."""
        _, remainder = to_minor(amount, "usd")
        assert 0 <= remainder < minor_units("usd")

    def test_floors_rather_than_rounds(self):
        """The minor amount never exceeds the exact value (R3 floors)."""
        for amount in AMOUNTS:
            minor, _ = to_minor(amount, "usd")
            assert minor * minor_units("usd") <= amount

    def test_returns_the_remainder_rather_than_hiding_it(self):
        """A caller that ignores the carry has to write the code that does so."""
        result = to_minor(19_999, "usd")
        assert isinstance(result, tuple) and len(result) == 2
        assert result == (1, 9_999)

    def test_negative_amounts_keep_both_invariants(self):
        """Reassembly and remainder-range hold below zero too (refund paths)."""
        for amount in (-1, -9_999, -10_000, -10_001):
            minor, remainder = to_minor(amount, "usd")
            assert minor * minor_units("usd") + remainder == amount
            assert 0 <= remainder < minor_units("usd")

    def test_unknown_currency_is_refused(self):
        with pytest.raises(UnknownCurrency):
            to_minor(10_000, "jpy")


class TestFromMinor:
    def test_is_exact(self):
        for minor in (0, 1, 150, 999_999):
            assert from_minor(minor, "usd") == minor * minor_units("usd")

    @pytest.mark.parametrize("minor", [0, 1, 150, 999_999])
    def test_round_trips_with_no_remainder(self, minor):
        """An amount that came from a minor unit is aligned by construction."""
        assert to_minor(from_minor(minor, "usd"), "usd") == (minor, 0)

    def test_unknown_currency_is_refused(self):
        with pytest.raises(UnknownCurrency):
            from_minor(1, "jpy")


class TestAssertAligned:
    def test_accepts_whole_minor_units(self):
        for minor in (0, 1, 150, 999_999):
            assert assert_aligned(from_minor(minor, "usd"), "usd") is None

    def test_refuses_a_remainder(self):
        for amount in (1, 9_999, 10_001, 19_999):
            with pytest.raises(MisalignedAmount):
                assert_aligned(amount, "usd")

    def test_refusal_names_the_amount(self):
        with pytest.raises(MisalignedAmount) as exc:
            assert_aligned(1_500_001, "usd")
        assert "1500001" in str(exc.value).replace("_", "")

    def test_is_exactly_the_zero_remainder_condition(self):
        """The assertion and the conversion agree — it proves the carry ran."""
        for amount in AMOUNTS:
            _, remainder = to_minor(amount, "usd")
            if remainder == 0:
                assert assert_aligned(amount, "usd") is None
            else:
                with pytest.raises(MisalignedAmount):
                    assert_aligned(amount, "usd")

    def test_unknown_currency_is_refused(self):
        with pytest.raises(UnknownCurrency):
            assert_aligned(10_000, "jpy")


# (numerator, denominator) pairs spanning below-half, exact-half and above-half
# for both odd and even denominators.
RATIOS = [
    (0, 3), (1, 3), (2, 3), (3, 3),
    (0, 4), (1, 4), (2, 4), (3, 4), (5, 4), (6, 4), (7, 4),
    (49, 100), (50, 100), (51, 100), (150, 100),
    (1_499_999, 1_000_000), (1_500_000, 1_000_000), (1_500_001, 1_000_000),
]


class TestRoundCharge:
    def test_exact_half_rounds_up(self):
        """Half-up: the tie goes to the charge (R4)."""
        assert round_charge(1, 2) == 1
        assert round_charge(50, 100) == 1
        assert round_charge(150, 100) == 2

    def test_below_half_rounds_down(self):
        assert round_charge(49, 100) == 0
        assert round_charge(1_499_999, 1_000_000) == 1

    def test_exact_values_are_untouched(self):
        for n in (0, 1, 7, 1_000_000):
            assert round_charge(n * 13, 13) == n

    @pytest.mark.parametrize("numerator,denominator", RATIOS)
    def test_never_off_by_more_than_half(self, numerator, denominator):
        """|result*d - n| <= d/2 — the defining property of nearest-rounding."""
        result = round_charge(numerator, denominator)
        assert abs(result * denominator - numerator) * 2 <= denominator

    def test_matches_the_arithmetic_it_replaces(self):
        """The markup and rate-card sites are re-expressed, not re-decided."""
        for cost, pct in ((1_234_567, 15_000_000), (999, 1), (0, 50_000_000)):
            assert round_charge(cost * pct, 100_000_000) == (
                cost * pct + 50_000_000) // 100_000_000
        for units, rate, quantity in ((7, 333, 1_000_000), (1, 1, 3), (99, 101, 10)):
            assert round_charge(units * rate, quantity) == (
                units * rate + quantity // 2) // quantity

    def test_non_positive_denominator_is_refused(self):
        for denominator in (0, -1):
            with pytest.raises(ValueError):
                round_charge(100, denominator)


class TestRoundCeiling:
    @pytest.mark.parametrize("numerator,denominator", RATIOS)
    def test_never_rounds_up(self, numerator, denominator):
        """A percentage-derived ceiling binds no later than the declared value.

        This is the one direction a spend control must never err (R4): a
        ceiling that rounded up would let a job burn more than the tenant said.
        """
        assert round_ceiling(numerator, denominator) * denominator <= numerator

    @pytest.mark.parametrize("numerator,denominator", RATIOS)
    def test_is_never_above_the_charge_rounding(self, numerator, denominator):
        """The two rules differ only in the direction of the tie."""
        assert round_ceiling(numerator, denominator) <= round_charge(
            numerator, denominator)

    def test_exact_half_rounds_down(self):
        assert round_ceiling(1, 2) == 0
        assert round_ceiling(50, 100) == 0
        assert round_ceiling(150, 100) == 1

    def test_exact_values_are_untouched(self):
        for n in (0, 1, 7, 1_000_000):
            assert round_ceiling(n * 13, 13) == n

    def test_non_positive_denominator_is_refused(self):
        for denominator in (0, -1):
            with pytest.raises(ValueError):
                round_ceiling(100, denominator)


class TestSupportedCurrencies:
    def test_the_table_is_unchanged_by_the_relocation(self):
        """CUR-1's eighteen currencies moved house; none were admitted or dropped."""
        assert SUPPORTED_CURRENCIES == frozenset({
            "usd", "eur", "gbp", "aud", "cad", "chf", "nzd", "sgd", "hkd",
            "sek", "nok", "dkk", "pln", "czk", "mxn", "brl", "inr", "zar",
        })

    def test_every_admitted_currency_is_two_decimal(self):
        """Why every routed site is byte-identical to the literal it replaced.

        Admitting a currency with a different minor unit is a real behaviour
        change at twenty sites; it must break this test on the way in.
        """
        for currency in SUPPORTED_CURRENCIES:
            assert minor_units(currency) == 10_000

    def test_default_currency_is_admitted(self):
        assert DEFAULT_CURRENCY in SUPPORTED_CURRENCIES

    def test_the_table_and_the_multiplier_agree(self):
        """One table, one place: nothing is supported without a minor unit."""
        from core import money

        assert SUPPORTED_CURRENCIES == frozenset(money._MINOR_UNIT_EXPONENT)
