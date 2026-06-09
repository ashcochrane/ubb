import unittest
from unittest.mock import patch, MagicMock
from ubb.metering import MeteringClient

BUSINESS_MARGIN_FIXTURE = {
    "business_id": "00000000-0000-0000-0000-000000000001",
    "external_id": "biz",
    "totals": {
        "subscription_revenue_micros": 0,
        "usage_revenue_micros": 0,
        "provider_cost_micros": 300_000,
        "total_revenue_micros": 0,
        "gross_margin_micros": 500_000,
        "event_count": 2,
    },
    "seats": [
        {
            "customer_id": "00000000-0000-0000-0000-000000000002",
            "revenue_mode": "metered_only",
            "subscription_revenue_micros": 0,
            "usage_billed_micros": 500_000,
            "usage_revenue_micros": 0,
            "provider_cost_micros": 200_000,
            "total_revenue_micros": 0,
            "gross_margin_micros": 300_000,
            "margin_percentage": 0.0,
            "event_count": 1,
        },
        {
            "customer_id": "00000000-0000-0000-0000-000000000003",
            "revenue_mode": "metered_only",
            "subscription_revenue_micros": 0,
            "usage_billed_micros": 300_000,
            "usage_revenue_micros": 0,
            "provider_cost_micros": 100_000,
            "total_revenue_micros": 0,
            "gross_margin_micros": 200_000,
            "margin_percentage": 0.0,
            "event_count": 1,
        },
    ],
}


class BusinessMarginClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.get")
    def test_get_business_margin(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: BUSINESS_MARGIN_FIXTURE)
        result = self.client.get_business_margin("biz")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["external_id"], "biz")
        self.assertEqual(result["totals"]["gross_margin_micros"], 500_000)
        self.assertEqual(len(result["seats"]), 2)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/margin/business/biz")

    @patch("ubb.metering.httpx.Client.get")
    def test_get_business_margin_with_dates(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: BUSINESS_MARGIN_FIXTURE)
        self.client.get_business_margin("biz", start_date="2026-06-01", end_date="2026-07-01")
        params = mock_get.call_args.kwargs.get("params") or {}
        self.assertEqual(params.get("start_date"), "2026-06-01")
        self.assertEqual(params.get("end_date"), "2026-07-01")
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/margin/business/biz")


if __name__ == "__main__":
    unittest.main()
