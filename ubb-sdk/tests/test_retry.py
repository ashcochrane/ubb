"""Tests for SDK retry logic."""
import unittest

from ubb.exceptions import (
    UBBAPIError, UBBAuthError, UBBConnectionError, UBBConflictError,
    UBBHardStopError, UBBRunNotActiveError, UBBValidationError,
)
from unittest.mock import patch, MagicMock
from ubb.retry import is_retryable, backoff_delay, request_with_retry


class TestRetryAfterAttribute(unittest.TestCase):
    def test_api_error_has_retry_after_default_none(self):
        err = UBBAPIError(429, "rate limited")
        self.assertIsNone(err.retry_after)

    def test_api_error_retry_after_can_be_set(self):
        err = UBBAPIError(429, "rate limited")
        err.retry_after = 1.5
        self.assertEqual(err.retry_after, 1.5)

    def test_hard_stop_error_has_retry_after_none(self):
        err = UBBHardStopError("run_1", "cost_exceeded", 100000)
        self.assertIsNone(err.retry_after)

    def test_run_not_active_error_has_retry_after_none(self):
        err = UBBRunNotActiveError("run_1", "killed")
        self.assertIsNone(err.retry_after)


class TestIsRetryable(unittest.TestCase):
    def test_connection_error_is_retryable(self):
        err = UBBConnectionError("timeout", original=None)
        self.assertTrue(is_retryable(err))

    def test_429_api_error_is_retryable(self):
        err = UBBAPIError(429, "rate limited")
        self.assertTrue(is_retryable(err))

    def test_502_api_error_is_retryable(self):
        err = UBBAPIError(502, "bad gateway")
        self.assertTrue(is_retryable(err))

    def test_503_api_error_is_retryable(self):
        err = UBBAPIError(503, "service unavailable")
        self.assertTrue(is_retryable(err))

    def test_504_api_error_is_retryable(self):
        err = UBBAPIError(504, "gateway timeout")
        self.assertTrue(is_retryable(err))

    def test_hard_stop_error_not_retryable(self):
        err = UBBHardStopError("run_1", "cost_exceeded", 100000)
        self.assertFalse(is_retryable(err))

    def test_run_not_active_error_not_retryable(self):
        err = UBBRunNotActiveError("run_1", "killed")
        self.assertFalse(is_retryable(err))

    def test_auth_error_not_retryable(self):
        err = UBBAuthError("bad key")
        self.assertFalse(is_retryable(err))

    def test_400_api_error_not_retryable(self):
        err = UBBAPIError(400, "bad request")
        self.assertFalse(is_retryable(err))

    def test_401_api_error_not_retryable(self):
        err = UBBAPIError(401, "unauthorized")
        self.assertFalse(is_retryable(err))

    def test_404_api_error_not_retryable(self):
        err = UBBAPIError(404, "not found")
        self.assertFalse(is_retryable(err))

    def test_409_conflict_not_retryable(self):
        err = UBBConflictError("duplicate")
        self.assertFalse(is_retryable(err))

    def test_422_api_error_not_retryable(self):
        err = UBBAPIError(422, "unprocessable")
        self.assertFalse(is_retryable(err))

    def test_validation_error_not_retryable(self):
        err = UBBValidationError("bad input")
        self.assertFalse(is_retryable(err))


class TestBackoffDelay(unittest.TestCase):
    def test_attempt_0_base_is_0_5(self):
        delay = backoff_delay(0)
        self.assertGreaterEqual(delay, 0.375)
        self.assertLessEqual(delay, 0.625)

    def test_attempt_1_base_is_1(self):
        delay = backoff_delay(1)
        self.assertGreaterEqual(delay, 0.75)
        self.assertLessEqual(delay, 1.25)

    def test_attempt_2_base_is_2(self):
        delay = backoff_delay(2)
        self.assertGreaterEqual(delay, 1.5)
        self.assertLessEqual(delay, 2.5)

    def test_capped_at_10(self):
        delay = backoff_delay(10)
        self.assertLessEqual(delay, 10.0)

    def test_retry_after_overrides_backoff(self):
        delay = backoff_delay(0, retry_after=3.0)
        self.assertEqual(delay, 3.0)


class TestRequestWithRetry(unittest.TestCase):
    def test_success_on_first_attempt(self):
        fn = MagicMock(return_value="ok")
        result = request_with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")
        fn.assert_called_once()

    @patch("ubb.retry.time.sleep")
    def test_retries_on_connection_error(self, mock_sleep):
        fn = MagicMock(side_effect=[
            UBBConnectionError("timeout", original=None),
            "ok",
        ])
        result = request_with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("ubb.retry.time.sleep")
    def test_retries_on_429(self, mock_sleep):
        err = UBBAPIError(429, "rate limited")
        fn = MagicMock(side_effect=[err, "ok"])
        result = request_with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 2)

    @patch("ubb.retry.time.sleep")
    def test_retries_on_502(self, mock_sleep):
        fn = MagicMock(side_effect=[UBBAPIError(502, "bad gateway"), "ok"])
        result = request_with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")

    @patch("ubb.retry.time.sleep")
    def test_retries_on_503(self, mock_sleep):
        fn = MagicMock(side_effect=[UBBAPIError(503, "service unavailable"), "ok"])
        result = request_with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")

    @patch("ubb.retry.time.sleep")
    def test_retries_on_504(self, mock_sleep):
        fn = MagicMock(side_effect=[UBBAPIError(504, "gateway timeout"), "ok"])
        result = request_with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")

    @patch("ubb.retry.time.sleep")
    def test_uses_retry_after_header_for_429(self, mock_sleep):
        err = UBBAPIError(429, "rate limited")
        err.retry_after = 2.5
        fn = MagicMock(side_effect=[err, "ok"])
        request_with_retry(fn, max_retries=3)
        mock_sleep.assert_called_once_with(2.5)

    def test_no_retry_on_hard_stop(self):
        fn = MagicMock(side_effect=UBBHardStopError("r1", "cost", 100))
        with self.assertRaises(UBBHardStopError):
            request_with_retry(fn, max_retries=3)
        fn.assert_called_once()

    def test_no_retry_on_run_not_active(self):
        fn = MagicMock(side_effect=UBBRunNotActiveError("r1", "killed"))
        with self.assertRaises(UBBRunNotActiveError):
            request_with_retry(fn, max_retries=3)
        fn.assert_called_once()

    def test_no_retry_on_400(self):
        fn = MagicMock(side_effect=UBBAPIError(400, "bad request"))
        with self.assertRaises(UBBAPIError):
            request_with_retry(fn, max_retries=3)
        fn.assert_called_once()

    def test_no_retry_on_auth_error(self):
        fn = MagicMock(side_effect=UBBAuthError("bad key"))
        with self.assertRaises(UBBAuthError):
            request_with_retry(fn, max_retries=3)
        fn.assert_called_once()

    @patch("ubb.retry.time.sleep")
    def test_max_retries_0_disables_retry(self, mock_sleep):
        fn = MagicMock(side_effect=UBBConnectionError("timeout", original=None))
        with self.assertRaises(UBBConnectionError):
            request_with_retry(fn, max_retries=0)
        fn.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("ubb.retry.time.sleep")
    def test_exhausts_retries_then_raises(self, mock_sleep):
        err = UBBAPIError(503, "unavailable")
        fn = MagicMock(side_effect=err)
        with self.assertRaises(UBBAPIError) as ctx:
            request_with_retry(fn, max_retries=2)
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(fn.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("ubb.retry.time.sleep")
    def test_backoff_increases(self, mock_sleep):
        fn = MagicMock(side_effect=UBBConnectionError("timeout", original=None))
        with self.assertRaises(UBBConnectionError):
            request_with_retry(fn, max_retries=3)
        self.assertEqual(mock_sleep.call_count, 3)
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertLess(delays[0], delays[1])
        self.assertLess(delays[1], delays[2])


class TestClientRetryIntegration(unittest.TestCase):
    """Verify product clients accept max_retries and use retry wrapper."""

    @patch("ubb.retry.time.sleep")
    def test_metering_client_retries_on_503(self, mock_sleep):
        from ubb.metering import MeteringClient
        client = MeteringClient("ubb_live_test", "http://localhost:8001",
                                max_retries=2)
        with patch.object(client._http, "get") as mock_get:
            resp_fail = MagicMock(status_code=503, text="unavailable")
            resp_fail.json.return_value = {"error": "unavailable"}
            resp_fail.headers = {}
            resp_ok = MagicMock(status_code=200)
            resp_ok.json.return_value = {"balance_micros": 100, "currency": "USD"}
            mock_get.side_effect = [resp_fail, resp_ok]
            result = client._request("get", "/test")
            self.assertEqual(mock_get.call_count, 2)
        client.close()

    @patch("ubb.retry.time.sleep")
    def test_billing_client_retries_on_timeout(self, mock_sleep):
        import httpx
        from ubb.billing import BillingClient
        client = BillingClient("ubb_live_test", "http://localhost:8001",
                               max_retries=1)
        with patch.object(client._http, "get") as mock_get:
            mock_get.side_effect = [
                httpx.TimeoutException("timeout"),
                MagicMock(status_code=200, json=lambda: {}),
            ]
            result = client._request("get", "/test")
            self.assertEqual(mock_get.call_count, 2)
        client.close()

    def test_metering_request_usage_no_retry_on_hard_stop(self):
        from ubb.metering import MeteringClient
        client = MeteringClient("ubb_live_test", max_retries=3)
        with patch.object(client._http, "post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=429,
                json=lambda: {"hard_stop": True, "run_id": "r1",
                              "reason": "cost", "total_cost_micros": 100},
            )
            with self.assertRaises(UBBHardStopError):
                client._request_usage("post", "/api/v1/metering/usage", json={})
            mock_post.assert_called_once()
        client.close()

    @patch("ubb.retry.time.sleep")
    def test_ubb_client_passes_max_retries(self, mock_sleep):
        from ubb.client import UBBClient
        client = UBBClient("ubb_live_test", max_retries=5,
                           metering=True, billing=True)
        self.assertEqual(client.metering._max_retries, 5)
        self.assertEqual(client.billing._max_retries, 5)
        client.close()

    def test_ubb_client_default_max_retries_is_3(self):
        from ubb.client import UBBClient
        client = UBBClient("ubb_live_test", metering=True, billing=True)
        self.assertEqual(client.metering._max_retries, 3)
        self.assertEqual(client.billing._max_retries, 3)
        client.close()

    def test_request_once_parses_retry_after_header(self):
        from ubb.metering import MeteringClient
        client = MeteringClient("ubb_live_test", max_retries=0)
        with patch.object(client._http, "get") as mock_get:
            resp = MagicMock(status_code=429, text="rate limited")
            resp.json.return_value = {"error": "rate limited"}
            resp.headers = {"Retry-After": "2.5"}
            mock_get.return_value = resp
            with self.assertRaises(UBBAPIError) as ctx:
                client._request_once("get", "/test")
            self.assertEqual(ctx.exception.retry_after, 2.5)
        client.close()


if __name__ == "__main__":
    unittest.main()
