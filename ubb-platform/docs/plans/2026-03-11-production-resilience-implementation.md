# Production Resilience Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add production resilience to the UBB platform (API rate limiting) and SDK (retry logic with backoff), plus deployment config for timeouts and connection pooling.

**Architecture:** Two-layer Redis rate limiting (global middleware + per-tenant ninja dependency) with Lua atomic counters and fail-open degradation. SDK retry via shared module wrapping existing `_request()` methods with exponential backoff + jitter. Deployment config as settings-only changes.

**Tech Stack:** Django 6.0, django-ninja, Redis (Lua scripts), Python SDK (httpx), `time.sleep` + `random` for backoff.

**Spec:** `docs/plans/2026-03-11-production-resilience-design.md`

---

## File Structure

### Platform (rate limiting)

| File | Responsibility |
|------|---------------|
| `core/rate_limit.py` | NEW — Lua script, `GlobalRateLimitMiddleware`, `RateLimit` dependency, `RateLimitHeaderMiddleware` |
| `apps/platform/tenants/models.py` | MODIFY — add `rate_limit_per_second` nullable field |
| `apps/platform/tenants/migrations/0008_add_rate_limit_field.py` | NEW — migration |
| `config/settings.py` | MODIFY — add rate limit defaults, middleware entries, timeout/pooling config |
| `api/v1/metering_endpoints.py` | MODIFY — add `RateLimit("high")` dependency |
| `api/v1/billing_endpoints.py` | MODIFY — add `RateLimit("high")` / `RateLimit("standard")` dependencies |
| `api/v1/endpoints.py` | MODIFY — add `RateLimit("standard")` dependency |
| `api/v1/platform_endpoints.py` | MODIFY — add `RateLimit("standard")` dependency |
| `api/v1/tenant_endpoints.py` | MODIFY — add `RateLimit("standard")` dependency |
| `apps/subscriptions/api/endpoints.py` | MODIFY — add `RateLimit("standard")` dependency |
| `apps/referrals/api/endpoints.py` | MODIFY — add `RateLimit("standard")` dependency |
| `apps/platform/events/api/webhook_endpoints.py` | MODIFY — add `RateLimit("standard")` dependency |
| `core/tests/test_rate_limit.py` | NEW — all rate limit tests |

### SDK (retry logic)

| File | Responsibility |
|------|---------------|
| `ubb-sdk/ubb/retry.py` | NEW — `is_retryable()`, `backoff_delay()`, `request_with_retry()` |
| `ubb-sdk/ubb/exceptions.py` | MODIFY — add `retry_after` to `UBBAPIError` |
| `ubb-sdk/ubb/metering.py` | MODIFY — accept `max_retries`, set `retry_after` on 429, wrap with retry |
| `ubb-sdk/ubb/billing.py` | MODIFY — accept `max_retries`, set `retry_after` on 429, wrap with retry |
| `ubb-sdk/ubb/subscriptions.py` | MODIFY — accept `max_retries`, set `retry_after` on 429, wrap with retry |
| `ubb-sdk/ubb/referrals.py` | MODIFY — accept `max_retries`, set `retry_after` on 429, wrap with retry |
| `ubb-sdk/ubb/client.py` | MODIFY — accept `max_retries`, pass to product clients |
| `ubb-sdk/tests/test_retry.py` | NEW — all retry logic tests |

---

## Chunk 1: SDK Retry Logic

### Task 1: Add `retry_after` to `UBBAPIError`

**Files:**
- Modify: `ubb-sdk/ubb/exceptions.py:10-14`

- [ ] **Step 1: Write the failing test**

Create `ubb-sdk/tests/test_retry.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-sdk && python -m pytest tests/test_retry.py::TestRetryAfterAttribute -v`
Expected: FAIL — `UBBAPIError` has no `retry_after` attribute

- [ ] **Step 3: Write minimal implementation**

Edit `ubb-sdk/ubb/exceptions.py` — add `retry_after` to `UBBAPIError.__init__`:

```python
class UBBAPIError(UBBError):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        self.retry_after: float | None = None
        super().__init__(f"API error {status_code}: {detail}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ubb-sdk && python -m pytest tests/test_retry.py::TestRetryAfterAttribute -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ubb-sdk/ubb/exceptions.py ubb-sdk/tests/test_retry.py
git commit -m "feat: add retry_after attribute to UBBAPIError"
```

---

### Task 2: Create retry module — `is_retryable()` and `backoff_delay()`

**Files:**
- Create: `ubb-sdk/ubb/retry.py`
- Test: `ubb-sdk/tests/test_retry.py`

- [ ] **Step 1: Write the failing tests**

Append to `ubb-sdk/tests/test_retry.py`:

```python
from ubb.retry import is_retryable, backoff_delay
from ubb.exceptions import (
    UBBConnectionError, UBBAPIError, UBBAuthError,
    UBBHardStopError, UBBRunNotActiveError, UBBConflictError,
    UBBValidationError,
)


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
        """UBBHardStopError has status 429 but must NOT be retried."""
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
        # With random seed for deterministic test
        delay = backoff_delay(0)
        self.assertGreaterEqual(delay, 0.375)  # 0.5 - 25%
        self.assertLessEqual(delay, 0.625)      # 0.5 + 25%

    def test_attempt_1_base_is_1(self):
        delay = backoff_delay(1)
        self.assertGreaterEqual(delay, 0.75)
        self.assertLessEqual(delay, 1.25)

    def test_attempt_2_base_is_2(self):
        delay = backoff_delay(2)
        self.assertGreaterEqual(delay, 1.5)
        self.assertLessEqual(delay, 2.5)

    def test_capped_at_10(self):
        delay = backoff_delay(10)  # base would be 512
        self.assertLessEqual(delay, 10.0)

    def test_retry_after_overrides_backoff(self):
        """When retry_after is provided, it is used instead of computed backoff."""
        delay = backoff_delay(0, retry_after=3.0)
        self.assertEqual(delay, 3.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-sdk && python -m pytest tests/test_retry.py::TestIsRetryable tests/test_retry.py::TestBackoffDelay -v`
Expected: FAIL — `ubb.retry` module does not exist

- [ ] **Step 3: Write minimal implementation**

Create `ubb-sdk/ubb/retry.py`:

```python
"""Shared retry logic for UBB SDK clients.

Exponential backoff with jitter, matching the platform's stripe_service.py pattern:
- Base: 0.5s * 2^attempt
- Jitter: +/-25%
- Max delay: 10s
"""
from __future__ import annotations

import random
import time

from ubb.exceptions import (
    UBBConnectionError, UBBAPIError, UBBHardStopError, UBBRunNotActiveError,
)

_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


def is_retryable(error: Exception) -> bool:
    """Check whether an error should be retried.

    Domain errors (UBBHardStopError, UBBRunNotActiveError) are never retried,
    even though their status codes (429, 409) overlap with retryable codes.
    """
    if isinstance(error, (UBBHardStopError, UBBRunNotActiveError)):
        return False
    if isinstance(error, UBBConnectionError):
        return True
    if isinstance(error, UBBAPIError):
        return error.status_code in _RETRYABLE_STATUS_CODES
    return False


def backoff_delay(attempt: int, retry_after: float | None = None) -> float:
    """Compute delay for the given attempt number.

    If retry_after is provided (from Retry-After header), it takes precedence.
    Otherwise: 0.5s * 2^attempt with +/-25% jitter, capped at 10s.
    """
    if retry_after is not None:
        return retry_after
    base = 0.5 * (2 ** attempt)
    jitter = base * 0.25 * (2 * random.random() - 1)
    return min(base + jitter, 10.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-sdk && python -m pytest tests/test_retry.py::TestIsRetryable tests/test_retry.py::TestBackoffDelay -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add ubb-sdk/ubb/retry.py ubb-sdk/tests/test_retry.py
git commit -m "feat: add retry module with is_retryable and backoff_delay"
```

---

### Task 3: Add `request_with_retry()` wrapper

**Files:**
- Modify: `ubb-sdk/ubb/retry.py`
- Test: `ubb-sdk/tests/test_retry.py`

- [ ] **Step 1: Write the failing tests**

Append to `ubb-sdk/tests/test_retry.py`:

```python
from unittest.mock import patch, MagicMock, call
from ubb.retry import request_with_retry


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
        fn = MagicMock(side_effect=[
            UBBAPIError(502, "bad gateway"),
            "ok",
        ])
        result = request_with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")

    @patch("ubb.retry.time.sleep")
    def test_retries_on_503(self, mock_sleep):
        fn = MagicMock(side_effect=[
            UBBAPIError(503, "service unavailable"),
            "ok",
        ])
        result = request_with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")

    @patch("ubb.retry.time.sleep")
    def test_retries_on_504(self, mock_sleep):
        fn = MagicMock(side_effect=[
            UBBAPIError(504, "gateway timeout"),
            "ok",
        ])
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
        self.assertEqual(fn.call_count, 3)  # 1 initial + 2 retries
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("ubb.retry.time.sleep")
    def test_backoff_increases(self, mock_sleep):
        """Verify sleep durations increase across retries."""
        fn = MagicMock(side_effect=UBBConnectionError("timeout", original=None))
        with self.assertRaises(UBBConnectionError):
            request_with_retry(fn, max_retries=3)
        self.assertEqual(mock_sleep.call_count, 3)
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        # Attempt 0: ~0.5s, Attempt 1: ~1s, Attempt 2: ~2s
        self.assertLess(delays[0], delays[1])
        self.assertLess(delays[1], delays[2])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-sdk && python -m pytest tests/test_retry.py::TestRequestWithRetry -v`
Expected: FAIL — `request_with_retry` not found in `ubb.retry`

- [ ] **Step 3: Write minimal implementation**

Append to `ubb-sdk/ubb/retry.py`:

```python
import logging

logger = logging.getLogger("ubb.retry")


def request_with_retry(fn, *, max_retries: int = 3, **kwargs):
    """Call fn() with retry on transient errors.

    Args:
        fn: Callable that makes the API request. Called with **kwargs.
        max_retries: Maximum number of retry attempts (0 disables retry).
        **kwargs: Passed through to fn().

    Returns:
        The return value of fn().

    Raises:
        The last exception if all retries are exhausted, or any
        non-retryable exception immediately.
    """
    last_error: Exception | None = None
    for attempt in range(1 + max_retries):
        try:
            return fn(**kwargs)
        except Exception as e:
            if not is_retryable(e) or attempt >= max_retries:
                raise
            last_error = e
            retry_after = getattr(e, "retry_after", None)
            delay = backoff_delay(attempt, retry_after=retry_after)
            logger.warning(
                "Retrying request (attempt %d/%d) after %.2fs: %s",
                attempt + 1, max_retries, delay, e,
            )
            time.sleep(delay)
    raise last_error  # pragma: no cover — loop always raises or returns
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-sdk && python -m pytest tests/test_retry.py::TestRequestWithRetry -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add ubb-sdk/ubb/retry.py ubb-sdk/tests/test_retry.py
git commit -m "feat: add request_with_retry wrapper with backoff"
```

---

### Task 4: Wire retry into SDK product clients

**Files:**
- Modify: `ubb-sdk/ubb/metering.py:18-19,35-49,94-123`
- Modify: `ubb-sdk/ubb/billing.py:17-18,34-48`
- Modify: `ubb-sdk/ubb/subscriptions.py:17-18` (same `_request` pattern)
- Modify: `ubb-sdk/ubb/referrals.py:17-18` (same `_request` pattern)
- Modify: `ubb-sdk/ubb/client.py:34-67`

- [ ] **Step 1: Write the failing test**

Append to `ubb-sdk/tests/test_retry.py`:

```python
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
            resp_ok = MagicMock(status_code=200)
            resp_ok.json.return_value = {"balance_micros": 100, "currency": "USD"}
            mock_get.side_effect = [resp_fail, resp_ok]
            # _request is wrapped with retry — should succeed on 2nd attempt
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
            mock_post.assert_called_once()  # No retry
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
        """Verify _request_once sets retry_after from Retry-After response header."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-sdk && python -m pytest tests/test_retry.py::TestClientRetryIntegration -v`
Expected: FAIL — `MeteringClient.__init__` does not accept `max_retries`

- [ ] **Step 3: Implement — update MeteringClient**

Edit `ubb-sdk/ubb/metering.py`:

1. Add import at top:
```python
from ubb.retry import request_with_retry
```

2. Update `__init__` to accept `max_retries`:
```python
    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, max_retries: int = 3) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
```

3. Rename existing `_request` to `_request_once` and add retry-wrapping `_request`:
```python
    def _request_once(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = getattr(self._http, method)(path, **kwargs)
        except httpx.TimeoutException as e:
            raise UBBConnectionError("Request timed out", original=e) from e
        except httpx.ConnectError as e:
            raise UBBConnectionError("Could not connect to UBB API", original=e) from e
        if response.status_code == 401:
            raise UBBAuthError("Invalid or revoked API key")
        detail = self._extract_error_detail(response)
        if response.status_code == 409:
            raise UBBConflictError(detail)
        if response.status_code >= 400:
            err = UBBAPIError(response.status_code, detail)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    err.retry_after = float(retry_after)
                except (ValueError, TypeError):
                    pass
            raise err
        return response

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return request_with_retry(
            self._request_once, max_retries=self._max_retries,
            method=method, path=path, **kwargs,
        )
```

4. Rename existing `_request_usage` to `_request_usage_once` and add retry wrapper:
```python
    def _request_usage_once(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Like _request_once but handles run-specific error codes."""
        try:
            response = getattr(self._http, method)(path, **kwargs)
        except httpx.TimeoutException as e:
            raise UBBConnectionError("Request timed out", original=e) from e
        except httpx.ConnectError as e:
            raise UBBConnectionError("Could not connect to UBB API", original=e) from e
        if response.status_code == 401:
            raise UBBAuthError("Invalid or revoked API key")
        if response.status_code == 429:
            body = response.json()
            if body.get("hard_stop"):
                raise UBBHardStopError(
                    run_id=body.get("run_id", ""),
                    reason=body.get("reason", ""),
                    total_cost_micros=body.get("total_cost_micros", 0),
                )
            # Regular 429 (rate limited) — raise UBBAPIError with retry_after
            detail = self._extract_error_detail(response)
            err = UBBAPIError(429, detail)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    err.retry_after = float(retry_after)
                except (ValueError, TypeError):
                    pass
            raise err
        if response.status_code == 409:
            body = response.json()
            if body.get("error") == "run_not_active":
                raise UBBRunNotActiveError(
                    run_id=body.get("run_id", ""),
                    status=body.get("status", ""),
                )
            raise UBBConflictError(self._extract_error_detail(response))
        detail = self._extract_error_detail(response)
        if response.status_code >= 400:
            err = UBBAPIError(response.status_code, detail)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    err.retry_after = float(retry_after)
                except (ValueError, TypeError):
                    pass
            raise err
        return response

    def _request_usage(self, method: str, path: str, **kwargs) -> httpx.Response:
        return request_with_retry(
            self._request_usage_once, max_retries=self._max_retries,
            method=method, path=path, **kwargs,
        )
```

- [ ] **Step 4: Implement — update BillingClient**

Edit `ubb-sdk/ubb/billing.py`:

1. Add import:
```python
from ubb.retry import request_with_retry
```

2. Update `__init__`:
```python
    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, max_retries: int = 3) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
```

3. Rename `_request` to `_request_once`, add retry-aware error handling and new `_request`:
```python
    def _request_once(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = getattr(self._http, method)(path, **kwargs)
        except httpx.TimeoutException as e:
            raise UBBConnectionError("Request timed out", original=e) from e
        except httpx.ConnectError as e:
            raise UBBConnectionError("Could not connect to UBB API", original=e) from e
        if response.status_code == 401:
            raise UBBAuthError("Invalid or revoked API key")
        detail = self._extract_error_detail(response)
        if response.status_code == 409:
            raise UBBConflictError(detail)
        if response.status_code >= 400:
            err = UBBAPIError(response.status_code, detail)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    err.retry_after = float(retry_after)
                except (ValueError, TypeError):
                    pass
            raise err
        return response

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return request_with_retry(
            self._request_once, max_retries=self._max_retries,
            method=method, path=path, **kwargs,
        )
```

- [ ] **Step 5: Implement — update SubscriptionsClient and ReferralsClient**

Apply the same pattern to both:
1. Add `from ubb.retry import request_with_retry`
2. Add `max_retries: int = 3` to `__init__`, store as `self._max_retries`
3. Rename `_request` → `_request_once` with `retry_after` extraction on errors
4. Add new `_request` that delegates to `request_with_retry`

The changes are identical to BillingClient above — same `_request_once` / `_request` split.

- [ ] **Step 6: Implement — update UBBClient**

Edit `ubb-sdk/ubb/client.py`:

1. Add `max_retries: int = 3` to `__init__` signature:
```python
    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, widget_secret: str | None = None,
                 tenant_id: str | None = None,
                 max_retries: int = 3,
                 metering: bool = True, billing: bool = False,
                 subscriptions: bool = False,
                 referrals: bool = False) -> None:
```

2. Pass `max_retries` to each product client construction:
```python
        self.metering: MeteringClient | None = (
            MeteringClient(api_key, base_url, timeout, max_retries=max_retries) if metering else None
        )
        self.billing: BillingClient | None = (
            BillingClient(api_key, base_url, timeout, max_retries=max_retries) if billing else None
        )
        # ... same for subscriptions and referrals
```

- [ ] **Step 7: Update existing SDK tests to disable retry**

Existing tests expect single-attempt behavior. With the default `max_retries=3`, tests that trigger retryable errors (timeouts, connection errors) will now retry with real `time.sleep` delays. Fix by passing `max_retries=0` when creating test clients.

Update `setUp` in each existing test file:

**`ubb-sdk/tests/test_metering_client.py`** — change client creation to:
```python
self.client = MeteringClient(api_key="ubb_live_test123",
                              base_url="http://localhost:8001",
                              max_retries=0)
```

**`ubb-sdk/tests/test_billing_client.py`** — same pattern with `max_retries=0`

**`ubb-sdk/tests/test_subscriptions_client.py`** — same pattern with `max_retries=0`

**`ubb-sdk/tests/test_referrals_client.py`** — same pattern with `max_retries=0`

**`ubb-sdk/tests/test_client.py`** — change `UBBClient` creation to include `max_retries=0`:
```python
self.client = UBBClient(api_key="ubb_live_test123",
                         base_url="http://localhost:8001",
                         metering=True, billing=True,
                         max_retries=0)
```

Similarly for `test_sdk_delegation.py`, `test_orchestration.py`, `test_ubb_client_subscriptions.py`, `test_ubb_client_referrals.py`.

- [ ] **Step 8: Run ALL SDK tests to verify nothing is broken**

Run: `cd ubb-sdk && python -m pytest tests/ -v`
Expected: All tests pass (existing tests + new retry tests)

- [ ] **Step 8: Commit**

```bash
git add ubb-sdk/ubb/retry.py ubb-sdk/ubb/exceptions.py ubb-sdk/ubb/metering.py ubb-sdk/ubb/billing.py ubb-sdk/ubb/subscriptions.py ubb-sdk/ubb/referrals.py ubb-sdk/ubb/client.py ubb-sdk/tests/test_retry.py
git commit -m "feat: wire retry logic into all SDK product clients"
```

---

## Chunk 2: API Rate Limiting — Core Module

### Task 5: Add `rate_limit_per_second` field to Tenant model

**Files:**
- Modify: `ubb-platform/apps/platform/tenants/models.py:19` (after `min_balance_micros`)
- Create: `ubb-platform/apps/platform/tenants/migrations/0008_add_rate_limit_field.py`

- [ ] **Step 1: Write the failing test**

Create `ubb-platform/core/tests/test_rate_limit.py`:

```python
"""Tests for API rate limiting."""
import pytest
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantRateLimitField:
    def test_rate_limit_field_defaults_to_none(self):
        tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering"],
        )
        assert tenant.rate_limit_per_second is None

    def test_rate_limit_field_can_be_set(self):
        tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering"],
            rate_limit_per_second=1000,
        )
        tenant.refresh_from_db()
        assert tenant.rate_limit_per_second == 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_rate_limit.py::TestTenantRateLimitField -v`
Expected: FAIL — `Tenant` has no field `rate_limit_per_second`

- [ ] **Step 3: Write minimal implementation**

Edit `ubb-platform/apps/platform/tenants/models.py` — add field after line 19 (`min_balance_micros`):

```python
    rate_limit_per_second = models.BigIntegerField(null=True, blank=True)
```

Generate and check migration:

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tenants --name add_rate_limit_field
```

This creates `apps/platform/tenants/migrations/0008_add_rate_limit_field.py`.

- [ ] **Step 4: Run migration and test**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate tenants
```

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_rate_limit.py::TestTenantRateLimitField -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add apps/platform/tenants/models.py apps/platform/tenants/migrations/0008_add_rate_limit_field.py core/tests/test_rate_limit.py
git commit -m "feat: add rate_limit_per_second field to Tenant model"
```

---

### Task 6: Implement Lua script and global rate limit middleware

**Files:**
- Create: `ubb-platform/core/rate_limit.py`
- Test: `ubb-platform/core/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing tests**

Append to `ubb-platform/core/tests/test_rate_limit.py`:

```python
from unittest.mock import patch, MagicMock
from django.test import RequestFactory, override_settings
import json
import time


class TestGlobalRateLimitMiddleware:
    """Tests for GlobalRateLimitMiddleware."""

    def setup_method(self):
        self.factory = RequestFactory()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_allows_request_under_limit(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware

        mock_redis = MagicMock()
        mock_redis.evalsha.return_value = 5  # under limit of 10
        mock_get_redis.return_value = mock_redis

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/metering/usage")
        response = middleware(request)
        assert response.status_code == 200
        get_response.assert_called_once()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_returns_429_when_over_limit(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware

        mock_redis = MagicMock()
        mock_redis.evalsha.return_value = 11  # over limit of 10
        mock_get_redis.return_value = mock_redis

        get_response = MagicMock()
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/metering/usage")
        response = middleware(request)
        assert response.status_code == 429
        body = json.loads(response.content)
        assert body["error"] == "rate_limited"
        assert response["Retry-After"] == "1"
        get_response.assert_not_called()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_skips_health_endpoint(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/health")
        response = middleware(request)
        assert response.status_code == 200
        mock_get_redis.assert_not_called()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_skips_ready_endpoint(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/ready")
        response = middleware(request)
        assert response.status_code == 200
        mock_get_redis.assert_not_called()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_skips_stripe_webhook(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.post("/api/v1/webhooks/stripe")
        response = middleware(request)
        assert response.status_code == 200
        mock_get_redis.assert_not_called()

    @override_settings(UBB_GLOBAL_RATE_LIMIT=10)
    @patch("core.rate_limit._get_redis")
    def test_fail_open_when_redis_unavailable(self, mock_get_redis):
        from core.rate_limit import GlobalRateLimitMiddleware
        import redis as redis_lib

        mock_get_redis.side_effect = redis_lib.ConnectionError("Redis down")

        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = GlobalRateLimitMiddleware(get_response)
        request = self.factory.get("/api/v1/metering/usage")
        response = middleware(request)
        assert response.status_code == 200  # fail open
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_rate_limit.py::TestGlobalRateLimitMiddleware -v`
Expected: FAIL — `core.rate_limit` module does not exist

- [ ] **Step 3: Write minimal implementation**

Create `ubb-platform/core/rate_limit.py`:

```python
"""API rate limiting: global middleware + per-tenant dependency.

Uses Redis fixed-window counters with atomic Lua script.
Fails open if Redis is unavailable.
"""
from __future__ import annotations

import json
import logging
import time

import redis
from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger("core.rate_limit")

# Lua script: atomic INCR + conditional EXPIRE
_LUA_INCR_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

_SKIP_PATHS = {
    "/api/v1/health",
    "/api/v1/ready",
    "/api/v1/webhooks/stripe",              # Stripe billing webhook (external)
    "/api/v1/subscriptions/webhooks/stripe", # Stripe subscriptions webhook (external)
}

_redis_client = None
_lua_sha = None


def _get_redis():
    """Get or create a Redis client from settings.REDIS_URL."""
    global _redis_client, _lua_sha
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        _lua_sha = _redis_client.script_load(_LUA_INCR_SCRIPT)
    return _redis_client


def _incr_counter(key: str, window_seconds: int = 2) -> int:
    """Atomically increment a counter and set expiry. Returns new count.

    TTL is 2s (not 1s) as a safety margin — ensures the key outlives the
    1-second window even with minor clock skew or Redis lag.
    """
    r = _get_redis()
    return r.evalsha(_lua_sha, 1, key, window_seconds)


class GlobalRateLimitMiddleware:
    """Pre-auth rate limit on all inbound requests.

    Uses a 1-second fixed window. Returns 429 if global limit exceeded.
    Skips health/ready endpoints. Fails open if Redis is unavailable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in _SKIP_PATHS:
            return self.get_response(request)

        limit = getattr(settings, "UBB_GLOBAL_RATE_LIMIT", 5000)
        try:
            window_ts = int(time.time())
            key = f"ratelimit:global:{window_ts}"
            count = _incr_counter(key)
        except Exception:
            logger.warning("Redis unavailable for global rate limit — failing open")
            return self.get_response(request)

        if count > limit:
            return JsonResponse(
                {"error": "rate_limited", "detail": "Global rate limit exceeded"},
                status=429,
                headers={"Retry-After": "1"},
            )

        return self.get_response(request)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_rate_limit.py::TestGlobalRateLimitMiddleware -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add core/rate_limit.py core/tests/test_rate_limit.py
git commit -m "feat: add GlobalRateLimitMiddleware with Lua atomic counter"
```

---

### Task 7: Implement per-tenant rate limit dependency

**Files:**
- Modify: `ubb-platform/core/rate_limit.py`
- Test: `ubb-platform/core/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing tests**

Append to `ubb-platform/core/tests/test_rate_limit.py`:

```python
from ninja.errors import HttpError


@pytest.mark.django_db
class TestPerTenantRateLimit:
    """Tests for RateLimit dependency."""

    def setup_method(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering"],
        )

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_high_tier_uses_full_limit(self, mock_incr):
        from core.rate_limit import RateLimit

        mock_incr.return_value = 50  # under limit of 100
        dep = RateLimit("high")
        request = self.factory.get("/api/v1/metering/usage")
        request.tenant = self.tenant
        dep(request)  # should not raise
        key_arg = mock_incr.call_args[0][0]
        assert f"ratelimit:tenant:{self.tenant.id}:" in key_arg

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_standard_tier_uses_20_percent(self, mock_incr):
        from core.rate_limit import RateLimit

        mock_incr.return_value = 21  # over 20% of 100 = 20
        dep = RateLimit("standard")
        request = self.factory.get("/api/v1/platform/customers")
        request.tenant = self.tenant
        with pytest.raises(HttpError) as exc_info:
            dep(request)
        assert exc_info.value.status_code == 429
        assert request.rate_limit_exceeded is True

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_tenant_override_respected(self, mock_incr):
        from core.rate_limit import RateLimit

        self.tenant.rate_limit_per_second = 200
        self.tenant.save()
        mock_incr.return_value = 150  # over default 100 but under override 200
        dep = RateLimit("high")
        request = self.factory.get("/api/v1/metering/usage")
        request.tenant = self.tenant
        dep(request)  # should not raise — using override of 200

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_standard_tier_minimum_is_1(self, mock_incr):
        from core.rate_limit import RateLimit

        self.tenant.rate_limit_per_second = 3  # 3 // 5 = 0, but min is 1
        self.tenant.save()
        mock_incr.return_value = 1  # at limit of 1
        dep = RateLimit("standard")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        dep(request)  # should not raise — count == limit

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_stores_rate_limit_info_on_request(self, mock_incr):
        from core.rate_limit import RateLimit

        mock_incr.return_value = 30
        dep = RateLimit("high")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        dep(request)
        assert hasattr(request, "rate_limit_info")
        assert request.rate_limit_info["limit"] == 100
        assert request.rate_limit_info["remaining"] == 70

    @override_settings(UBB_TENANT_RATE_LIMIT=100)
    @patch("core.rate_limit._incr_counter")
    def test_fail_open_when_redis_unavailable(self, mock_incr):
        from core.rate_limit import RateLimit

        mock_incr.side_effect = Exception("Redis down")
        dep = RateLimit("high")
        request = self.factory.get("/test")
        request.tenant = self.tenant
        dep(request)  # should not raise — fail open
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_rate_limit.py::TestPerTenantRateLimit -v`
Expected: FAIL — `RateLimit` not found in `core.rate_limit`

- [ ] **Step 3: Write minimal implementation**

Append to `ubb-platform/core/rate_limit.py`:

```python
from ninja.errors import HttpError


class RateLimit:
    """Per-tenant rate limit dependency for django-ninja endpoints.

    Usage:
        _rate_limit = RateLimit("high")    # full tenant limit
        _rate_limit = RateLimit("standard")  # 20% of tenant limit

    Stores rate limit info on request for header injection by
    RateLimitHeaderMiddleware.
    """

    def __init__(self, tier: str = "standard"):
        if tier not in ("high", "standard"):
            raise ValueError(f"Invalid tier: {tier}")
        self.tier = tier

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return  # unauthenticated — skip

        base_limit = tenant.rate_limit_per_second or getattr(
            settings, "UBB_TENANT_RATE_LIMIT", 500
        )
        if self.tier == "high":
            limit = base_limit
        else:
            limit = max(1, base_limit // 5)

        window_ts = int(time.time())
        key = f"ratelimit:tenant:{tenant.id}:{window_ts}"

        try:
            count = _incr_counter(key)
        except Exception:
            logger.warning(
                "Redis unavailable for tenant rate limit — failing open",
                extra={"tenant_id": str(tenant.id)},
            )
            return

        remaining = max(0, limit - count)
        reset_ts = window_ts + 1

        # Store on request for header middleware
        request.rate_limit_info = {
            "limit": limit,
            "remaining": remaining,
            "reset": reset_ts,
        }

        if count > limit:
            # Store exceeded flag for header middleware to add Retry-After
            request.rate_limit_exceeded = True
            raise HttpError(429, "Rate limit exceeded")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_rate_limit.py::TestPerTenantRateLimit -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add core/rate_limit.py core/tests/test_rate_limit.py
git commit -m "feat: add RateLimit per-tenant dependency"
```

---

### Task 8: Implement rate limit response header middleware

**Files:**
- Modify: `ubb-platform/core/rate_limit.py`
- Test: `ubb-platform/core/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing tests**

Append to `ubb-platform/core/tests/test_rate_limit.py`:

```python
class TestRateLimitHeaderMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()

    def test_injects_headers_when_rate_limit_info_present(self):
        from core.rate_limit import RateLimitHeaderMiddleware

        response = MagicMock(status_code=200)
        response.__setitem__ = MagicMock()
        get_response = MagicMock(return_value=response)
        middleware = RateLimitHeaderMiddleware(get_response)

        request = self.factory.get("/test")
        request.rate_limit_info = {
            "limit": 500,
            "remaining": 450,
            "reset": 1710000001,
        }
        result = middleware(request)
        response.__setitem__.assert_any_call("X-RateLimit-Limit", "500")
        response.__setitem__.assert_any_call("X-RateLimit-Remaining", "450")
        response.__setitem__.assert_any_call("X-RateLimit-Reset", "1710000001")

    def test_no_headers_when_no_rate_limit_info(self):
        from core.rate_limit import RateLimitHeaderMiddleware

        response = MagicMock(status_code=200)
        response.__setitem__ = MagicMock()
        get_response = MagicMock(return_value=response)
        middleware = RateLimitHeaderMiddleware(get_response)

        request = self.factory.get("/test")
        result = middleware(request)
        response.__setitem__.assert_not_called()

    def test_retry_after_header_on_429(self):
        from core.rate_limit import RateLimitHeaderMiddleware

        response = MagicMock(status_code=429)
        response.__setitem__ = MagicMock()
        get_response = MagicMock(return_value=response)
        middleware = RateLimitHeaderMiddleware(get_response)

        request = self.factory.get("/test")
        request.rate_limit_exceeded = True
        result = middleware(request)
        response.__setitem__.assert_any_call("Retry-After", "1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_rate_limit.py::TestRateLimitHeaderMiddleware -v`
Expected: FAIL — `RateLimitHeaderMiddleware` not found

- [ ] **Step 3: Write minimal implementation**

Append to `ubb-platform/core/rate_limit.py`:

```python
class RateLimitHeaderMiddleware:
    """Injects X-RateLimit-* headers on responses.

    Reads rate_limit_info stored on request by the RateLimit dependency.
    Must be placed AFTER authentication middleware in the middleware stack.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        info = getattr(request, "rate_limit_info", None)
        if info:
            response["X-RateLimit-Limit"] = str(info["limit"])
            response["X-RateLimit-Remaining"] = str(info["remaining"])
            response["X-RateLimit-Reset"] = str(info["reset"])
        # Add Retry-After on per-tenant 429s
        if response.status_code == 429 and getattr(request, "rate_limit_exceeded", False):
            response["Retry-After"] = "1"
        return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_rate_limit.py::TestRateLimitHeaderMiddleware -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add core/rate_limit.py core/tests/test_rate_limit.py
git commit -m "feat: add RateLimitHeaderMiddleware for response headers"
```

---

## Chunk 3: Wiring Rate Limiting + Deployment Config

### Task 9: Add settings and register middleware

**Files:**
- Modify: `ubb-platform/config/settings.py`

- [ ] **Step 1: Add rate limit defaults and middleware**

Edit `config/settings.py`:

1. Add to MIDDLEWARE list — `GlobalRateLimitMiddleware` goes right after `CorrelationIdMiddleware` (position 2), and `RateLimitHeaderMiddleware` goes at the end:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.CorrelationIdMiddleware",
    "core.rate_limit.GlobalRateLimitMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.rate_limit.RateLimitHeaderMiddleware",
]
```

2. Add rate limit defaults after the `REDIS_URL` / cache section (after line 115):

```python
# Rate limiting defaults
UBB_GLOBAL_RATE_LIMIT = int(os.environ.get("UBB_GLOBAL_RATE_LIMIT", "5000"))
UBB_TENANT_RATE_LIMIT = int(os.environ.get("UBB_TENANT_RATE_LIMIT", "500"))
```

3. Add timeout and pooling config at the end of the file:

```python
# Request timeout — documented here, enforced by Gunicorn/Nginx/Render
UBB_REQUEST_TIMEOUT_SECONDS = 30

# Connection pooling: set USE_PGBOUNCER=true when behind PgBouncer
if os.environ.get("USE_PGBOUNCER", "").lower() == "true":
    DATABASES["default"]["CONN_MAX_AGE"] = 0
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = False
```

- [ ] **Step 2: Run all platform tests to verify settings don't break anything**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add config/settings.py
git commit -m "feat: add rate limit settings, middleware registration, deployment config"
```

---

### Task 10: Wire RateLimit dependency into all endpoint files

**Files:**
- Modify: `ubb-platform/api/v1/metering_endpoints.py`
- Modify: `ubb-platform/api/v1/billing_endpoints.py`
- Modify: `ubb-platform/api/v1/endpoints.py`
- Modify: `ubb-platform/api/v1/platform_endpoints.py`
- Modify: `ubb-platform/api/v1/tenant_endpoints.py`
- Modify: `ubb-platform/apps/subscriptions/api/endpoints.py`
- Modify: `ubb-platform/apps/referrals/api/endpoints.py`
- Modify: `ubb-platform/apps/platform/events/api/webhook_endpoints.py`

- [ ] **Step 1: Wire high-tier endpoints**

**`api/v1/metering_endpoints.py`** — add import and instantiation near the top (after `_product_check`):

```python
from core.rate_limit import RateLimit

_rate_limit_high = RateLimit("high")
```

Then add `_rate_limit_high(request)` as the first line of:
- `record_usage()` (POST /usage) — high throughput endpoint
- `close_run()` (POST /runs/{run_id}/close) — high throughput endpoint

And add a standard rate limit for remaining endpoints:
```python
_rate_limit_std = RateLimit("standard")
```
Call `_rate_limit_std(request)` in `get_usage()`, `get_analytics()`, provider rate endpoints, etc.

**`api/v1/billing_endpoints.py`** — same pattern:

```python
from core.rate_limit import RateLimit

_rate_limit_high = RateLimit("high")
_rate_limit_std = RateLimit("standard")
```

- `pre_check()` (POST /pre-check) → `_rate_limit_high(request)`
- All other billing endpoints → `_rate_limit_std(request)`

- [ ] **Step 2: Wire standard-tier endpoints**

For all remaining endpoint files, add:

```python
from core.rate_limit import RateLimit

_rate_limit = RateLimit("standard")
```

Then add `_rate_limit(request)` as the first line of each endpoint function in:
- `api/v1/endpoints.py` — skip `health` and `ready` (they have `auth=None` and won't have `request.tenant`)
- `api/v1/platform_endpoints.py`
- `api/v1/tenant_endpoints.py`
- `apps/subscriptions/api/endpoints.py`
- `apps/referrals/api/endpoints.py`
- `apps/platform/events/api/webhook_endpoints.py`

**Important:** The `RateLimit` dependency checks `getattr(request, "tenant", None)` and returns early if None, so it's safe to call on all endpoints including unauthenticated ones.

**Note:** `api/v1/me_endpoints.py` is intentionally excluded — it uses `WidgetJWTAuth` which sets `request.widget_tenant`, not `request.tenant`. Widget rate limiting can be added as a follow-up if needed. Stripe webhook views (`api/v1/webhooks.py`, `apps/subscriptions/api/stripe_webhook.py`) are also excluded — they use Stripe signature verification and are already covered by the global rate limit with skip paths for the webhook URLs.

- [ ] **Step 3: Run all platform tests**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All tests pass (RateLimit's `_incr_counter` will fail in tests without Redis, but it fails open so tests should still pass)

- [ ] **Step 4: Commit**

```bash
git add api/v1/metering_endpoints.py api/v1/billing_endpoints.py api/v1/endpoints.py api/v1/platform_endpoints.py api/v1/tenant_endpoints.py apps/subscriptions/api/endpoints.py apps/referrals/api/endpoints.py apps/platform/events/api/webhook_endpoints.py
git commit -m "feat: wire RateLimit dependency into all API endpoints"
```

---

### Task 11: Final integration — run full test suite

**Files:** None — verification only.

- [ ] **Step 1: Run full platform test suite**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

Expected: All tests pass

- [ ] **Step 2: Run full SDK test suite**

```bash
cd ubb-sdk && python -m pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 3: Verify migration applies cleanly**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate --check
```

Expected: No unapplied migrations

- [ ] **Step 4: Final commit if any fixups needed**

Only if tests revealed issues that needed fixing.
