import unittest
from unittest.mock import patch, MagicMock
import httpx
from ubb.metering import MeteringClient
from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)
from ubb.types import RecordUsageResult, UsageEvent, PaginatedResponse


class MeteringClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_test123", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    # ---- record_usage ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_basic(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_1", "new_balance_micros": 8_500_000, "suspended": False,
        })
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r1", idempotency_key="i1",
            provider_cost_micros=1_500_000,
        )
        self.assertIsInstance(result, RecordUsageResult)
        self.assertEqual(result.event_id, "evt_1")
        self.assertEqual(result.new_balance_micros, 8_500_000)
        self.assertFalse(result.suspended)
        self.assertEqual(mock_post.call_args.kwargs["json"]["provider_cost_micros"], 1_500_000)
        # Verify endpoint
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/usage")

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_with_explicit_billed(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_2", "new_balance_micros": 9_000_000, "suspended": False,
            "provider_cost_micros": 500_000, "billed_cost_micros": 1_000_000,
        })
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r2", idempotency_key="i2",
            provider_cost_micros=500_000, billed_cost_micros=1_000_000,
            event_type="chat_completion", provider="openai",
        )
        self.assertIsInstance(result, RecordUsageResult)
        self.assertEqual(result.billed_cost_micros, 1_000_000)
        self.assertEqual(result.provider_cost_micros, 500_000)
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["provider_cost_micros"], 500_000)
        self.assertEqual(body["billed_cost_micros"], 1_000_000)
        # No usage_metrics supplied → must not appear in body
        self.assertNotIn("usage_metrics", body)

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_with_tags(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_3", "new_balance_micros": 7_000_000, "suspended": False,
        })
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r3", idempotency_key="i3",
            provider_cost_micros=1_000_000, tags={"project": "proj_1"},
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["tags"], {"project": "proj_1"})

    # ---- get_usage ----

    @patch("ubb.metering.httpx.Client.get")
    def test_get_usage(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [
                {"id": "e1", "request_id": "r1", "billed_cost_micros": 10000,
                 "metadata": {}, "effective_at": "2025-01-01T00:00:00Z"},
            ],
            "next_cursor": "cur_abc",
            "has_more": True,
        })
        result = self.client.get_usage(customer_id="cust_1")
        self.assertIsInstance(result, PaginatedResponse)
        self.assertEqual(len(result.data), 1)
        self.assertIsInstance(result.data[0], UsageEvent)
        self.assertTrue(result.has_more)
        self.assertEqual(result.next_cursor, "cur_abc")
        # Verify endpoint
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/customers/cust_1/usage")

    @patch("ubb.metering.httpx.Client.get")
    def test_get_usage_with_cursor_and_limit(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        self.client.get_usage(customer_id="cust_1", cursor="cur_xyz", limit=10)
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["params"]["cursor"], "cur_xyz")
        self.assertEqual(call_kwargs.kwargs["params"]["limit"], 10)

    @patch("ubb.metering.httpx.Client.get")
    def test_get_usage_with_tag_filter(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        self.client.get_usage(customer_id="cust_1", tag_key="project", tag_value="proj_1")
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["params"]["tag_key"], "project")
        self.assertEqual(call_kwargs.kwargs["params"]["tag_value"], "proj_1")

    # ---- error handling ----

    @patch("ubb.metering.httpx.Client.post")
    def test_auth_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401)
        with self.assertRaises(UBBAuthError):
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                provider_cost_micros=1000,
            )

    @patch("ubb.metering.httpx.Client.post")
    def test_api_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")
        mock_post.return_value.json.side_effect = Exception("not json")
        with self.assertRaises(UBBAPIError):
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                provider_cost_micros=1000,
            )

    @patch("ubb.metering.httpx.Client.post")
    def test_conflict_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=409, text="Conflict",
            json=lambda: {"error": "duplicate idempotency_key"},
        )
        with self.assertRaises(UBBConflictError):
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                provider_cost_micros=1000,
            )

    @patch("ubb.metering.httpx.Client.post")
    def test_timeout_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("timed out")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                provider_cost_micros=1000,
            )
        self.assertIsNotNone(ctx.exception.original)

    @patch("ubb.metering.httpx.Client.post")
    def test_connect_error_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                provider_cost_micros=1000,
            )
        self.assertIn("Could not connect", str(ctx.exception))

    # ---- context manager ----

    def test_context_manager(self):
        with patch.object(self.client, "close") as mock_close:
            with self.client:
                pass
            mock_close.assert_called_once()

    # ---- close ----

    def test_close(self):
        with patch.object(self.client._http, "close") as mock_close:
            self.client.close()
            mock_close.assert_called_once()

    # ---- record_usage with usage_metrics (no provider_cost_micros) ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_with_usage_metrics_no_cost(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_m1", "new_balance_micros": 9_000_000, "suspended": False,
        })
        result = self.client.record_usage(
            customer_id="c", request_id="r", idempotency_key="i",
            usage_metrics={"input_tokens": 1000},
        )
        self.assertIsInstance(result, RecordUsageResult)
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["usage_metrics"], {"input_tokens": 1000})
        self.assertNotIn("provider_cost_micros", body)

    # ---- record_usage tolerates extra server fields (usage_metrics/provenance/uncosted) ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_full_server_body_with_extra_fields(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False,
            "provider_cost_micros": 2000, "billed_cost_micros": 2000,
            "usage_metrics": {"input_tokens": 1000},
            "pricing_provenance": {"engine_version": "x"},
            "uncosted_metrics": ["foo"],
        })
        res = self.client.record_usage(
            customer_id="c", request_id="r", idempotency_key="i",
            usage_metrics={"input_tokens": 1000},
        )
        self.assertIsInstance(res, RecordUsageResult)
        self.assertEqual(res.provider_cost_micros, 2000)
        self.assertEqual(res.uncosted_metrics, ["foo"])

    # ---- rate-card URL correctness ----

    @patch("ubb.metering.httpx.Client.post")
    def test_create_rate_card_url(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "id": "rc_1", "card_type": "cost", "metric_name": "input_tokens",
            "provider": "", "event_type": "", "dimensions": {},
            "pricing_model": "per_unit", "rate_per_unit_micros": 0,
            "unit_quantity": 1_000_000, "fixed_micros": 0, "currency": "usd",
            "product_id": "", "customer_id": None,
        })
        self.client.create_rate_card(card_type="cost", metric_name="input_tokens")
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/pricing/rate-cards")

    @patch("ubb.metering.httpx.Client.get")
    def test_list_rate_cards_url(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        self.client.list_rate_cards()
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/pricing/rate-cards")

    @patch("ubb.metering.httpx.Client.delete")
    def test_delete_rate_card_url(self, mock_delete):
        mock_delete.return_value = MagicMock(status_code=204, json=lambda: {})
        self.client.delete_rate_card("rc_42")
        call_args = mock_delete.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/pricing/rate-cards/rc_42")

    # ---- usage_analytics ----

    @patch("ubb.metering.httpx.Client.get")
    def test_usage_analytics_url_and_params(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"rows": []})
        result = self.client.usage_analytics(customer_id="c", tag_key="agent")
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/analytics/usage")
        params = call_args.kwargs["params"]
        self.assertEqual(params["customer_id"], "c")
        self.assertEqual(params["tag_key"], "agent")
        self.assertEqual(result, {"rows": []})


if __name__ == "__main__":
    unittest.main()
