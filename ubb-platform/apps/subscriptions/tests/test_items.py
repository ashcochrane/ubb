from apps.subscriptions.stripe.items import (
    MirroredAmount, _product_name, mirrored_amounts, paid_amounts)


def _fake_sub(currency="usd"):
    return {
        "currency": currency,
        "items": {
            "data": [
                {
                    "price": {
                        "unit_amount": 5000,
                        "recurring": {"interval": "month", "usage_type": "licensed"},
                        "product": {"name": "Pro Access"},
                    },
                    "quantity": 1,
                },
                {
                    "price": {
                        "unit_amount": 800,
                        "recurring": {"interval": "month", "usage_type": "licensed"},
                    },
                    "quantity": 10,
                },
            ]
        }
    }


def test_mirrored_amounts_sum_access_plus_seats():
    # access item: 5000c * 1; seat item: 800c * 10 — Stripe's integers summed,
    # and in dollars that is 130_000_000 micros.
    assert mirrored_amounts(_fake_sub()) == MirroredAmount(
        "usd", 13_000, 130_000_000, 10, "month")


def test_a_foreign_subscription_keeps_stripes_integer_and_has_no_dollar_amount():
    """#564: never scaled by anybody's minor unit, never relabelled."""
    assert mirrored_amounts(_fake_sub("eur")) == MirroredAmount(
        "eur", 13_000, None, 10, "month")


def test_a_currency_core_money_cannot_represent_is_kept_too():
    assert mirrored_amounts(_fake_sub(" JPY "))[:3] == ("jpy", 13_000, None)


def test_a_subscription_naming_no_currency_is_not_assumed_to_be_dollars():
    sub = _fake_sub()
    del sub["currency"]
    assert mirrored_amounts(sub)[:3] == ("", 13_000, None)


def test_an_invoice_reads_the_same_way():
    from types import SimpleNamespace
    assert paid_amounts(SimpleNamespace(currency="usd", amount_paid=4_900)) == (
        "usd", 4_900, 49_000_000)
    assert paid_amounts(SimpleNamespace(currency="eur", amount_paid=4_900)) == (
        "eur", 4_900, None)


def test_mirrored_amounts_skip_metered_items():
    sub = {
        "currency": "usd",
        "items": {
            "data": [
                {"price": {"unit_amount": 5000,
                           "recurring": {"interval": "month", "usage_type": "licensed"},
                           "product": {"name": "Pro"}}, "quantity": 1},
                {"price": {"unit_amount": 999,
                           "recurring": {"interval": "month", "usage_type": "metered"}},
                 "quantity": 1},
            ]
        }
    }
    # metered item contributes 0 (its revenue arrives as InvoiceItems).
    assert mirrored_amounts(sub) == MirroredAmount(
        "usd", 5_000, 50_000_000, 1, "month")


def test_product_name_from_first_named_product():
    assert _product_name(_fake_sub()) == "Pro Access"
