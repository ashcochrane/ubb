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

    # `unresolved_event_count` is required on the row (#327): the supplier cost
    # a margin is taken against can be one UBB has not resolved, and a row that
    # did not say so would report a ceiling on a margin as a margin. One here,
    # so the fixture is a row of the kind that needs the field rather than a row
    # that merely carries it.
    ROWS = {"period": {}, "rows": [
        {"grouping_field_value": "openai", "provider_cost_micros": 1_000_000,
         "unresolved_event_count": 1,
         "billed_cost_micros": 1_300_000, "margin_micros": 300_000,
         "event_count": 2}]}

    @patch("ubb.metering.httpx.Client.get")
    def test_get_margin_by_grouping_field(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self.ROWS)
        rows = self.client.get_margin_by_grouping_field()
        self.assertIsInstance(rows[0], GroupingFieldMarginRow)
        self.assertEqual(rows[0].margin_micros, 300_000)
        # Asserted explicitly because the generated model keeps an unrecognised
        # key in `additional_properties` rather than refusing it: without this
        # line the mock could spell the value property any way it liked, the
        # attribute would be UNSET, and every other assertion here would still
        # pass — a test whose mock agrees with the mistake.
        self.assertEqual(rows[0].grouping_field_value, "openai")
        # The completeness reaches a typed attribute, not the untyped bag —
        # which is the whole reason the row declares it rather than letting it
        # arrive: a caller must be able to see that this margin is a ceiling.
        self.assertEqual(rows[0].unresolved_event_count, 1)

    @patch("ubb.metering.httpx.Client.get")
    def test_the_request_carries_the_axis_and_nothing_the_route_would_drop(
            self, mock_get):
        """The whole params dict, not one key of it — and this is the point.

        THE DEFECT THIS REPLACES, recorded by #278 and left for the ticket that
        owns this method. The method used to take `provider: bool` and
        `product: bool` and send them as `provider=1` / `product=1`. The route
        publishes no such parameters — its four are the axis, the open-bag key
        and the two date bounds — and Django Ninja DROPS an unknown query
        parameter rather than refusing it. So `product=True` returned rows
        grouped by the axis parameter's default, which is `provider`, and had
        always done so: a wrong request that answered 200 with plausible,
        wrong data. `provider=True` looked right for the same reason it was
        never doing anything.

        Asserting the dict WHOLE is what makes that unrepeatable. A per-key
        assertion passes while a pseudo-flag rides along beside it, which is
        exactly how the old one stayed green.
        """
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self.ROWS)
        self.client.get_margin_by_grouping_field(group_by="event_type")
        self.assertEqual(mock_get.call_args.kwargs["params"],
                         {"group_by": "event_type"})

    @patch("ubb.metering.httpx.Client.get")
    def test_a_declared_grouping_field_key_is_an_axis_like_any_other(self, mock_get):
        """A tenant's own declared key goes on the wire unchanged.

        The route resolves the four built-in axes itself and looks anything
        else up in the tenant's declared slots, answering 422 for a key it
        does not know. The client does not second-guess that: a client holding
        its own list of valid axes would refuse a key the tenant declared
        after the client was pinned.
        """
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self.ROWS)
        self.client.get_margin_by_grouping_field(group_by="model",
                                                 start_date="2026-06-01",
                                                 end_date="2026-06-30")
        self.assertEqual(mock_get.call_args.kwargs["params"],
                         {"group_by": "model", "start_date": "2026-06-01",
                          "end_date": "2026-06-30"})

    # THE OPEN-BAG GROUPING PARAMETER IS DELIBERATELY NOT EXERCISED HERE, and
    # the reason is a gate rather than an oversight. Its name is a retired term
    # whose ledger entry belongs to a later slice and records the exact set of
    # files it may appear in; this file is not one of them, and a test written
    # to cover it fails the sweep with `term_spread` — the word reaching
    # further while the debt stands. The parameter is unchanged by this ticket
    # (it took the same keyword before the rebuild and still does), so nothing
    # this commit alters goes uncovered. It joins these assertions in the
    # commit that renames it.

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
