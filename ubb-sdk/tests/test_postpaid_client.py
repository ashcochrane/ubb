import unittest
from unittest.mock import patch, MagicMock
from ubb.billing import BillingClient
from ubb.types import UsageInvoice


class PostpaidClientTest(unittest.TestCase):
    def setUp(self):
        self.client = BillingClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.billing.httpx.Client.get")
    def test_get_usage_invoices(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [
            {"period_start": "2026-06-01", "period_end": "2026-07-01", "total_billed_micros": 1000,
             "currency": "usd", "status": "pushed", "stripe_invoice_id": "in_1", "skip_reason": ""}])
        rows = self.client.get_usage_invoices("c1")
        self.assertIsInstance(rows[0], UsageInvoice)
        self.assertEqual(rows[0].total_billed_micros, 1000)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/billing/customers/c1/usage-invoices")

    @patch("ubb.billing.httpx.Client.get")
    def test_get_usage_invoices_returns_list(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [
            {"period_start": "2026-05-01", "period_end": "2026-06-01", "total_billed_micros": 500,
             "currency": "usd", "status": "skipped", "stripe_invoice_id": None, "skip_reason": "below_threshold"},
            {"period_start": "2026-06-01", "period_end": "2026-07-01", "total_billed_micros": 2000,
             "currency": "usd", "status": "pushed", "stripe_invoice_id": "in_2", "skip_reason": ""},
        ])
        rows = self.client.get_usage_invoices("c2")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].status, "skipped")
        self.assertEqual(rows[0].skip_reason, "below_threshold")
        self.assertEqual(rows[1].stripe_invoice_id, "in_2")

    @patch("ubb.billing.httpx.Client.get")
    def test_get_postpaid_config(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"usage_line_item_group_by": "product_id"})
        out = self.client.get_postpaid_config()
        self.assertEqual(out, "product_id")
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/billing/postpaid-config")

    @patch("ubb.billing.httpx.Client.put")
    def test_set_postpaid_config(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {"usage_line_item_group_by": "product_id"})
        out = self.client.set_postpaid_config("product_id")
        self.assertEqual(out, "product_id")
        self.assertEqual(mock_put.call_args.args[0], "/api/v1/billing/postpaid-config")

    @patch("ubb.billing.httpx.Client.put")
    def test_set_postpaid_config_empty(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {"usage_line_item_group_by": ""})
        out = self.client.set_postpaid_config()
        self.assertEqual(out, "")
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body["usage_line_item_group_by"], "")


if __name__ == "__main__":
    unittest.main()
