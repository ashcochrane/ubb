from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
    UBBHardStopError, UBBRunNotActiveError,
)
from ubb.types import (
    RecordUsageResult, CloseRunResult, UsageEvent, PaginatedResponse,
    CustomerMargin, DimensionMargin, MarginTrendPoint, CustomerRevenue,
    RateCard,
)


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

    def record_usage(self, customer_id: str, request_id: str, idempotency_key: str, *,
                     provider_cost_micros: int | None = None, billed_cost_micros: int | None = None,
                     units: int | None = None, provider: str = "", event_type: str = "",
                     currency: str | None = None, tags: dict | None = None,
                     product_id: str = "", metadata: dict | None = None,
                     run_id: str | None = None,
                     usage_metrics: dict | None = None) -> RecordUsageResult:
        """Record a usage event via POST /api/v1/metering/usage."""
        body: dict = {
            "customer_id": customer_id,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "metadata": metadata or {},
        }
        if provider_cost_micros is not None:
            body["provider_cost_micros"] = provider_cost_micros
        if usage_metrics is not None:
            body["usage_metrics"] = usage_metrics
        if billed_cost_micros is not None:
            body["billed_cost_micros"] = billed_cost_micros
        if units is not None:
            body["units"] = units
        if currency is not None:
            body["currency"] = currency
        if tags is not None:
            body["tags"] = tags
        if product_id:
            body["product_id"] = product_id
        if event_type:
            body["event_type"] = event_type
        if provider:
            body["provider"] = provider
        if run_id is not None:
            body["run_id"] = run_id
        r = self._request_usage("post", "/api/v1/metering/usage", json=body)
        data = r.json()
        return RecordUsageResult(**{k: v for k, v in data.items()
                                    if k in RecordUsageResult.__dataclass_fields__})

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
                  tag_key: str | None = None, tag_value: str | None = None) -> PaginatedResponse[UsageEvent]:
        """Get usage history via GET /api/v1/metering/customers/{customer_id}/usage."""
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if tag_key is not None:
            params["tag_key"] = tag_key
        if tag_value is not None:
            params["tag_value"] = tag_value
        r = self._request("get", f"/api/v1/metering/customers/{customer_id}/usage", params=params)
        body = r.json()
        events = [UsageEvent(**item) for item in body["data"]]
        return PaginatedResponse(data=events, next_cursor=body.get("next_cursor"), has_more=body["has_more"])

    def get_customer_margin(self, customer_id, start_date=None, end_date=None):
        params = {k: v for k, v in {"start_date": start_date, "end_date": end_date}.items() if v}
        r = self._request("get", f"/api/v1/margin/{customer_id}", params=params)
        return CustomerMargin(**{k: v for k, v in r.json().items()
                                 if k in CustomerMargin.__dataclass_fields__})

    def get_margin_by_dimension(self, *, provider=False, product=False, tag_key=None,
                                start_date=None, end_date=None):
        params = {}
        if provider:
            params["provider"] = 1
        if product:
            params["product"] = 1
        if tag_key:
            params["tag_key"] = tag_key
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        r = self._request("get", "/api/v1/margin/by-dimension", params=params)
        return [DimensionMargin(**row) for row in r.json()["rows"]]

    def get_unprofitable_customers(self, period_start=None):
        params = {"period_start": period_start} if period_start else {}
        r = self._request("get", "/api/v1/margin/unprofitable", params=params)
        return r.json()["customers"]

    def get_margin_trend(self, customer_id, periods=6):
        r = self._request("get", f"/api/v1/margin/{customer_id}/trend", params={"periods": periods})
        return [MarginTrendPoint(**p) for p in r.json()["points"]]

    def set_customer_revenue(self, customer_id, recurring_amount_micros, interval="month",
                             currency="usd", effective_from=None, effective_to=None):
        body = {"recurring_amount_micros": recurring_amount_micros, "interval": interval,
                "currency": currency}
        if effective_from:
            body["effective_from"] = effective_from
        if effective_to:
            body["effective_to"] = effective_to
        r = self._request("put", f"/api/v1/margin/customers/{customer_id}/revenue", json=body)
        return CustomerRevenue(**r.json())

    def get_customer_revenue(self, customer_id):
        r = self._request("get", f"/api/v1/margin/customers/{customer_id}/revenue")
        return CustomerRevenue(**r.json())

    def get_business_margin(self, external_id, start_date=None, end_date=None):
        params = {k: v for k, v in {"start_date": start_date, "end_date": end_date}.items() if v}
        r = self._request("get", f"/api/v1/margin/business/{external_id}", params=params)
        return r.json()

    def set_revenue_mode(self, customer_id, revenue_mode=""):
        r = self._request("put", f"/api/v1/margin/customers/{customer_id}/revenue-mode",
                          json={"revenue_mode": revenue_mode})
        return r.json()

    def get_revenue_mode(self, customer_id):
        r = self._request("get", f"/api/v1/margin/customers/{customer_id}/revenue-mode")
        return r.json()

    @staticmethod
    def _rate_card(row):
        return RateCard(**{k: v for k, v in row.items()
                           if k in RateCard.__dataclass_fields__})

    def create_rate_card(self, *, card_type, metric_name, provider="", event_type="",
                         dimensions=None, pricing_model="per_unit", rate_per_unit_micros=0,
                         unit_quantity=1_000_000, fixed_micros=0, currency="usd",
                         product_id="", customer_id=None):
        body = {"card_type": card_type, "metric_name": metric_name, "provider": provider,
                "event_type": event_type, "dimensions": dimensions or {}, "pricing_model": pricing_model,
                "rate_per_unit_micros": rate_per_unit_micros, "unit_quantity": unit_quantity,
                "fixed_micros": fixed_micros, "currency": currency, "product_id": product_id,
                "customer_id": customer_id}
        r = self._request("post", "/api/v1/metering/pricing/rate-cards", json=body)
        return self._rate_card(r.json())

    def update_rate_card(self, card_id, **fields):
        """Soft-version a rate card via PUT. Only the provided ``fields`` change;
        unspecified fields are copied from the active version. Returns the new
        version (same ``lineage_id``, new ``id``)."""
        r = self._request("put", f"/api/v1/metering/pricing/rate-cards/{card_id}", json=fields)
        return self._rate_card(r.json())

    def get_rate_card_history(self, lineage_id):
        """Return every version sharing ``lineage_id``, newest first."""
        r = self._request("get", f"/api/v1/metering/pricing/rate-cards/{lineage_id}/history")
        return [self._rate_card(row) for row in r.json()]

    def list_rate_cards(self, card_type=None, include_history=False, as_of=None):
        params = {}
        if card_type:
            params["card_type"] = card_type
        if include_history:
            params["include_history"] = include_history
        if as_of is not None:
            params["as_of"] = as_of
        r = self._request("get", "/api/v1/metering/pricing/rate-cards", params=params or None)
        return [self._rate_card(row) for row in r.json()]

    def bulk_create_rate_cards(self, cards: list[dict]) -> dict:
        """Atomically create multiple rate cards via POST /api/v1/metering/pricing/rate-cards/batch.

        All cards are validated before any are created; if any card is invalid the
        entire batch is rejected (no partial writes).  Returns a dict with ``created``
        (list of new card IDs) and ``count``.
        """
        r = self._request("post", "/api/v1/metering/pricing/rate-cards/batch",
                          json={"cards": cards})
        return r.json()

    def delete_rate_card(self, card_id):
        self._request("delete", f"/api/v1/metering/pricing/rate-cards/{card_id}")
        return True

    def usage_timeseries(self, *, granularity="day", start_date=None, end_date=None,
                         customer_id=None, group_by=None) -> dict:
        """Time-series spend rollup via GET /api/v1/metering/analytics/usage/timeseries.

        Returns dict with ``granularity``, ``group_by``, and ``series`` (list of bucket dicts).
        """
        params: dict = {"granularity": granularity}
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        if customer_id is not None:
            params["customer_id"] = customer_id
        if group_by is not None:
            params["group_by"] = group_by
        r = self._request("get", "/api/v1/metering/analytics/usage/timeseries", params=params)
        return r.json()

    def usage_analytics(self, *, start_date=None, end_date=None, customer_id=None,
                        tag_key=None, dimensions=None):
        """Cost + margin analytics with customer/product/tag breakdowns via
        GET /api/v1/metering/analytics/usage.

        Pass ``dimensions`` as a list of strings (e.g. ``["product_id", "tag:region"]``)
        to receive a ``breakdowns`` dict in the response.  httpx encodes a list as
        repeated query parameters, matching what django-ninja expects.
        """
        params = {k: v for k, v in {
            "start_date": start_date, "end_date": end_date,
            "customer_id": customer_id, "tag_key": tag_key}.items() if v}
        if dimensions is not None:
            params["dimensions"] = dimensions
        r = self._request("get", "/api/v1/metering/analytics/usage", params=params)
        return r.json()

    def close(self) -> None:
        self._http.close()
