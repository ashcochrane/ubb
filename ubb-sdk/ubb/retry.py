"""Shared retry logic for UBB SDK clients.

Exponential backoff with jitter, matching the platform's stripe_service.py pattern:
- Base: 0.5s * 2^attempt
- Jitter: +/-25%
- Max delay: 10s
"""
from __future__ import annotations

import logging
import random
import time

from ubb.exceptions import (
    UBBConnectionError, UBBAPIError, UBBHardStopError, UBBRunNotActiveError,
)

logger = logging.getLogger("ubb.retry")

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
    raise last_error  # pragma: no cover
