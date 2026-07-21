"""One-rule contract: every usage report answers 200; the ack carries the
stop verdict (stop / stop_reason / stop_scope), and raise_on_stop=True turns
any stop verdict into UBBStoppedError(reason, scope, task_id)."""
import unittest
from unittest.mock import patch, MagicMock

from ubb.metering import MeteringClient
from ubb.exceptions import UBBStoppedError


class StopVerdictTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_surfaces_customer_stop_fields(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": True, "stop_reason": "customer_wide_stop",
            "stop_scope": "customer"})
        result = self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1")
        self.assertTrue(result.stop)
        self.assertEqual(result.stop_reason, "customer_wide_stop")
        self.assertEqual(result.stop_scope, "customer")

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_surfaces_task_stop_fields_and_totals(self, mock_post):
        """A task-limit crossing rides a 200 — the event landed and billed;
        the ack names the task and carries its post-event totals."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": True, "stop_reason": "task_limit",
            "stop_scope": "task", "task_id": "task_1", "parent_task_id": None,
            "task_total_billed_cost_micros": 2_000_000,
            "task_total_provider_cost_micros": 1_100_000})
        result = self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                          task_id="task_1")
        self.assertTrue(result.stop)
        self.assertEqual(result.stop_reason, "task_limit")
        self.assertEqual(result.stop_scope, "task")
        self.assertEqual(result.task_id, "task_1")
        self.assertIsNone(result.parent_task_id)
        self.assertEqual(result.task_total_billed_cost_micros, 2_000_000)
        self.assertEqual(result.task_total_provider_cost_micros, 1_100_000)

    @patch("ubb.metering.httpx.Client.post")
    def test_default_does_not_raise_on_stop(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": True, "stop_reason": "customer_wide_stop"})
        result = self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1")
        self.assertTrue(result.stop)  # returned, not raised

    @patch("ubb.metering.httpx.Client.post")
    def test_raise_on_stop_raises_for_customer_scope(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": True, "stop_reason": "customer_wide_stop",
            "stop_scope": "customer"})
        with self.assertRaises(UBBStoppedError) as cm:
            self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                     raise_on_stop=True)
        self.assertEqual(cm.exception.reason, "customer_wide_stop")
        self.assertEqual(cm.exception.scope, "customer")
        self.assertIsNone(cm.exception.task_id)

    @patch("ubb.metering.httpx.Client.post")
    def test_raise_on_stop_raises_for_task_scope_with_task_id(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": True, "stop_reason": "task_limit",
            "stop_scope": "task", "task_id": "task_1"})
        with self.assertRaises(UBBStoppedError) as cm:
            self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                     task_id="task_1", raise_on_stop=True)
        self.assertEqual(cm.exception.reason, "task_limit")
        self.assertEqual(cm.exception.scope, "task")
        self.assertEqual(cm.exception.task_id, "task_1")

    @patch("ubb.metering.httpx.Client.post")
    def test_raise_on_stop_raises_for_task_not_active(self, mock_post):
        """An event landing on a killed/completed task still records + bills
        (HTTP 200); the verdict is task_not_active, scope task."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": True, "stop_reason": "task_not_active",
            "stop_scope": "task", "task_id": "task_1",
            "task_total_billed_cost_micros": 3_000_000,
            "task_total_provider_cost_micros": 1_500_000})
        with self.assertRaises(UBBStoppedError) as cm:
            self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                     task_id="task_1", raise_on_stop=True)
        self.assertEqual(cm.exception.reason, "task_not_active")
        self.assertEqual(cm.exception.scope, "task")
        self.assertEqual(cm.exception.task_id, "task_1")

    @patch("ubb.metering.httpx.Client.post")
    def test_raise_on_stop_raises_for_customer_floor(self, mock_post):
        """crossed_floor_snapshot: reason customer_floor, scope task."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": True, "stop_reason": "customer_floor",
            "stop_scope": "task", "task_id": "task_1"})
        with self.assertRaises(UBBStoppedError) as cm:
            self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                     task_id="task_1", raise_on_stop=True)
        self.assertEqual(cm.exception.reason, "customer_floor")
        self.assertEqual(cm.exception.scope, "task")

    @patch("ubb.metering.httpx.Client.post")
    def test_raise_on_stop_no_raise_when_not_stopped(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False, "stop": False})
        result = self.client.record_usage(customer_id="c1", request_id="r1", idempotency_key="i1",
                                          raise_on_stop=True)
        self.assertFalse(result.stop)  # no raise

    def test_stopped_error_exported_from_ubb(self):
        import ubb
        self.assertIs(ubb.UBBStoppedError, UBBStoppedError)
        self.assertIn("UBBStoppedError", ubb.__all__)
