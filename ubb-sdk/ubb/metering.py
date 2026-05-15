from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
    UBBHardStopError, UBBRunNotActiveError,
)
from ubb.retry import request_with_retry
from ubb.types import (
    RecordUsageResult, CloseRunResult, UsageEvent, UsageAnalyticsResult,
    PaginatedResponse,
)


class MeteringClient:
    """Product-specific client for the UBB Metering API (/api/v1/metering/)."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, max_retries: int = 3) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
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

    def record_usage(
        self,
        customer_id: str,
        request_id: str,
        idempotency_key: str,
        pricing_card: str,
        usage_metrics: dict,
        group: str | None = None,
        run_id: str | None = None,
    ) -> RecordUsageResult:
        """Record a usage event via POST /api/v1/metering/usage.

        Pricing is resolved by the server via the pricing_card slug. The server
        looks up the tenant's Card by slug and applies the stored per-metric rates.
        """
        body: dict = {
            "customerId": customer_id,
            "requestId": request_id,
            "idempotencyKey": idempotency_key,
            "pricingCard": pricing_card,
            "usageMetrics": usage_metrics,
        }
        if group is not None:
            body["group"] = group
        if run_id is not None:
            body["runId"] = run_id
        r = self._request_usage("post", "/api/v1/metering/usage", json=body)
        body = r.json()
        return RecordUsageResult(
            event_id=body.get("eventId", ""),
            provider_cost_micros=body.get("providerCostMicros"),
            billed_cost_micros=body.get("billedCostMicros"),
            run_id=body.get("runId"),
            run_total_cost_micros=body.get("runTotalCostMicros"),
            hard_stop=body.get("hardStop", False),
        )

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
            if body.get("hardStop"):
                raise UBBHardStopError(
                    run_id=body.get("runId", ""),
                    reason=body.get("reason", ""),
                    total_cost_micros=body.get("totalCostMicros", 0),
                )
            # Regular 429 (rate limited)
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
                    run_id=body.get("runId", ""),
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

    def close_run(self, run_id: str) -> CloseRunResult:
        """Close (complete) a run via POST /api/v1/metering/runs/{run_id}/close."""
        r = self._request("post", f"/api/v1/metering/runs/{run_id}/close")
        body = r.json()
        return CloseRunResult(
            run_id=body.get("runId", ""),
            status=body.get("status", ""),
            total_cost_micros=body.get("totalCostMicros", 0),
            event_count=body.get("eventCount", 0),
        )

    def get_usage(self, customer_id: str, cursor: str | None = None, limit: int = 20,
                  group: str | None = None) -> PaginatedResponse[UsageEvent]:
        """Get usage history via GET /api/v1/metering/customers/{customer_id}/usage."""
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if group is not None:
            params["group"] = group
        r = self._request("get", f"/api/v1/metering/customers/{customer_id}/usage", params=params)
        body = r.json()
        events = [
            UsageEvent(
                id=str(item["id"]),
                request_id=item["requestId"],
                cost_micros=item["costMicros"],
                effective_at=item["effectiveAt"],
                card_slug=item.get("cardSlug", ""),
                card_name=item.get("cardName", ""),
                provider=item.get("provider", ""),
                provider_cost_micros=item.get("providerCostMicros"),
                billed_cost_micros=item.get("billedCostMicros"),
            )
            for item in body["data"]
        ]
        return PaginatedResponse(data=events, next_cursor=body.get("nextCursor"), has_more=body["hasMore"])

    def get_usage_analytics(self, start_date: str | None = None,
                            end_date: str | None = None) -> UsageAnalyticsResult:
        """Get usage analytics via GET /api/v1/metering/analytics/usage."""
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        r = self._request("get", "/api/v1/metering/analytics/usage", params=params)
        body = r.json()
        return UsageAnalyticsResult(
            total_events=body["totalEvents"],
            total_billed_cost_micros=body["totalBilledCostMicros"],
            total_provider_cost_micros=body["totalProviderCostMicros"],
            by_provider=body["byProvider"],
            by_card=body["byCard"],
        )

    def close(self) -> None:
        self._http.close()
