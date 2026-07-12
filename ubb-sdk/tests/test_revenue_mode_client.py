import unittest
from unittest.mock import patch, MagicMock
from ubb.metering import MeteringClient


class RevenueModeClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.put")
    def test_set_revenue_mode(self, mock_put):
        mock_put.return_value = MagicMock(
            status_code=200,
            json=lambda: {"revenue_mode": "metered_only", "resolved": "metered_only"},
        )
        out = self.client.set_revenue_mode("c1", "metered_only")
        self.assertEqual(out["revenue_mode"], "metered_only")
        self.assertEqual(out["resolved"], "metered_only")
        self.assertIn("revenue-mode", mock_put.call_args.args[0])
        self.assertIn("/api/v1/margin/customers/c1/revenue-mode", mock_put.call_args.args[0])

    @patch("ubb.metering.httpx.Client.put")
    def test_set_revenue_mode_body(self, mock_put):
        mock_put.return_value = MagicMock(
            status_code=200,
            json=lambda: {"revenue_mode": "metered_only", "resolved": "metered_only"},
        )
        self.client.set_revenue_mode("c1", "metered_only")
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body["revenue_mode"], "metered_only")

    @patch("ubb.metering.httpx.Client.put")
    def test_set_revenue_mode_default_empty(self, mock_put):
        mock_put.return_value = MagicMock(
            status_code=200,
            json=lambda: {"revenue_mode": "", "resolved": "prepaid"},
        )
        out = self.client.set_revenue_mode("c2")
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body["revenue_mode"], "")
        self.assertEqual(out["resolved"], "prepaid")

    @patch("ubb.metering.httpx.Client.get")
    def test_get_revenue_mode(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"revenue_mode": "metered_only", "resolved": "metered_only"},
        )
        out = self.client.get_revenue_mode("c1")
        self.assertEqual(out["revenue_mode"], "metered_only")
        self.assertEqual(out["resolved"], "metered_only")
        self.assertIn("/api/v1/margin/customers/c1/revenue-mode", mock_get.call_args.args[0])

    @patch("ubb.metering.httpx.Client.get")
    def test_get_revenue_mode_path(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"revenue_mode": "prepaid", "resolved": "prepaid"},
        )
        self.client.get_revenue_mode("cust99")
        path = mock_get.call_args.args[0]
        self.assertEqual(path, "/api/v1/margin/customers/cust99/revenue-mode")


if __name__ == "__main__":
    unittest.main()
