"""The margin calls this client still has, and the ones it must not grow back.

⚠ **FIVE CASES FOR THREE METHODS WERE HERE AND ARE GONE (#501)** — one
customer's margin, the grouped breakdown with its axis and declared-key cases,
and the trend. They called routes that no longer exist, and the surface that
replaced all three is one economic query named by MEASURES and AXES rather than
by a route. The ergonomic handle for it is a later ticket's; until then the
operation is reachable through the generated client with a `generated_only`
disposition recorded for it, which is the same shape the supplied-revenue pair
has carried since #495.
"""
import unittest
from unittest.mock import patch, MagicMock

from ubb.client import UBBClient
from ubb.metering import MeteringClient


class MarginClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    #: Every margin call removed from this client with its route, and the
    #: ticket that took it. Read as one list because the failure mode is
    #: identical for all of them: a method that quietly comes back is a call
    #: whose route answers 404.
    REMOVED = {
        "set_customer_revenue": "#496 — the recurring revenue pair",
        "get_customer_revenue": "#496 — the recurring revenue pair",
        "get_customer_margin": "#501 — one customer's margin",
        "get_margin_by_grouping_field": "#501 — the grouped margin breakdown",
        "get_margin_trend": "#501 — one customer's margin trend",
        "usage_analytics": "#501 — the usage analytics report",
        "usage_timeseries": "#501 — its timeseries sibling",
    }

    def test_no_removed_margin_call_is_still_on_the_client(self):
        """`hasattr` is the only thing that fails when a method comes back."""
        for name, why in self.REMOVED.items():
            with self.subTest(name):
                self.assertFalse(hasattr(self.client, name), why)

    def test_and_none_of_them_is_still_on_the_facade_either(self):
        """⚠ **THE HALF THAT WAS MISSING, AND IT HAD ALREADY BITTEN.**

        `UBBClient` forwards to the product clients, and its two delegates for
        the recurring revenue pair OUTLIVED the methods they forwarded to: #496
        removed those and left these, so calling either raised `AttributeError`
        from inside the client rather than answering anything. A facade that
        forwards to nothing looks callable, which is worse than one that does
        not forward at all — and the case above could not see it, because it
        asks the wrong object.

        Found while removing three more of the same shape (#501), which is why
        the assertion is over the same list rather than beside it.
        """
        for name, why in self.REMOVED.items():
            with self.subTest(name):
                self.assertFalse(hasattr(UBBClient, name), why)

    @patch("ubb.metering.httpx.Client.get")
    def test_get_unprofitable(self, mock_get):
        """The alerting read, which keeps its own contract (slice 7 §8, §14):
        it counts customers a threshold rule has NAMED rather than deriving
        anything from a margin figure."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "period_start": "2026-06-01", "customers": [{"customer_id": "c1"}]})
        rows = self.client.get_unprofitable_customers()
        self.assertEqual(rows[0]["customer_id"], "c1")

    def test_the_alerting_read_is_still_on_the_facade(self):
        """The vacuity guard on the two absence cases above.

        They assert that seven names are missing from two objects. A facade
        that had lost every margin call — or a typo'd import leaving `UBBClient`
        as something else entirely — would satisfy both and mean nothing.
        """
        self.assertTrue(hasattr(UBBClient, "get_unprofitable_customers"))
        self.assertTrue(hasattr(self.client, "get_unprofitable_customers"))


if __name__ == "__main__":
    unittest.main()
