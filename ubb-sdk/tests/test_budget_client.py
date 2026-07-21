import unittest
from unittest.mock import patch, MagicMock
from ubb.billing import BillingClient
from ubb._core.models.budget_config_out import BudgetConfigOut
from ubb._core.models.budget_status_out import BudgetStatusOut


class BudgetClientTest(unittest.TestCase):
    def setUp(self):
        self.client = BillingClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.billing.httpx.Client.put")
    def test_set_budget(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "cap_micros": 1000, "enforce_mode": "enforcing", "hard_stop_pct": 100,
            "alert_levels": [50, 80, 100, 110], "fail_closed": False})
        cfg = self.client.set_budget("c1", 1000, enforce_mode="enforcing")
        self.assertIsInstance(cfg, BudgetConfigOut)
        self.assertEqual(cfg.cap_micros, 1000)
        self.assertEqual(mock_put.call_args.args[0], "/api/v1/billing/customers/c1/budget")

    @patch("ubb.billing.httpx.Client.put")
    def test_set_budget_with_alert_levels(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "cap_micros": 5000, "enforce_mode": "advisory", "hard_stop_pct": 90,
            "alert_levels": [50, 75, 90], "fail_closed": True})
        cfg = self.client.set_budget("c2", 5000, hard_stop_pct=90,
                                     alert_levels=[50, 75, 90], fail_closed=True)
        self.assertIsInstance(cfg, BudgetConfigOut)
        self.assertEqual(cfg.alert_levels, [50, 75, 90])
        self.assertTrue(cfg.fail_closed)
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body["alert_levels"], [50, 75, 90])

    @patch("ubb.billing.httpx.Client.get")
    def test_get_budget(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "cap_micros": 2000, "enforce_mode": "advisory", "hard_stop_pct": 100,
            "alert_levels": None, "fail_closed": False})
        cfg = self.client.get_budget("c1")
        self.assertIsInstance(cfg, BudgetConfigOut)
        self.assertEqual(cfg.cap_micros, 2000)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/billing/customers/c1/budget")

    @patch("ubb.billing.httpx.Client.get")
    def test_get_budget_status(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "period": "2026-06", "spend_micros": 600, "cap_micros": 1000, "pct": 60.0,
            "enforce_mode": "advisory"})
        s = self.client.get_budget_status("c1")
        self.assertIsInstance(s, BudgetStatusOut)
        self.assertEqual(s.pct, 60.0)
        self.assertEqual(s.spend_micros, 600)
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/billing/customers/c1/budget/status")


if __name__ == "__main__":
    unittest.main()
