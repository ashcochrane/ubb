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
    def test_record_usage_with_cost_micros(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_1", "new_balance_micros": 8_500_000, "suspended": False,
        })
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r1", idempotency_key="i1",
            cost_micros=1_500_000,
        )
        self.assertIsInstance(result, RecordUsageResult)
        self.assertEqual(result.event_id, "evt_1")
        self.assertEqual(result.new_balance_micros, 8_500_000)
        self.assertFalse(result.suspended)
        # Verify endpoint
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/usage")

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_with_usage_metrics(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_2", "new_balance_micros": 9_000_000, "suspended": False,
            "provider_cost_micros": 500_000, "billed_cost_micros": 1_000_000,
        })
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r2", idempotency_key="i2",
            event_type="chat_completion", provider="openai",
            usage_metrics={"input_tokens": 100, "output_tokens": 50},
            properties={"model": "gpt-4"},
        )
        self.assertIsInstance(result, RecordUsageResult)
        self.assertEqual(result.billed_cost_micros, 1_000_000)
        self.assertEqual(result.provider_cost_micros, 500_000)

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_with_group_keys(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_3", "new_balance_micros": 7_000_000, "suspended": False,
        })
        result = self.client.record_usage(
            customer_id="cust_1", request_id="r3", idempotency_key="i3",
            cost_micros=1_000_000, group_keys={"project": "proj_1"},
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["group_keys"], {"project": "proj_1"})

    # ---- get_usage ----

    @patch("ubb.metering.httpx.Client.get")
    def test_get_usage(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [
                {"id": "e1", "request_id": "r1", "cost_micros": 10000,
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
    def test_get_usage_with_group_filter(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        self.client.get_usage(customer_id="cust_1", group_key="project", group_value="proj_1")
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["params"]["group_key"], "project")
        self.assertEqual(call_kwargs.kwargs["params"]["group_value"], "proj_1")

    # ---- error handling ----

    @patch("ubb.metering.httpx.Client.post")
    def test_auth_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401)
        with self.assertRaises(UBBAuthError):
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                cost_micros=1000,
            )

    @patch("ubb.metering.httpx.Client.post")
    def test_api_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")
        mock_post.return_value.json.side_effect = Exception("not json")
        with self.assertRaises(UBBAPIError):
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                cost_micros=1000,
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
                cost_micros=1000,
            )

    @patch("ubb.metering.httpx.Client.post")
    def test_timeout_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("timed out")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                cost_micros=1000,
            )
        self.assertIsNotNone(ctx.exception.original)

    @patch("ubb.metering.httpx.Client.post")
    def test_connect_error_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.record_usage(
                customer_id="c1", request_id="r1", idempotency_key="i1",
                cost_micros=1000,
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


if __name__ == "__main__":
    unittest.main()
