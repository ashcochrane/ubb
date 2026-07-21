"""Shared HTTP error handling for the shell's product clients.

The shell owns transport (decision #65): retry policy, connection-error mapping,
and turning an RFC 9457 problem+json (#78) into the generated per-code exception
hierarchy all live here, so ``MeteringClient`` and ``BillingClient`` share one
implementation instead of two copies that can drift.
"""

from __future__ import annotations

import httpx

from ubb.exceptions import UBBAuthError
from ubb._exceptions_generated import exception_for


def extract_problem(response: httpx.Response) -> tuple[str | None, str]:
    """``(code, detail)`` from a problem+json body (#78); falls back to
    ``(None, raw text)`` for anything that is not a problem document."""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("title") or response.text
            return body.get("code"), detail
    except Exception:
        pass
    return None, response.text


def raise_for_status(response: httpx.Response) -> None:
    """Raise the most specific exception for an error response, or return.

    401 maps to the hand-owned ``UBBAuthError`` (auth is special and predates the
    registry); every other 4xx/5xx maps through ``exception_for`` to a per-code
    leaf, its status family, or a bare ``UBBAPIError``. A ``Retry-After`` header
    rides onto the exception so the retry policy can honour it.
    """
    status = response.status_code
    if status == 401:
        raise UBBAuthError("Invalid or revoked API key")
    if status < 400:
        return
    code, detail = extract_problem(response)
    exc = exception_for(status, code, detail)
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            exc.retry_after = float(retry_after)
        except (ValueError, TypeError):
            pass
    raise exc
