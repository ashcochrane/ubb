import unittest
from unittest.mock import patch, MagicMock
from ubb.metering import MeteringClient
from ubb._core.models.customer_margin_out import CustomerMarginOut
from ubb._core.models.grouping_field_margin_row import GroupingFieldMarginRow
from ubb._core.models.margin_trend_point_out import MarginTrendPointOut
from ubb._core.models.revenue_profile_out import RevenueProfileOut


class MarginClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.get")
    def test_get_customer_margin(self, mock_get):
        # The full body the endpoint serves (CustomerMarginOut, #98).
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "customer_id": "c1", "external_id": "ext", "revenue_mode": "billed",
            "subscription_revenue_micros": 500_000_000,
            "usage_billed_micros": 1_300_000, "usage_revenue_micros": 1_300_000,
            "provider_cost_micros": 1_000_000, "total_revenue_micros": 501_300_000,
            "gross_margin_micros": 500_300_000, "margin_percentage": 99.8,
            "event_count": 2, "period": {"start": "2026-06-01", "end": "2026-06-09"}})
        m = self.client.get_customer_margin("c1")
        self.assertIsInstance(m, CustomerMarginOut)
        self.assertEqual(m.gross_margin_micros, 500_300_000)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/margin/customers/c1")

    @patch("ubb.metering.httpx.Client.get")
    def test_get_margin_by_dimension(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "period": {}, "rows": [
                {"grouping_field_value": "openai", "provider_cost_micros": 1_000_000,
                 "billed_cost_micros": 1_300_000, "margin_micros": 300_000, "event_count": 2}]})
        rows = self.client.get_margin_by_dimension(provider=True)
        self.assertIsInstance(rows[0], GroupingFieldMarginRow)
        self.assertEqual(rows[0].margin_micros, 300_000)
        # Asserted explicitly because the generated model keeps an unrecognised
        # key in `additional_properties` rather than refusing it: without this
        # line the mock could spell the value property any way it liked, the
        # attribute would be UNSET, and every other assertion here would still
        # pass — a test whose mock agrees with the mistake.
        self.assertEqual(rows[0].grouping_field_value, "openai")
        # DEFECT, PRE-DATING #278 AND LEFT FOR #282, WHICH OWNS THIS METHOD.
        # The line below asserts that the client sends `provider=1`, and the
        # route does not accept it: the breakdown publishes four query
        # parameters — the axis, the open-bag key, and the two date bounds —
        # and the boolean pseudo-flags were deleted long enough ago that #278
        # found their accepted-break entries INERT. Django Ninja ignores an
        # unknown query parameter, so the call returns 200 grouped by the
        # axis parameter's default, which is "provider" — and that is why
        # `provider=True` has always looked correct. `product=True` has not
        # been: it also returns provider-grouped rows, silently.
        # The assertion stays until the method is rebuilt, because deleting it
        # now would remove the only place the wrong request is written down.
        self.assertEqual(mock_get.call_args.kwargs["params"]["provider"], 1)

    @patch("ubb.metering.httpx.Client.get")
    def test_get_margin_trend(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "customer_id": "c1", "points": [
                {"period_start": "2026-05-01", "provider_cost_micros": 100,
                 "usage_billed_micros": 200, "subscription_revenue_micros": 0,
                 "gross_margin_micros": 100, "margin_percentage": 50.0}]})
        pts = self.client.get_margin_trend("c1", periods=3)
        self.assertIsInstance(pts[0], MarginTrendPointOut)
        self.assertEqual(mock_get.call_args.kwargs["params"]["periods"], 3)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/margin/customers/c1/trend")

    @patch("ubb.metering.httpx.Client.put")
    def test_set_customer_revenue(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "recurring_amount_micros": 500_000_000, "interval": "month", "currency": "usd",
            "effective_from": "2026-06-01", "effective_to": None})
        rev = self.client.set_customer_revenue("c1", 500_000_000)
        self.assertIsInstance(rev, RevenueProfileOut)
        self.assertEqual(rev.recurring_amount_micros, 500_000_000)
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body["recurring_amount_micros"], 500_000_000)
        self.assertEqual(mock_put.call_args.args[0], "/api/v1/margin/customers/c1/revenue")

    @patch("ubb.metering.httpx.Client.get")
    def test_get_unprofitable(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "period_start": "2026-06-01", "customers": [{"customer_id": "c1"}]})
        rows = self.client.get_unprofitable_customers()
        self.assertEqual(rows[0]["customer_id"], "c1")


if __name__ == "__main__":
    unittest.main()
