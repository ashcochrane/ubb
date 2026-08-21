from __future__ import annotations

from datetime import datetime

import httpx

from ubb import _operations as ops
from ubb.exceptions import UBBConnectionError, UBBStoppedError
from ubb._http import raise_for_status
from ubb._models import from_wire, list_from_wire
from ubb.retry import request_with_retry
from ubb.types import (
    PaginatedResponse,
    BatchItemResult, BatchResult,
    RateCard,
)
# Generated DTOs (the wrap, #84): response types come from the committed core,
# never hand-typed again.
from ubb._core.models.record_usage_response import RecordUsageResponse
from ubb._core.models.close_task_response import CloseTaskResponse
from ubb._core.models.customer_margin_out import CustomerMarginOut
from ubb._core.models.grouping_field_margin_row import GroupingFieldMarginRow
from ubb._core.models.margin_trend_point_out import MarginTrendPointOut
from ubb._core.models.revenue_profile_out import RevenueProfileOut
from ubb._core.models.usage_event_out import UsageEventOut
from ubb._core.models.pricing_book_out import PricingBookOut
from ubb._core.models.cost_book_out import CostBookOut


def _serialize_recorded_at(value):
    """ISO string for the wire. A datetime MUST be timezone-aware — naive
    datetimes are rejected client-side, before any HTTP request, because the
    server cannot guess the intended offset. Strings pass through untouched
    (a naive ISO string is rejected server-side with a 422
    ``effective_at_naive``)."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "recorded_at must be a timezone-aware datetime (e.g. "
                "datetime.now(timezone.utc)) or an ISO-8601 string with offset")
        return value.isoformat()
    return str(value)


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
        raise_for_status(response)
        return response

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return request_with_retry(
            self._request_once, max_retries=self._max_retries,
            method=method, path=path, **kwargs,
        )

    # ---- public API ----

    def record_usage(self, customer_id: str, request_id: str, idempotency_key: str, *,
                     provider_cost_micros: int | None = None,
                     claimed_provider_cost_micros: int | None = None,
                     provider: str = "", event_type: str = "",
                     currency: str | None = None,
                     dimensions: dict | None = None,
                     metadata: dict | None = None,
                     task_id: str | None = None,
                     measurements: dict | None = None,
                     recorded_at: datetime | str | None = None,
                     raise_on_stop: bool = False) -> RecordUsageResponse:
        """Record a usage event via POST /api/v1/metering/usage.

        One-rule contract: every event that reaches UBB is priced, recorded,
        and billed with an HTTP 200 — check ``result.stop`` on every ack and
        stop sending work for the named scope (``result.stop_scope``: the
        task, or the whole customer). A non-200 always means "this was not
        recorded".

        ``dimensions``: declared EVENT-scoped grouping field values (the
        tenant's registry, ``PUT /api/v1/metering/grouping-fields``) — what
        rate cards select on and analytics group by. The keyword still spells
        the registry's old name because the request property does; the route
        moved to the canonical one and the property follows in the slice that
        owns it.

        Distinct from ``metadata``, the one open bag: free-form labelling,
        filterable and readable, never consulted for pricing or grouping. The
        second open bag folded into it and its name retired with the grouping
        capability that name promised — a caller that sent the old bag sends
        the same keys under ``metadata``.

        ``recorded_at``: when the usage actually happened — a timezone-aware
        datetime or ISO-8601 string (sent as ``effective_at``). Naive datetimes
        raise ValueError client-side. Bounded server-side by the tenant's
        backfill window (default 34 days; typed 422 codes: effective_at_naive,
        effective_at_in_future, effective_at_too_old, billing_period_closed).
        Omitted = server receive time.

        ``provider_cost_micros`` is the SUPPLIER'S OWN reported cost, and it
        is COGS. UBB accepts it only where the Event Type declares that the
        figure arrives on the call — the reported costing method with a
        caller-supplied source — and refuses it anywhere else rather than
        recording a number it would never read as cost: a 422 from this call,
        and a rejected item verdict from ``record_batch``, whose response is
        200 whatever its items say. This client holds no list of which Event
        Types those are, per the open-world rule in
        ``docs/conventions/sdk-wrap.md``: the route decides and says so.

        ``claimed_provider_cost_micros`` is what YOU believe the call cost. It
        is accepted on any event, recorded as stated, and never treated as
        cost — never rated, never summed into a cost total, never the figure
        above. Send it when you have an estimate and no declaration, which is
        the case the 422 above points at.

        THERE IS NO KEYWORD FOR THE CUSTOMER'S PRICE, and there is no equivalent
        of the claimed cost on that side either. What you charge a customer is
        resolved by UBB from the pricing rules your tenant configures, and it
        arrives on the response — ``result.billed_cost_micros``, with
        ``result.pricing_status`` saying whether it settled. A price sent on the
        call would be a decision made outside the system that goes stale the
        moment the underlying cost moves, so the route REFUSES a body carrying
        ``billed_cost_micros``: it is a 422 naming the field, not a silent 200.
        That refusal is specific to this one retired name — every other key the
        request does not publish is still dropped without comment. Write the
        rule instead.

        ``raise_on_stop``: when True, raise UBBStoppedError if the response
        carries a stop verdict (result.stop). The event is still
        recorded+charged either way; this is purely an ergonomic choice
        between checking result.stop and catching an exception.
        """
        body: dict = {
            "customer_id": customer_id,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "metadata": metadata or {},
        }
        if recorded_at is not None:
            body["effective_at"] = _serialize_recorded_at(recorded_at)
        if provider_cost_micros is not None:
            body["provider_cost_micros"] = provider_cost_micros
        if claimed_provider_cost_micros is not None:
            body["claimed_provider_cost_micros"] = claimed_provider_cost_micros
        if measurements is not None:
            body["measurements"] = measurements
        if currency is not None:
            body["currency"] = currency
        if dimensions is not None:
            body["dimensions"] = dimensions
        if event_type:
            body["event_type"] = event_type
        if provider:
            body["provider"] = provider
        if task_id is not None:
            body["task_id"] = task_id
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_RECORD_USAGE, json=body)
        result = from_wire(RecordUsageResponse, r.json())
        if raise_on_stop and result.stop:
            raise UBBStoppedError(
                reason=result.stop_reason, scope=result.stop_scope, task_id=result.task_id)
        return result

    def record_batch(self, events: list[dict]) -> BatchResult:
        """Record up to 100 INDEPENDENT usage events via POST
        /api/v1/metering/usage/batch.

        Each event dict takes the same keys as record_usage kwargs (plus
        ``customer_id``); a per-event ``recorded_at`` is serialized to
        ``effective_at`` (naive datetimes raise ValueError before any HTTP).

        Items succeed or fail INDEPENDENTLY — the response is always HTTP 200
        with per-item results aligned positionally to ``events``. On a network
        failure, retry the WHOLE batch: per-item idempotency keys make a full
        replay return the original event ids with zero new rows.
        """
        wire_events = []
        for ev in events:
            ev = dict(ev)
            recorded_at = ev.pop("recorded_at", None)
            if recorded_at is not None:
                ev["effective_at"] = _serialize_recorded_at(recorded_at)
            wire_events.append(ev)
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_RECORD_USAGE_BATCH,
                          json={"events": wire_events})
        body = r.json()
        results = [
            BatchItemResult(
                accepted=item.get("accepted", False),
                code=item.get("code"),
                detail=item.get("detail"),
                event_id=item.get("event_id"),
                data=item,
            )
            for item in body.get("results", [])
        ]
        return BatchResult(results=results, accepted=body.get("accepted", 0),
                           rejected=body.get("rejected", 0))

    def close_task(self, task_id: str) -> CloseTaskResponse:
        """Close (complete) a task via POST /api/v1/metering/tasks/{task_id}/close.

        Closing a parent auto-completes its active subtasks server-side —
        cleanup is one call. Closing a subtask closes it alone."""
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_CLOSE_TASK(task_id))
        return from_wire(CloseTaskResponse, r.json())

    def get_usage(self, customer_id: str, cursor: str | None = None, limit: int = 20,
                  tag_key: str | None = None, tag_value: str | None = None,
                  past_limit: bool | None = None, stop_scope: str | None = None,
                  episode_seq: int | None = None) -> PaginatedResponse[UsageEventOut]:
        """Get usage history via GET /api/v1/metering/customers/{customer_id}/usage.

        The #41 past-limit filters: ``past_limit=True`` returns only events
        that landed past a stop (each carries ``stop_context``);
        ``stop_scope`` / ``episode_seq`` narrow to a scope or one
        customer-wide stop episode."""
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if tag_key is not None:
            params["tag_key"] = tag_key
        if tag_value is not None:
            params["tag_value"] = tag_value
        if past_limit is not None:
            params["past_limit"] = past_limit
        if stop_scope is not None:
            params["stop_scope"] = stop_scope
        if episode_seq is not None:
            params["episode_seq"] = episode_seq
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_GET_USAGE(customer_id), params=params)
        body = r.json()
        events = [from_wire(UsageEventOut, item) for item in body["data"]]
        return PaginatedResponse(data=events, next_cursor=body.get("next_cursor"), has_more=body["has_more"])

    def get_past_limit_report(self, customer_id: str, *, since=None, until=None) -> dict:
        """The past-limit report (#41) via
        GET /api/v1/customers/{customer_id}/past-limit-report — "exactly what
        was spent past the limit and why" in one call: episodes (the tripping
        limit, tripped_at, resume time, itemized events) plus
        ``totals_per_limit`` in both denominations. Soft-floor episodes are
        crossed/cleared marker rows with no itemized events. ``since`` /
        ``until`` (ISO datetimes) window episodes and itemized events."""
        params = {k: v for k, v in {"since": since, "until": until}.items() if v}
        r = self._request(*ops.API_V1_ENDPOINTS_PAST_LIMIT_REPORT(customer_id),
                          params=params)
        return r.json()

    def get_customer_margin(self, customer_id, start_date=None, end_date=None):
        params = {k: v for k, v in {"start_date": start_date, "end_date": end_date}.items() if v}
        r = self._request(
            *ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_CUSTOMER_MARGIN(customer_id),
            params=params)
        return from_wire(CustomerMarginOut, r.json())

    def get_margin_by_grouping_field(self, *, group_by="provider", tag_key=None,
                                     start_date=None, end_date=None):
        """Margin broken down by one Grouping Field, one row per value.

        ``group_by`` is the axis: one of the built-in ``provider``,
        ``event_type``, ``task_type``, ``subtask_type``, or any key the tenant
        has declared in its Grouping Field registry. The route resolves the key
        and answers 422 for one it does not know — this client does not hold a
        list of its own, because a client that did would refuse a key declared
        after it was pinned.

        ``tag_key`` groups by a key in the open metadata bag instead, and the
        route prefers it over the axis when both arrive.

        The row's value is ``grouping_field_value`` — the thing that was
        reported, a model name or a region. The axis is not repeated on every
        row, because the request already names it.
        """
        params = {"group_by": group_by}
        if tag_key:
            params["tag_key"] = tag_key
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        r = self._request(
            *ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_MARGIN_BY_GROUPING_FIELD,
            params=params)
        return list_from_wire(GroupingFieldMarginRow, r.json()["rows"])

    def get_unprofitable_customers(self, period_start=None):
        params = {"period_start": period_start} if period_start else {}
        r = self._request(
            *ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_MARGIN_UNPROFITABLE,
            params=params)
        return r.json()["customers"]

    def get_margin_trend(self, customer_id, periods=6):
        r = self._request(
            *ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_MARGIN_TREND(customer_id),
            params={"periods": periods})
        return list_from_wire(MarginTrendPointOut, r.json()["points"])

    def set_customer_revenue(self, customer_id, recurring_amount_micros, interval="month",
                             currency="usd", effective_from=None, effective_to=None):
        body = {"recurring_amount_micros": recurring_amount_micros, "interval": interval,
                "currency": currency}
        if effective_from:
            body["effective_from"] = effective_from
        if effective_to:
            body["effective_to"] = effective_to
        r = self._request(
            *ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_PUT_REVENUE(customer_id),
            json=body)
        return from_wire(RevenueProfileOut, r.json())

    def get_customer_revenue(self, customer_id):
        r = self._request(*ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_GET_REVENUE(customer_id))
        return from_wire(RevenueProfileOut, r.json())

    def get_business_margin(self, external_id, start_date=None, end_date=None):
        params = {k: v for k, v in {"start_date": start_date, "end_date": end_date}.items() if v}
        r = self._request(
            *ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_BUSINESS_MARGIN(external_id),
            params=params)
        return r.json()

    def set_revenue_mode(self, customer_id, revenue_mode=""):
        r = self._request(
            *ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_PUT_REVENUE_MODE(customer_id),
            json={"revenue_mode": revenue_mode})
        return r.json()

    def get_revenue_mode(self, customer_id):
        r = self._request(
            *ops.APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_GET_REVENUE_MODE(customer_id))
        return r.json()

    @staticmethod
    def _rate_card(row):
        return RateCard(**{k: v for k, v in row.items()
                           if k in RateCard.__dataclass_fields__})

    def declare_pricing_book(self, *, key, name="", is_default=False):
        """Declare a Pricing Book: a catalogue of what this tenant charges.

        It names neither a supplier nor a currency — a tenant's price for a
        unit of work does not change because they switched supplier, and a
        tenant has exactly one currency. A rule that should price one
        supplier's work differently pins `provider` as a selector.

        The book arrives EMPTY: UBB ships no catalogue, so it prices nothing
        until rules are published into it.
        """
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_DECLARE_PRICING_BOOK,
                          json={"key": key, "name": name,
                                "is_default": is_default})
        return from_wire(PricingBookOut, r.json())

    def withdraw_pricing_book(self, book_id):
        """Withdraw a Pricing Book the tenant no longer prices from.

        A book still holding rules answers 409: those rules are what customers
        were charged from, and the receipts explaining past charges point at
        them. Retire them through a publish first.
        """
        r = self._request(
            *ops.API_V1_METERING_ENDPOINTS_WITHDRAW_PRICING_BOOK(book_id))
        return r.json()

    def declare_cost_book(self, *, key, provider_key="", name="",
                          currency=None, is_default=False):
        """Declare a cost book: what one supplier charges this tenant.

        It names the supplier and the currency that supplier bills in.
        `provider_key=""` is a stated value and means the book applies whatever
        the supplier — the provider-agnostic bucket resolution reads alongside
        a supplier's own.
        """
        body = {"key": key, "provider_key": provider_key, "name": name,
                "is_default": is_default}
        if currency is not None:
            body["currency"] = currency
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_DECLARE_COST_BOOK,
                          json=body)
        return from_wire(CostBookOut, r.json())

    def withdraw_cost_book(self, book_id):
        """Withdraw a cost book, under `withdraw_pricing_book`'s own rule."""
        r = self._request(
            *ops.API_V1_METERING_ENDPOINTS_WITHDRAW_COST_BOOK(book_id))
        return r.json()

    def update_rate_card(self, card_id, **fields):
        """Soft-version a rate card via PUT. Only the provided ``fields`` change;
        unspecified fields are copied from the active version. Returns the new
        version (same ``lineage_id``, new ``id``)."""
        r = self._request(*ops.UNPUBLISHED_PUT_METERING_PRICING_RATE_CARDS(card_id), json=fields)
        return self._rate_card(r.json())

    def get_rate_card_history(self, lineage_id):
        """Return every version sharing ``lineage_id``, newest first."""
        r = self._request(*ops.UNPUBLISHED_GET_METERING_PRICING_RATE_CARDS_HISTORY(lineage_id))
        return [self._rate_card(row) for row in r.json()]

    def list_pricing_books(self, cursor=None, limit=None):
        """The tenant's Pricing Books, newest first.

        ⚠ **TWO METHODS WHERE THERE WAS ONE WITH A KIND ARGUMENT (#368).** A
        Pricing Book and a cost book are separately shaped entities on separate
        paths, so the argument that used to select between them has nothing
        left to select: the two answer different types, and a caller says which
        it wants by naming a method rather than by passing a word.
        """
        params = {k: v for k, v in {"cursor": cursor, "limit": limit}.items()
                  if v is not None}
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_LIST_PRICING_BOOKS,
                          params=params or None)
        return list_from_wire(PricingBookOut, r.json()["data"])

    def list_cost_books(self, cursor=None, limit=None):
        """The tenant's cost books, newest first."""
        params = {k: v for k, v in {"cursor": cursor, "limit": limit}.items()
                  if v is not None}
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_LIST_COST_BOOKS,
                          params=params or None)
        return list_from_wire(CostBookOut, r.json()["data"])

    def bulk_create_rate_cards(self, cards: list[dict]) -> dict:
        """Atomically create multiple rate cards via POST /api/v1/metering/pricing/rate-cards/batch.

        All cards are validated before any are created; if any card is invalid the
        entire batch is rejected (no partial writes).  Returns a dict with ``created``
        (list of new card IDs) and ``count``.
        """
        r = self._request(*ops.UNPUBLISHED_POST_METERING_PRICING_RATE_CARDS_BATCH,
                          json={"cards": cards})
        return r.json()

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
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_USAGE_TIMESERIES, params=params)
        return r.json()

    def usage_analytics(self, *, start_date=None, end_date=None, customer_id=None,
                        tag_key=None, dimensions=None, past_limit=None,
                        stop_scope=None, episode_seq=None):
        """Cost + margin analytics with customer/product/tag breakdowns via
        GET /api/v1/metering/analytics/usage.

        Pass ``dimensions`` as a list of strings (e.g. ``["product_id", "tag:region"]``)
        to receive a ``breakdowns`` dict in the response.  httpx encodes a list as
        repeated query parameters, matching what django-ninja expects.

        The #41 past-limit filters (``past_limit`` / ``stop_scope`` /
        ``episode_seq``) compose with every breakdown — e.g.
        ``past_limit=True`` totals exactly what was spent past a stop, in
        both denominations.
        """
        params = {k: v for k, v in {
            "start_date": start_date, "end_date": end_date,
            "customer_id": customer_id, "tag_key": tag_key}.items() if v}
        if dimensions is not None:
            params["dimensions"] = dimensions
        if past_limit is not None:
            params["past_limit"] = past_limit
        if stop_scope is not None:
            params["stop_scope"] = stop_scope
        if episode_seq is not None:
            params["episode_seq"] = episode_seq
        r = self._request(*ops.API_V1_METERING_ENDPOINTS_USAGE_ANALYTICS, params=params)
        return r.json()

    # ---- NO MARKUP METHODS (#369) ----
    #
    # Four of them read and wrote a tenant-wide markup and one customer's
    # override, over a record that is deleted with its five routes and its two
    # component schemas. Deleting the methods is forced rather than chosen: the
    # operations they named leave the published contract, so the generated
    # constants they resolved through stop existing in the same regeneration.
    #
    # **NOTHING REPLACES THEM HERE, AND THAT IS SIGNED FOR.** The tenant's
    # declared default markup rung has three published operations and no
    # ergonomic wrapper, licensed in `coverage-authorisations.yaml` under
    # `slice-4-357-the-tenant-default-markup-rung-is-declarable`: deciding what
    # a customer is charged is a governance act performed once by a person
    # entitled to, not something an integrator's code does, and that entry
    # names this commit as the one where the surface these methods wrapped goes
    # away. A customer's own price is a rule in their own pricing book, which
    # is on the same side of that line.

    def close(self) -> None:
        self._http.close()
