"""Behaviour pins for the registry-derived exception hierarchy (issue #84).

The per-code classes are generated from openapi/error-codes.json; the CI ratchet
guarantees the file matches the registry. These tests pin the *behaviour* the
wrap promises: a caller can catch a whole status family or one exact registry
code, everything stays an ``UBBAPIError``, and the transport maps a problem+json
to the most specific class.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from ubb.exceptions import (
    UBBAPIError,
    UBBAuthError,
    UBBConflictError,
    UBBValidationError,
    ConflictError,
    InsufficientBalanceError,
    WouldOverdrawError,
    UnprocessableEntityError,
    ValidationError,
    NotFoundError,
    RateLimitError,
    exception_for,
)
from ubb._http import raise_for_status

REGISTRY = json.loads(
    (Path(__file__).resolve().parents[2] / "openapi" / "error-codes.json").read_text()
)


class TestCatchByFamilyOrCode:
    def test_specific_code_is_catchable_as_leaf_family_and_base(self):
        exc = exception_for(409, "insufficient_balance", "no funds")
        assert isinstance(exc, InsufficientBalanceError)  # exact code
        assert isinstance(exc, ConflictError)  # status family
        assert isinstance(exc, UBBAPIError)  # base
        assert exc.status_code == 409
        assert exc.code == "insufficient_balance"

    def test_two_conflict_codes_share_a_family(self):
        a = exception_for(409, "insufficient_balance", "")
        b = exception_for(409, "would_overdraw", "")
        assert isinstance(a, ConflictError) and isinstance(b, ConflictError)
        assert type(a) is InsufficientBalanceError and type(b) is WouldOverdrawError

    def test_ubbconflicterror_alias_still_works(self):
        exc = exception_for(409, "currency_locked", "")
        assert isinstance(exc, UBBConflictError)  # legacy name, now == ConflictError

    def test_server_validation_error_is_not_client_validation_error(self):
        exc = exception_for(422, "validation_error", "")
        assert isinstance(exc, ValidationError)
        assert isinstance(exc, UnprocessableEntityError)
        assert not isinstance(exc, UBBValidationError)  # client-side input error


class TestFallbacks:
    def test_unknown_code_falls_back_to_status_family(self):
        exc = exception_for(422, "a_code_added_next_year", "")
        assert type(exc) is UnprocessableEntityError
        assert exc.code == "a_code_added_next_year"  # honest: no fabrication

    def test_missing_code_uses_family_default_code(self):
        exc = exception_for(409, None, "conflict")
        assert type(exc) is ConflictError
        assert exc.code == "conflict"

    def test_undocumented_status_is_bare_apierror(self):
        exc = exception_for(418, None, "teapot")
        assert type(exc) is UBBAPIError
        assert exc.status_code == 418


class TestEveryRegistryCodeMaps:
    def test_all_non_401_codes_resolve_to_an_apierror(self):
        for code, meta in REGISTRY["problems"].items():
            status = meta["status"]
            if status == 401:
                continue  # owned by UBBAuthError
            exc = exception_for(status, code, "")
            assert isinstance(exc, UBBAPIError)
            assert exc.status_code == status


def _response(status: int, body: dict | None = None, headers: dict | None = None):
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.headers = headers or {}
    r.text = json.dumps(body) if body else ""
    r.json = MagicMock(return_value=body if body is not None else {})
    return r


class TestRaiseForStatus:
    def test_maps_problem_to_specific_exception(self):
        resp = _response(409, {"code": "would_overdraw", "detail": "below floor"})
        with pytest.raises(WouldOverdrawError) as ei:
            raise_for_status(resp)
        assert ei.value.detail == "below floor"

    def test_401_is_auth_error(self):
        with pytest.raises(UBBAuthError):
            raise_for_status(_response(401))

    def test_retry_after_rides_the_exception(self):
        resp = _response(429, {"code": "rate_limit_exceeded"}, headers={"Retry-After": "2.5"})
        with pytest.raises(RateLimitError) as ei:
            raise_for_status(resp)
        assert ei.value.retry_after == 2.5

    def test_2xx_does_not_raise(self):
        assert raise_for_status(_response(200)) is None
