from __future__ import annotations

import logging
from datetime import datetime

import httpx

from ubb import _operations as ops
from ubb.exceptions import (
    TaskOutcomeRequired, UBBConnectionError, UBBStopRequested,
)
from ubb._http import raise_for_status
from ubb._models import from_wire, list_from_wire
from ubb.retry import request_with_retry
from ubb.types import (
    PaginatedResponse,
    BatchItemResult, BatchResult,
)
# The lifecycle's values are NAMED, never spelled (#422, story 28): the
# three declarations the handle below sends, the one reason the block may
# declare on its own, and the closed set of states — which this module holds
# by reference so an integrator branches on a name rather than a string they
# typed. `ubb.vocabulary` is generated from the registry and rides its own
# ratchet, so what this client sends cannot drift from what the server
# recognises.
from ubb.vocabulary import (
    OUTCOME_REASON_EXECUTION_FAILED, TASK_OUTCOME_CANCELLED,
    TASK_OUTCOME_DELIVERED, TASK_OUTCOME_FAILED, TASK_STATUS_ACTIVE,
    TASK_STATUS_VALUES,
)
# Generated DTOs (the wrap, #84): response types come from the committed core,
# never hand-typed again.
from ubb._core.models.record_usage_response import RecordUsageResponse
from ubb._core.models.close_task_response import CloseTaskResponse
from ubb._core.models.start_task_response import StartTaskResponse
from ubb._core.models.task_detail_out import TaskDetailOut
from ubb._core.models.task_out import TaskOut
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


def _page_of(model_cls, body: dict) -> PaginatedResponse:
    """The cursor envelope every list answers, parsed through ``model_cls``."""
    return PaginatedResponse(data=list_from_wire(model_cls, body["data"]),
                             next_cursor=body.get("next_cursor"),
                             has_more=body["has_more"])


logger = logging.getLogger("ubb.metering")


#: THE STATES A UNIT OF WORK CAN HAVE ENDED IN — every state the registry
#: declares except the one live one, read off its closed set rather than
#: listed a second time here. `active` is the only non-terminal state, so
#: work whose state is in this set has ended and owes no declaration: that is
#: what `StartedTask.is_open` reads, and what an integrator branches on
#: (`if detail.status in TERMINAL_TASK_STATUSES`) instead of comparing five
#: strings they typed. Story 28's constant, for the states; the outcomes are
#: named on the handle's three methods.
TERMINAL_TASK_STATUSES = frozenset(TASK_STATUS_VALUES - {TASK_STATUS_ACTIVE})


def _attach(exc: BaseException, note: str) -> None:
    """Attach ``note`` to ``exc`` without raising anything in its place.

    A note rides the traceback where the developer is already looking. The
    SDK's floor is Python 3.10, where notes do not exist, so there it is
    logged instead — never swallowed, and never promoted over the exception
    that actually broke the work."""
    if hasattr(exc, "add_note"):
        exc.add_note(note)
    else:  # pragma: no cover - Python 3.10 only
        logger.warning(note)


class StartedTask:
    """A unit of work this client started, and the one place to say how it
    ended.

    ``start_task`` answers with one of these: the unit UBB registered, or the
    one the key already claimed (``replayed``). Use it as a context manager
    around the WHOLE run and declare the ending inside the block with exactly
    one of ``complete()``, ``fail(outcome_reason)`` or ``cancel()``::

        with client.start_task(customer_id, "nightly-42",
                               task_type="transcode") as task:
            client.record_usage(customer_id, "e1", task_id=task.task_id, ...)
            task.complete()

    The block declares an ending only where its own control flow is evidence
    for one. A declaration made inside it stands. A clean exit with none
    raises ``TaskOutcomeRequired`` and LEAVES THE WORK OPEN — nothing is sent
    and nothing is invented, and the declaration the block forgot still lands
    on the handle that signal carries. An ordinary exception escaping the
    block declares ``failed`` with the reason ``execution_failed`` — the
    exception's type name as the sentence beside it, never its message, which
    is yours to disclose — and the exception itself propagates; if reporting
    that failure to UBB fails too, the report's failure is attached to the
    original as a note and never raised in its place. A spend stop
    (``UBBStopRequested``), an interrupt, a cancellation or any other
    ``BaseException`` propagates with nothing declared: a stop is evidence of
    a stop, and a Ctrl-C during work that had in fact delivered must not
    write ``failed`` onto it.

    ``result`` is the whole registration (a ``StartTaskResponse``);
    ``task_id``, ``task_type``, ``parent_task_id``, ``replayed``,
    ``provider_cost_limit_micros``, ``agreed_price_micros``,
    ``external_task_id`` and ``created_at`` read straight off it. ``closed``
    is the close's acknowledgement once a declaration has landed, ``None``
    before; ``declared`` is the outcome sent through this handle, or ``None``.

    Your own key-values — a report id, an output location — are ``metadata``,
    declared on the start or on the usage events, and readable back. A
    completion takes no payload: ``outcome`` is the declaration, not a place
    for one, and no second word is coined beside it. The three methods are
    the whole close surface here; there is no single close taking an outcome
    word beside them, so the value a caller could mistype is never typed.
    ``close_task`` on the client is the primitive they delegate to, for
    closing work by id from somewhere this handle did not travel.
    """

    def __init__(self, client: MeteringClient, result: StartTaskResponse) -> None:
        self._client = client
        self.result = result
        self.declared: str | None = None
        self.closed: CloseTaskResponse | None = None

    # ---- identity: read off the registration, never copied ----

    @property
    def task_id(self) -> str:
        return self.result.task_id

    @property
    def task_type(self) -> str:
        return self.result.task_type or ""

    @property
    def parent_task_id(self) -> str | None:
        return self.result.parent_task_id

    @property
    def replayed(self) -> bool:
        return self.result.replayed

    @property
    def provider_cost_limit_micros(self) -> int | None:
        return self.result.provider_cost_limit_micros

    @property
    def agreed_price_micros(self) -> int | None:
        return self.result.agreed_price_micros

    @property
    def external_task_id(self) -> str:
        return self.result.external_task_id or ""

    @property
    def created_at(self) -> str:
        return self.result.created_at

    @property
    def status(self) -> str:
        """The last state this client saw: the one the close entered once a
        declaration has landed, the registration's before. The plain value,
        so it compares with ``ubb.vocabulary``'s names and sits in
        ``TERMINAL_TASK_STATUSES``."""
        recorded = self.closed if self.closed is not None else self.result
        return str(recorded.status)

    @property
    def is_open(self) -> bool:
        """Whether this handle still owes a declaration: the unit was live
        when it was handed back, and nothing has been declared THROUGH THIS
        HANDLE since. A replayed start can hand back work that already ended,
        which is not open. What this cannot see is a close made some other
        way — by id, from another process — and it does not ask UBB: it is a
        statement about this block, not a read."""
        return self.declared is None and self.status not in TERMINAL_TASK_STATUSES

    # ---- the three declarations ----

    def complete(self) -> CloseTaskResponse:
        """The work was delivered. Where the kind of work is sold at one
        agreed price this is the declaration that creates its charge, exactly
        once; ``charge_created`` on the acknowledgement says whether this
        call did."""
        return self._declare(TASK_OUTCOME_DELIVERED)

    def fail(self, outcome_reason: str, *,
             reason_detail: str | None = None) -> CloseTaskResponse:
        """The work failed. ``outcome_reason`` is REQUIRED and comes from
        UBB's closed list (``ubb.vocabulary.OUTCOME_REASON_VALUES``);
        ``unspecified`` is a member, so there is always an honest answer.
        ``reason_detail`` is the free-text sentence beside it, for display and
        never grouped on."""
        return self._declare(TASK_OUTCOME_FAILED, outcome_reason=outcome_reason,
                             reason_detail=reason_detail)

    def cancel(self, *, outcome_reason: str | None = None,
               reason_detail: str | None = None) -> CloseTaskResponse:
        """The work was withdrawn deliberately — by you, or by your customer.
        A reason is optional here, where ``fail`` requires one."""
        return self._declare(TASK_OUTCOME_CANCELLED,
                             outcome_reason=outcome_reason,
                             reason_detail=reason_detail)

    def _declare(self, outcome: str, *, outcome_reason: str | None = None,
                 reason_detail: str | None = None) -> CloseTaskResponse:
        # Recorded as declared BEFORE the request goes out: a refusal or a
        # transport failure raises out of this call to whoever made it, and
        # the block's exit must not then pile a second declaration onto the
        # one that was refused.
        self.declared = outcome
        self.closed = self._client.close_task(
            self.task_id, outcome, outcome_reason=outcome_reason,
            reason_detail=reason_detail)
        return self.closed

    # ---- the work block ----

    def __enter__(self) -> StartedTask:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        # THE FIVE EXITS (#179 §2.2), and the classification is STRUCTURAL:
        # nothing here lists what not to treat as failure. The spend stop sits
        # outside `Exception` (#421), so the second test below covers it along
        # with KeyboardInterrupt, SystemExit and CancelledError without naming
        # any of them — and a control-flow type added tomorrow is classified
        # the same way without anyone remembering to add it.
        if exc_type is None:
            if self.is_open:
                raise TaskOutcomeRequired(self)
            return False
        if issubclass(exc_type, Exception) and self.is_open:
            try:
                self.fail(OUTCOME_REASON_EXECUTION_FAILED,
                          reason_detail=type(exc).__qualname__)
            except Exception as reporting:
                # #179 §2.3: the exception that broke the work stays primary.
                _attach(exc, f"UBB was not told the work failed: reporting "
                             f"it raised {type(reporting).__name__}: "
                             f"{reporting}")
        return False


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

    def record_usage(self, customer_id: str, idempotency_key: str, *,
                     provider_cost_micros: int | None = None,
                     claimed_provider_cost_micros: int | None = None,
                     provider: str = "", event_type: str = "",
                     currency: str | None = None,
                     dimensions: dict | None = None,
                     metadata: dict | None = None,
                     task_id: str | None = None,
                     measurements: dict | None = None,
                     recorded_at: datetime | str | None = None,
                     raise_on_stop: bool = True) -> RecordUsageResponse:
        """Record a usage event via POST /api/v1/metering/usage.

        One-rule contract: every event that reaches UBB is priced, recorded,
        and billed with an HTTP 200, and the ack carries the verdict. When
        the verdict says stop, this call RAISES ``UBBStopRequested`` carrying
        that ack (see ``raise_on_stop`` below): stop sending work for the
        named scope (``stop_scope``: the task, or the whole customer). A
        non-200 always means "this was not recorded".

        ``idempotency_key`` is the ONE correlation value this call takes, and
        it is now the second positional parameter rather than the third. There
        used to be a second one beside it; it had no uniqueness constraint, no
        lookup and no read that changed anything, so it was deleted rather than
        renamed. This key is what decides a replay: send the same one and you
        get the original event back. Your own correlation strings belong in
        ``metadata``, where the keys are yours.

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

        ``raise_on_stop``: True by default. A stop verdict on the ack is
        raised as ``UBBStopRequested`` — a ``BaseException``, so your own
        ``except Exception:`` around a provider loop cannot swallow it and
        keep spending — carrying the whole acknowledgement, so nothing is
        lost by catching it. The event was recorded and charged either way;
        the signal is about the NEXT call, never a failed submission. Catch
        it once, at the boundary that can honour ``stop_scope``, and never
        resend the event. ``raise_on_stop=False`` returns the same ack with
        ``result.stop`` set instead of raising. The one reason to choose it
        is recording work that has ALREADY happened one call at a time,
        where a stop raised part-way would leave the rest unrecorded — and
        ``record_batch`` is the better tool for that, because it never
        raises.
        """
        body: dict = {
            "customer_id": customer_id,
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
            # Ordering is contract (#179 §1.3): the write committed and the
            # ack is fully built before anything is raised, and the signal
            # carries that ack. It sits after `_request`, so the retry loop
            # never sees it and a completed event is never re-sent.
            raise UBBStopRequested(result, idempotency_key=idempotency_key)
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

        A stop is REPORTED, never raised (#421). Each item carries its own
        verdict (``item.stop`` / ``stop_reason`` / ``stop_scope``);
        ``result.stop`` says whether any recorded item asked for one and
        ``result.first_stop_index`` names the earliest that did. One stopped
        piece of work must not abandon the rest of the batch, and a stop
        cannot prevent work that already completed — this path records
        history, and it records all of it. Honour the per-item scope in your
        own loop; ``record_usage`` is the call that raises.
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
                # A rejected item carries the server's constant verdict —
                # `stop: false`, null reason and scope — because nothing was
                # recorded and so nothing can have stopped; an accepted item
                # may omit the key altogether, since the contract's `stop`
                # is optional with a false default. Both read as False.
                stop=bool(item.get("stop", False)),
                stop_reason=item.get("stop_reason"),
                stop_scope=item.get("stop_scope"),
            )
            for item in body.get("results", [])
        ]
        return BatchResult(results=results, accepted=body.get("accepted", 0),
                           rejected=body.get("rejected", 0))

    def start_task(self, customer_id: str, idempotency_key: str, *,
                   task_type: str | None = None,
                   parent_task_id: str | None = None,
                   provider_cost_limit_micros: int | None = None,
                   dimensions: dict | None = None,
                   external_task_id: str | None = None,
                   metadata: dict | None = None) -> StartedTask:
        """Register a unit of work via POST /api/v1/tasks, and get the same
        one back on a retry.

        ``idempotency_key`` is REQUIRED and is YOUR identifier for this unit
        of work: unique per customer and stable across every retry of the
        same work, never minted on the line, because a new value on every
        attempt makes a retried start a second unit of work — and where the
        kind of work is sold at one agreed price, a second charge. Send the
        same key again and the answer is the unit you already started, with
        ``replayed`` True and nothing created a second time; send it
        describing a DIFFERENT unit and the server refuses it
        (``409 idempotency_key_conflict``) naming the field that differs.

        ``task_type`` names a declared kind of work, which pins its ceiling,
        its expiry windows and how it is sold. ``parent_task_id`` registers
        contained work under a running unit through this same call — there
        is one start shape, not two. ``provider_cost_limit_micros`` caps what
        the unit may spend at the supplier, never higher than the kind of
        work allows. ``dimensions`` is the declared grouping bag at this
        altitude, under the keyword ``record_usage`` already uses because the
        request property spells it. ``external_task_id`` is a free-text label
        reusable across attempts; ``metadata`` is your own key-values,
        readable back and never consulted for pricing. Neither of the last
        two is pinned: a replay carrying different values is still a replay,
        and the original's stand.

        A refusal is a refusal, never a 200: ``409 task_start_refused`` says
        why this customer may not begin new work, and a ``422`` answers a
        request that is wrong in itself. The answer is a ``StartedTask`` —
        use it as a context manager around the run and declare the ending
        inside it; see the class for the five exits.
        """
        body: dict = {"customer_id": customer_id,
                      "idempotency_key": idempotency_key}
        if task_type is not None:
            body["task_type"] = task_type
        if parent_task_id is not None:
            body["parent_task_id"] = parent_task_id
        if provider_cost_limit_micros is not None:
            body["provider_cost_limit_micros"] = provider_cost_limit_micros
        if dimensions is not None:
            body["dimensions"] = dimensions
        if external_task_id is not None:
            body["external_task_id"] = external_task_id
        if metadata is not None:
            body["metadata"] = metadata
        r = self._request(*ops.API_V1_TASK_ENDPOINTS_START_TASK, json=body)
        return StartedTask(self, from_wire(StartTaskResponse, r.json()))

    def get_task(self, task_id: str) -> TaskDetailOut:
        """One unit of work's cost receipt plus the work contained in it, via
        GET /api/v1/tasks/{task_id}: the materialised rollups — including
        events that landed after a kill — its state, and how it ended."""
        r = self._request(*ops.API_V1_TASK_ENDPOINTS_GET_TASK(task_id))
        return from_wire(TaskDetailOut, r.json())

    def list_tasks(self, *, cursor: str | None = None, limit: int | None = None,
                   customer_id: str | None = None, task_type: str | None = None,
                   status: str | None = None) -> PaginatedResponse[TaskOut]:
        """Top-level work with its rollups via GET /api/v1/tasks, newest
        first. Contained work is omitted — it belongs to its parent's detail
        — so a page counts whole pieces of work. ``status`` filters on one of
        ``ubb.vocabulary.TASK_STATUS_VALUES``; the route decides what it
        accepts, and this client holds no list of its own."""
        params = {k: v for k, v in {
            "cursor": cursor, "limit": limit, "customer_id": customer_id,
            "task_type": task_type, "status": status}.items() if v is not None}
        r = self._request(*ops.API_V1_TASK_ENDPOINTS_LIST_TASKS,
                          params=params or None)
        return _page_of(TaskOut, r.json())

    def list_subtasks(self, task_id: str, *, cursor: str | None = None,
                      limit: int | None = None) -> PaginatedResponse[TaskOut]:
        """The work contained in one unit, via
        GET /api/v1/tasks/{task_id}/subtasks. A unit with nothing inside it
        answers an empty page, not a 404. To start contained work, call
        ``start_task`` naming ``parent_task_id``."""
        params = {k: v for k, v in {"cursor": cursor, "limit": limit}.items()
                  if v is not None}
        r = self._request(*ops.API_V1_TASK_ENDPOINTS_LIST_SUBTASKS(task_id),
                          params=params or None)
        return _page_of(TaskOut, r.json())

    def close_task(self, task_id: str, outcome: str, *,
                   outcome_reason: str | None = None,
                   reason_detail: str | None = None) -> CloseTaskResponse:
        """Close a task via POST /api/v1/tasks/{task_id}/close, DECLARING HOW
        IT ENDED.

        ``outcome`` is REQUIRED and positional, and this wrapper supplies no
        default — the server does not either. A default here would be the
        forgiving path becoming the money-moving one: a caller that forgot the
        argument would silently declare a delivery.

        This is the primitive: the handle ``start_task`` returns declares
        through it as ``complete()`` / ``fail(outcome_reason)`` / ``cancel()``,
        which is the preferred shape because it never types the outcome word.
        Call this directly to close work by id from somewhere that handle did
        not travel, naming the outcome through ``ubb.vocabulary``.

        ``outcome_reason`` is required when the outcome is a failure, optional
        on a cancellation, and accepted on neither when the work was delivered;
        ``reason_detail`` is the free-text sentence beside it and is never
        required. An unrecognised reason is refused by the server rather than
        carried through — it is caller-supplied.

        The response says whether this call performed the close or found it
        already done (``replayed``); a close that contradicts a state the
        server already recorded is refused rather than answered 200.

        Closing a parent withdraws its still-running contained work
        server-side — cleanup is one call. Closing contained work closes it
        alone."""
        body: dict = {"outcome": outcome}
        if outcome_reason is not None:
            body["outcome_reason"] = outcome_reason
        if reason_detail is not None:
            body["reason_detail"] = reason_detail
        r = self._request(*ops.API_V1_TASK_ENDPOINTS_CLOSE_TASK(task_id),
                          json=body)
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
        return _page_of(UsageEventOut, r.json())

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
