import stripe

from apps.subscriptions.stripe.items import (
    MirroredAmount, _period_end, _period_start, _product_name, mirrored_amounts,
    paid_amounts)
from apps.subscriptions.tests._helpers import a_licensed_item, a_stripe_subscription


class TestTheReaderOnAGenuineStripeSubscription:
    """Stage C1a (F-3b): every reader in this module sees the REAL
    ``stripe.Subscription`` — a StripeObject with no ``.get``, nested
    ``items.data[].price.recurring`` StripeObjects, and a ``price.product``
    that is a ``Product`` object only when expanded."""

    def test_amounts_periods_and_the_expanded_product_name_are_read(self):
        sub = a_stripe_subscription("sub_real", "cus_1", "active", items=[
            a_licensed_item(5000, qty=1, product_name="Pro Access"),
            a_licensed_item(800, qty=10, product_name="Seat")])
        assert isinstance(sub, stripe.Subscription) and not hasattr(sub, "get")
        assert isinstance(sub.items.data[0].price.recurring, stripe.StripeObject)
        assert isinstance(sub.items.data[0].price.product, stripe.Product)
        assert mirrored_amounts(sub) == MirroredAmount("usd", 13_000, 130_000_000, 10, "month")
        assert _product_name(sub) == "Pro Access"
        assert _period_start(sub).isoformat() == "2025-02-01T00:00:00+00:00"
        assert _period_end(sub).isoformat() == "2025-03-03T00:00:00+00:00"

    def test_an_unexpanded_product_is_an_id_string_with_no_name(self):
        sub = a_stripe_subscription("sub_unexp", "cus_1", "active",
                                    items=[a_licensed_item(5000, qty=1)])
        assert isinstance(sub.items.data[0].price.product, str)
        assert _product_name(sub) == ""

    def test_a_metered_item_contributes_nothing_on_the_real_object(self):
        sub = a_stripe_subscription("sub_metered", "cus_1", "active", items=[
            a_licensed_item(5000, qty=1, product_name="Pro"),
            a_licensed_item(999, qty=1, usage_type="metered")])
        assert mirrored_amounts(sub) == MirroredAmount("usd", 5_000, 50_000_000, 1, "month")

    def test_a_foreign_real_subscription_is_kept_and_not_relabelled(self):
        sub = a_stripe_subscription("sub_eur", "cus_1", "active", currency="eur",
                                    items=[a_licensed_item(4900, qty=1, product_name="Pro")])
        assert mirrored_amounts(sub) == MirroredAmount("eur", 4_900, None, 1, "month")

    def test_a_real_subscription_with_no_items_reads_as_empty(self):
        sub = stripe.Subscription.construct_from(
            {"id": "sub_bare", "object": "subscription", "status": "active",
             "currency": "usd"}, "sk_test_sentinel")
        assert mirrored_amounts(sub) == MirroredAmount("usd", 0, 0, 1, "month")
        assert _product_name(sub) == ""
        assert _period_start(sub) is None and _period_end(sub) is None


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
