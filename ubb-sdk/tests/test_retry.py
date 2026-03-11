"""Tests for SDK retry logic."""
import unittest

from ubb.exceptions import (
    UBBAPIError, UBBAuthError, UBBConnectionError, UBBConflictError,
    UBBHardStopError, UBBRunNotActiveError, UBBValidationError,
)
from ubb.retry import is_retryable, backoff_delay


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


if __name__ == "__main__":
    unittest.main()
