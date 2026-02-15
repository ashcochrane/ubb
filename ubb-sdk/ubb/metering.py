from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
    UBBHardStopError, UBBRunNotActiveError,
)
from ubb.types import RecordUsageResult, CloseRunResult, UsageEvent, PaginatedResponse


class MeteringClient:
    """Product-specific client for the UBB Metering API (/api/v1/metering/)."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self) -> MeteringClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- internal request helper (same pattern as UBBClient) ----

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
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
            raise UBBAPIError(response.status_code, detail)
        return response

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """Parse JSON error body if available, fallback to raw text."""
        try:
            body = response.json()
            if isinstance(body, dict) and "error" in body:
                return body["error"]
            if isinstance(body, dict) and "detail" in body:
                return body["detail"]
        except Exception:
            pass
        return response.text

    # ---- public API ----

    def record_usage(self, customer_id: str, request_id: str, idempotency_key: str,
                     cost_micros: int | None = None, metadata: dict | None = None,
                     event_type: str | None = None, provider: str | None = None,
                     usage_metrics: dict | None = None, properties: dict | None = None,
                     group_keys: dict | None = None,
                     run_id: str | None = None) -> RecordUsageResult:
        """Record a usage event via POST /api/v1/metering/usage."""
        body: dict = {
            "customer_id": customer_id,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "metadata": metadata or {},
        }
        if cost_micros is not None:
            body["cost_micros"] = cost_micros
        if usage_metrics is not None:
            body["event_type"] = event_type
            body["provider"] = provider
            body["usage_metrics"] = usage_metrics
            if properties:
                body["properties"] = properties
        if group_keys is not None:
            body["group_keys"] = group_keys
        if run_id is not None:
            body["run_id"] = run_id
        r = self._request_usage("post", "/api/v1/metering/usage", json=body)
        return RecordUsageResult(**r.json())

    def _request_usage(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Like _request but handles run-specific error codes."""
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
            raise UBBAPIError(response.status_code, detail)
        return response

    def close_run(self, run_id: str) -> CloseRunResult:
        """Close (complete) a run via POST /api/v1/metering/runs/{run_id}/close."""
        r = self._request("post", f"/api/v1/metering/runs/{run_id}/close")
        return CloseRunResult(**r.json())

    def get_usage(self, customer_id: str, cursor: str | None = None, limit: int = 20,
                  group_key: str | None = None, group_value: str | None = None) -> PaginatedResponse[UsageEvent]:
        """Get usage history via GET /api/v1/metering/customers/{customer_id}/usage."""
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if group_key is not None:
            params["group_key"] = group_key
        if group_value is not None:
            params["group_value"] = group_value
        r = self._request("get", f"/api/v1/metering/customers/{customer_id}/usage", params=params)
        body = r.json()
        events = [UsageEvent(**item) for item in body["data"]]
        return PaginatedResponse(data=events, next_cursor=body.get("next_cursor"), has_more=body["has_more"])

    def close(self) -> None:
        self._http.close()
