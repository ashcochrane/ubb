"""P7: the SDK surfaces the Tier-2 customer-wide stop verdict, and the opt-in
raise_on_stop mode."""
import unittest
from unittest.mock import patch, MagicMock

from ubb.metering import MeteringClient
from ubb.exceptions import UBBCustomerStoppedError


class StopVerdictTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_surfaces_stop_fields(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "stop": True, "stop_reason": "customer_wide_stop",
            "stop_scope": "customer"})
        result = self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1")
        self.assertTrue(result.stop)
        self.assertEqual(result.stop_reason, "customer_wide_stop")
        self.assertEqual(result.stop_scope, "customer")

    @patch("ubb.metering.httpx.Client.post")
    def test_default_does_not_raise_on_stop(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "stop": True, "stop_reason": "customer_wide_stop"})
        result = self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1")
        self.assertTrue(result.stop)  # returned, not raised

    @patch("ubb.metering.httpx.Client.post")
    def test_raise_on_stop_raises_customer_stopped(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "stop": True, "stop_reason": "customer_wide_stop",
            "stop_scope": "customer", "run_id": "run_1"})
        with self.assertRaises(UBBCustomerStoppedError) as cm:
            self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                     raise_on_stop=True)
        self.assertEqual(cm.exception.reason, "customer_wide_stop")
        self.assertEqual(cm.exception.run_id, "run_1")

    @patch("ubb.metering.httpx.Client.post")
    def test_raise_on_stop_no_raise_when_not_stopped(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "stop": False})
        result = self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                          raise_on_stop=True)
        self.assertFalse(result.stop)  # no raise
