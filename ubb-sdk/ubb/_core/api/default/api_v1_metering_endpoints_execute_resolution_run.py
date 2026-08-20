from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.resolution_run_in import ResolutionRunIn
from ...models.resolution_run_out import ResolutionRunOut
from typing import cast



def _get_kwargs(
    *,
    body: ResolutionRunIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/resolution-runs",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | ResolutionRunOut | None:
    if response.status_code == 200:
        response_200 = ResolutionRunOut.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | ResolutionRunOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ResolutionRunIn,

) -> Response[ProblemOut | ResolutionRunOut]:
    """ Execute Resolution Run

     Complete what was never resolved: prices and supplier costs UBB could
    not work out at the time.

    Each posting the run reaches is re-resolved **at its own effective
    instant**, and a field recorded as unresolved is completed where that
    resolution now has an answer. Nothing else is touched: a posting already
    carrying a cost or a price is not in the set the run selects from, and
    neither is one whose charge was waived — a waived charge is a decision
    somebody made, not information UBB is missing.

    **Nothing is repriced.** A rule takes effect from the moment it is published
    forward, so writing one today does not change work recorded in July; what a
    run completes is what today's markup rung and today's Event Type
    declarations resolve at that past instant.

    **A run moves no money.** No invoice, credit note, charge or refund follows
    from one. It completes the numbers and records that it did, and the response
    says what it completed.

    The selector takes a date range, a customer and an Event Type in any
    combination — the range is half-open, `[from, to)` — and any other field is
    refused (`validation_error`). A customer this tenant does not have is a 404.
    `more_to_do` says the selector matched more postings than one run takes;
    send the same body again and the next run continues where this one stopped.

    A run cannot be undone: completing an unresolved field happens exactly once,
    and the receipt is sealed after it. It requires the `admin` role.

    Args:
        body (ResolutionRunIn): Which postings this run should reach: a date range, a customer, an
            Event Type — in any combination, and any of them may be omitted.

            An omitted axis is unpinned rather than empty: a body naming nothing at all
            reaches every posting of this tenant that was never resolved. The date range
            is over the posting's own effective instant and is half-open — `[from, to)`
            — so running one month and then the next repairs each posting exactly once.

            A run reaches only postings whose status says they were never resolved, and
            that is a property of how the set is built rather than of what you send:
            there is no field here that could widen it to a posting already carrying a
            cost or a price, and none that could reach one whose charge was waived.

            Any other field is refused (`validation_error`). A run takes no condition of
            its own.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ResolutionRunOut]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    body: ResolutionRunIn,

) -> ProblemOut | ResolutionRunOut | None:
    """ Execute Resolution Run

     Complete what was never resolved: prices and supplier costs UBB could
    not work out at the time.

    Each posting the run reaches is re-resolved **at its own effective
    instant**, and a field recorded as unresolved is completed where that
    resolution now has an answer. Nothing else is touched: a posting already
    carrying a cost or a price is not in the set the run selects from, and
    neither is one whose charge was waived — a waived charge is a decision
    somebody made, not information UBB is missing.

    **Nothing is repriced.** A rule takes effect from the moment it is published
    forward, so writing one today does not change work recorded in July; what a
    run completes is what today's markup rung and today's Event Type
    declarations resolve at that past instant.

    **A run moves no money.** No invoice, credit note, charge or refund follows
    from one. It completes the numbers and records that it did, and the response
    says what it completed.

    The selector takes a date range, a customer and an Event Type in any
    combination — the range is half-open, `[from, to)` — and any other field is
    refused (`validation_error`). A customer this tenant does not have is a 404.
    `more_to_do` says the selector matched more postings than one run takes;
    send the same body again and the next run continues where this one stopped.

    A run cannot be undone: completing an unresolved field happens exactly once,
    and the receipt is sealed after it. It requires the `admin` role.

    Args:
        body (ResolutionRunIn): Which postings this run should reach: a date range, a customer, an
            Event Type — in any combination, and any of them may be omitted.

            An omitted axis is unpinned rather than empty: a body naming nothing at all
            reaches every posting of this tenant that was never resolved. The date range
            is over the posting's own effective instant and is half-open — `[from, to)`
            — so running one month and then the next repairs each posting exactly once.

            A run reaches only postings whose status says they were never resolved, and
            that is a property of how the set is built rather than of what you send:
            there is no field here that could widen it to a posting already carrying a
            cost or a price, and none that could reach one whose charge was waived.

            Any other field is refused (`validation_error`). A run takes no condition of
            its own.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ResolutionRunOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ResolutionRunIn,

) -> Response[ProblemOut | ResolutionRunOut]:
    """ Execute Resolution Run

     Complete what was never resolved: prices and supplier costs UBB could
    not work out at the time.

    Each posting the run reaches is re-resolved **at its own effective
    instant**, and a field recorded as unresolved is completed where that
    resolution now has an answer. Nothing else is touched: a posting already
    carrying a cost or a price is not in the set the run selects from, and
    neither is one whose charge was waived — a waived charge is a decision
    somebody made, not information UBB is missing.

    **Nothing is repriced.** A rule takes effect from the moment it is published
    forward, so writing one today does not change work recorded in July; what a
    run completes is what today's markup rung and today's Event Type
    declarations resolve at that past instant.

    **A run moves no money.** No invoice, credit note, charge or refund follows
    from one. It completes the numbers and records that it did, and the response
    says what it completed.

    The selector takes a date range, a customer and an Event Type in any
    combination — the range is half-open, `[from, to)` — and any other field is
    refused (`validation_error`). A customer this tenant does not have is a 404.
    `more_to_do` says the selector matched more postings than one run takes;
    send the same body again and the next run continues where this one stopped.

    A run cannot be undone: completing an unresolved field happens exactly once,
    and the receipt is sealed after it. It requires the `admin` role.

    Args:
        body (ResolutionRunIn): Which postings this run should reach: a date range, a customer, an
            Event Type — in any combination, and any of them may be omitted.

            An omitted axis is unpinned rather than empty: a body naming nothing at all
            reaches every posting of this tenant that was never resolved. The date range
            is over the posting's own effective instant and is half-open — `[from, to)`
            — so running one month and then the next repairs each posting exactly once.

            A run reaches only postings whose status says they were never resolved, and
            that is a property of how the set is built rather than of what you send:
            there is no field here that could widen it to a posting already carrying a
            cost or a price, and none that could reach one whose charge was waived.

            Any other field is refused (`validation_error`). A run takes no condition of
            its own.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ResolutionRunOut]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ResolutionRunIn,

) -> ProblemOut | ResolutionRunOut | None:
    """ Execute Resolution Run

     Complete what was never resolved: prices and supplier costs UBB could
    not work out at the time.

    Each posting the run reaches is re-resolved **at its own effective
    instant**, and a field recorded as unresolved is completed where that
    resolution now has an answer. Nothing else is touched: a posting already
    carrying a cost or a price is not in the set the run selects from, and
    neither is one whose charge was waived — a waived charge is a decision
    somebody made, not information UBB is missing.

    **Nothing is repriced.** A rule takes effect from the moment it is published
    forward, so writing one today does not change work recorded in July; what a
    run completes is what today's markup rung and today's Event Type
    declarations resolve at that past instant.

    **A run moves no money.** No invoice, credit note, charge or refund follows
    from one. It completes the numbers and records that it did, and the response
    says what it completed.

    The selector takes a date range, a customer and an Event Type in any
    combination — the range is half-open, `[from, to)` — and any other field is
    refused (`validation_error`). A customer this tenant does not have is a 404.
    `more_to_do` says the selector matched more postings than one run takes;
    send the same body again and the next run continues where this one stopped.

    A run cannot be undone: completing an unresolved field happens exactly once,
    and the receipt is sealed after it. It requires the `admin` role.

    Args:
        body (ResolutionRunIn): Which postings this run should reach: a date range, a customer, an
            Event Type — in any combination, and any of them may be omitted.

            An omitted axis is unpinned rather than empty: a body naming nothing at all
            reaches every posting of this tenant that was never resolved. The date range
            is over the posting's own effective instant and is half-open — `[from, to)`
            — so running one month and then the next repairs each posting exactly once.

            A run reaches only postings whose status says they were never resolved, and
            that is a property of how the set is built rather than of what you send:
            there is no field here that could widen it to a posting already carrying a
            cost or a price, and none that could reach one whose charge was waived.

            Any other field is refused (`validation_error`). A run takes no condition of
            its own.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ResolutionRunOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
