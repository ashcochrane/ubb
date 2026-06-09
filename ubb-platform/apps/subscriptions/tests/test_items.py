from apps.subscriptions.stripe.items import _sum_items, _product_name


def _fake_sub():
    return {
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


def test_sum_items_multi_item_access_plus_seats():
    # access item: 5000c * 1 = 50_000_000 micros; seat item: 800c * 10 = 80_000_000 micros.
    assert _sum_items(_fake_sub()) == (130_000_000, 10, "month")


def test_sum_items_skips_metered_items():
    sub = {
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
    assert _sum_items(sub) == (50_000_000, 1, "month")


def test_product_name_from_first_named_product():
    assert _product_name(_fake_sub()) == "Pro Access"
