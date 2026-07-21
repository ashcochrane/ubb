"""#41 past-limit accounting SDK surfaces: stop_context on acks and usage
items, the past-limit report helper, the past-limit query filters, and
negative_since on the balance."""
import unittest
from unittest.mock import patch, MagicMock

from ubb.billing import BillingClient
from ubb.metering import MeteringClient

_CTX = [{"limit": "task_limit", "stop_scope": "task",
         "tripped_at": "2026-07-17T10:00:00+00:00", "episode_seq": None,
         "task_id": "task_1", "subtask_id": None, "arrived_after": False}]


class StopContextAckTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_carries_stop_context(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": True, "stop_reason": "task_limit",
            "stop_scope": "task", "stop_context": _CTX})
        result = self.client.record_usage(customer_id="c1", request_id="r1",
                                          idempotency_key="i1", task_id="task_1")
        self.assertEqual(result.stop_context, _CTX)
        self.assertFalse(result.stop_context[0]["arrived_after"])

    @patch("ubb.metering.httpx.Client.post")
    def test_stop_context_defaults_none(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"event_id": "e1", "suspended": False})
        result = self.client.record_usage(customer_id="c1", request_id="r1",
                                          idempotency_key="i1")
        self.assertIsNone(result.stop_context)


class UsageFiltersTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.get")
    def test_get_usage_passes_filters_and_parses_stop_context(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [{"id": "e1", "request_id": "r1", "stop_context": _CTX}],
            "next_cursor": None, "has_more": False})
        page = self.client.get_usage("c1", past_limit=True, stop_scope="task",
                                     episode_seq=3)
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["past_limit"], True)
        self.assertEqual(params["stop_scope"], "task")
        self.assertEqual(params["episode_seq"], 3)
        self.assertEqual(page.data[0].stop_context, _CTX)

    @patch("ubb.metering.httpx.Client.get")
    def test_analytics_passes_past_limit_filters(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"total_events": 0})
        self.client.usage_analytics(past_limit=True, stop_scope="customer",
                                    episode_seq=1)
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["past_limit"], True)
        self.assertEqual(params["stop_scope"], "customer")
        self.assertEqual(params["episode_seq"], 1)


class PastLimitReportTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.get")
    def test_report_hits_the_endpoint_and_returns_the_body(self, mock_get):
        body = {"customer_id": "c1", "billing_owner_id": "c1",
                "since": None, "until": None,
                "episodes": [{"family": "task", "limit": "task_limit",
                              "events": [], "event_count": 0}],
                "totals_per_limit": {}}
        mock_get.return_value = MagicMock(status_code=200, json=lambda: body)
        report = self.client.get_past_limit_report("c1", since="2026-07-01T00:00:00Z")
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/customers/c1/past-limit-report")
        self.assertEqual(mock_get.call_args.kwargs["params"],
                         {"since": "2026-07-01T00:00:00Z"})
        self.assertEqual(report, body)


class NegativeSinceTest(unittest.TestCase):
    def setUp(self):
        self.client = BillingClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                                    max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.billing.httpx.Client.get")
    def test_balance_carries_negative_since(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "balance_micros": -1_000_000, "currency": "usd",
            "negative_since": "2026-07-17T09:00:00+00:00"})
        result = self.client.get_balance("c1")
        self.assertEqual(result.negative_since, "2026-07-17T09:00:00+00:00")

    @patch("ubb.billing.httpx.Client.get")
    def test_negative_since_defaults_none(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "balance_micros": 5, "currency": "usd"})
        self.assertIsNone(self.client.get_balance("c1").negative_since)
