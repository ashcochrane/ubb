"""The hand-written customer spend pool wrapper (#456): it names the moved
operations, parses through the generated models, and sends the registry's
default enforce mode rather than a literal of its own."""
import unittest
from unittest.mock import patch, MagicMock
from ubb.billing import BillingClient
from ubb._core.models.customer_spend_pool_out import CustomerSpendPoolOut
from ubb._core.models.customer_spend_pool_status_out import CustomerSpendPoolStatusOut
from ubb.vocabulary import (SPEND_POOL_ENFORCE_MODE_ALERT_ONLY,
                            SPEND_POOL_ENFORCE_MODE_BLOCKING)


class CustomerSpendPoolClientTest(unittest.TestCase):
    def setUp(self):
        self.client = BillingClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.billing.httpx.Client.put")
    def test_set_customer_spend_pool(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "cap_micros": 1000, "enforce_mode": SPEND_POOL_ENFORCE_MODE_BLOCKING, "hard_stop_pct": 100,
            "alert_levels": [50, 80, 100, 110], "fail_closed": False})
        cfg = self.client.set_customer_spend_pool("c1", 1000, enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        self.assertIsInstance(cfg, CustomerSpendPoolOut)
        self.assertEqual(cfg.cap_micros, 1000)
        self.assertEqual(mock_put.call_args.args[0], "/api/v1/billing/customers/c1/customer-spend-pool")

    @patch("ubb.billing.httpx.Client.put")
    def test_set_customer_spend_pool_default_enforce_mode_is_the_registry_constant(self, mock_put):
        """The default is the registry's own value, held by reference — never a
        literal the SDK could let drift from the pair the route accepts."""
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "cap_micros": 1000, "enforce_mode": SPEND_POOL_ENFORCE_MODE_ALERT_ONLY, "hard_stop_pct": 100,
            "alert_levels": [], "fail_closed": False})
        self.client.set_customer_spend_pool("c1", 1000)
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body["enforce_mode"], SPEND_POOL_ENFORCE_MODE_ALERT_ONLY)

    @patch("ubb.billing.httpx.Client.put")
    def test_set_customer_spend_pool_with_alert_levels(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "cap_micros": 5000, "enforce_mode": SPEND_POOL_ENFORCE_MODE_ALERT_ONLY, "hard_stop_pct": 90,
            "alert_levels": [50, 75, 90], "fail_closed": True})
        cfg = self.client.set_customer_spend_pool("c2", 5000, hard_stop_pct=90,
                                                  alert_levels=[50, 75, 90], fail_closed=True)
        self.assertIsInstance(cfg, CustomerSpendPoolOut)
        self.assertEqual(cfg.alert_levels, [50, 75, 90])
        self.assertTrue(cfg.fail_closed)
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body["alert_levels"], [50, 75, 90])

    @patch("ubb.billing.httpx.Client.get")
    def test_get_customer_spend_pool(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "cap_micros": 2000, "enforce_mode": SPEND_POOL_ENFORCE_MODE_ALERT_ONLY, "hard_stop_pct": 100,
            "alert_levels": None, "fail_closed": False})
        cfg = self.client.get_customer_spend_pool("c1")
        self.assertIsInstance(cfg, CustomerSpendPoolOut)
        self.assertEqual(cfg.cap_micros, 2000)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/billing/customers/c1/customer-spend-pool")

    @patch("ubb.billing.httpx.Client.get")
    def test_get_customer_spend_pool_status(self, mock_get):
        """The status read's final shape (slice 6 §13): the basis as a pair,
        the assessment over the known figure, the highest threshold reached
        and whether blocking occurred — a transcript of what the route sends."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "period": "2026-06", "cap_micros": 1000,
            "enforce_mode": SPEND_POOL_ENFORCE_MODE_BLOCKING,
            "known_period_charges_micros": 600, "unresolved_posting_count": 1,
            "used_percentage": 60, "remaining_micros": 400,
            "highest_threshold_reached": 50, "blocking_occurred": False})
        s = self.client.get_customer_spend_pool_status("c1")
        self.assertIsInstance(s, CustomerSpendPoolStatusOut)
        self.assertEqual(s.known_period_charges_micros, 600)
        self.assertEqual(s.unresolved_posting_count, 1)
        self.assertEqual(s.used_percentage, 60)
        self.assertEqual(s.remaining_micros, 400)
        self.assertEqual(s.highest_threshold_reached, 50)
        self.assertIs(s.blocking_occurred, False)
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/billing/customers/c1/customer-spend-pool/status")


if __name__ == "__main__":
    unittest.main()
