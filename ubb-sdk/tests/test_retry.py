"""Tests for SDK retry logic."""
import unittest

from ubb.exceptions import UBBAPIError, UBBHardStopError, UBBRunNotActiveError


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


if __name__ == "__main__":
    unittest.main()
