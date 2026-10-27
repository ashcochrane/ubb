"""The one currency policy, asked directly (ADR-0023, #555).

Every door that admits money asks :func:`core.currency_policy.admit_currency`,
and the route tests prove each door asks it. This module proves what it
answers, and that the policy is a policy OVER the representation table and
never a shrinking of it (the owner's amendment A of 2026-10-26).
"""

import pytest
from django.db import models

from core import currency_policy, money
from core.currency_policy import (
    ECONOMIC_CURRENCY,
    UNSUPPORTED_CURRENCY,
    UnsupportedCurrency,
    admit_currency,
    is_admitted,
    usd_only_check,
)
from core.problems import PROBLEMS, VERDICTS


@pytest.mark.parametrize("spelled", ["usd", "USD", " Usd ", "usd\n"])
def test_us_dollars_in_any_spelling_are_admitted_in_the_stored_one(spelled):
    assert is_admitted(spelled)
    assert admit_currency(spelled) == "usd"


@pytest.mark.parametrize("offered", [
    "eur",   # represented (`core.money` knows its minor unit) and NOT admitted
    "jpy",   # neither represented nor admitted
    "usdx", "us", "", "   ", None, 840, ["usd"],
])
def test_anything_else_is_refused_by_name(offered):
    assert not is_admitted(offered)
    with pytest.raises(UnsupportedCurrency, match="UBB v1 admits US dollars only"):
        admit_currency(offered)


def test_the_refusal_is_the_catalogues_existing_code_on_every_route():
    """The single route raises it as a problem, and a batch item reports it as
    its verdict — so it is in both lists, never a second code for one rule."""
    assert UnsupportedCurrency.code == UNSUPPORTED_CURRENCY
    assert PROBLEMS[UNSUPPORTED_CURRENCY]["status"] == 422
    assert UNSUPPORTED_CURRENCY in VERDICTS["ingest_rejections"]


def test_the_refusal_is_a_value_error():
    """So every recording path that already maps a `ValueError` to a refusal
    refuses it rather than answering 500 — the error map names it ahead of the
    generic branch to give it its own code."""
    assert issubclass(UnsupportedCurrency, ValueError)


def test_the_policy_is_over_the_representation_table_never_in_place_of_it():
    """Amendment A: the minor-unit table keeps every currency it knows, because
    a foreign source fact still needs its exponent read honestly. The policy
    admits one of them."""
    assert ECONOMIC_CURRENCY in money.SUPPORTED_CURRENCIES
    assert len(money.SUPPORTED_CURRENCIES) > 1
    assert money.DEFAULT_CURRENCY == ECONOMIC_CURRENCY


def test_the_policy_reads_no_table():
    """Admission is not "the table knows it": `eur` is represented and refused.
    A policy that consulted the table would admit it."""
    assert "eur" in money.SUPPORTED_CURRENCIES
    assert not is_admitted("eur")
    assert "SUPPORTED_CURRENCIES" not in vars(currency_policy)


def test_the_database_check_names_the_one_currency():
    check = usd_only_check("currency", "ck_x")
    assert isinstance(check, models.CheckConstraint)
    assert check.name == "ck_x"
    assert check.condition == models.Q(currency="usd")


def test_a_blank_admitting_check_admits_the_empty_string_and_nothing_else():
    check = usd_only_check("currency", "ck_x", or_blank=True)
    assert check.condition == models.Q(currency="usd") | models.Q(currency="")
