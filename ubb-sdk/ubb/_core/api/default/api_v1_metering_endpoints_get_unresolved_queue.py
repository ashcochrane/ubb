from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.paginated_unresolved_queue import PaginatedUnresolvedQueue
from ...models.problem_out import ProblemOut
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime



def _get_kwargs(
    *,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_selected_from: None | str | Unset
    if isinstance(selected_from, Unset):
        json_selected_from = UNSET
    elif isinstance(selected_from, datetime.datetime):
        json_selected_from = selected_from.isoformat()
    else:
        json_selected_from = selected_from
    params["selected_from"] = json_selected_from

    json_selected_to: None | str | Unset
    if isinstance(selected_to, Unset):
        json_selected_to = UNSET
    elif isinstance(selected_to, datetime.datetime):
        json_selected_to = selected_to.isoformat()
    else:
        json_selected_to = selected_to
    params["selected_to"] = json_selected_to

    json_selected_customer_id: None | str | Unset
    if isinstance(selected_customer_id, Unset):
        json_selected_customer_id = UNSET
    elif isinstance(selected_customer_id, UUID):
        json_selected_customer_id = str(selected_customer_id)
    else:
        json_selected_customer_id = selected_customer_id
    params["selected_customer_id"] = json_selected_customer_id

    params["selected_event_type"] = selected_event_type

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params["limit"] = limit


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/pricing/unresolved-queue",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> PaginatedUnresolvedQueue | ProblemOut | None:
    if response.status_code == 200:
        response_200 = PaginatedUnresolvedQueue.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[PaginatedUnresolvedQueue | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[PaginatedUnresolvedQueue | ProblemOut]:
    """ Get Unresolved Queue

     Everything UBB could not resolve: a supplier cost it never learned, a
    customer price it could not work out, or both.

    Each row carries the status that put it in the list and, for a supplier
    cost, the recorded reason the cost is missing. An amount UBB does not have
    is `null`, never a zero.

    These are exactly the postings a Resolution Run over the same filter would
    take up. The filter is the run's: a date range over the posting's own
    effective instant (half-open, `[selected_from, selected_to)`), a customer,
    and an Event Type, in any combination. A customer this tenant does not have
    is a 404; a stated window longer than 366 days is a `validation_error`.

    `totals` is over the whole filter rather than over one page, one row per
    currency, and says how many postings each figure could not include.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PaginatedUnresolvedQueue | ProblemOut]
     """


    kwargs = _get_kwargs(
        selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,
cursor=cursor,
limit=limit,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> PaginatedUnresolvedQueue | ProblemOut | None:
    """ Get Unresolved Queue

     Everything UBB could not resolve: a supplier cost it never learned, a
    customer price it could not work out, or both.

    Each row carries the status that put it in the list and, for a supplier
    cost, the recorded reason the cost is missing. An amount UBB does not have
    is `null`, never a zero.

    These are exactly the postings a Resolution Run over the same filter would
    take up. The filter is the run's: a date range over the posting's own
    effective instant (half-open, `[selected_from, selected_to)`), a customer,
    and an Event Type, in any combination. A customer this tenant does not have
    is a 404; a stated window longer than 366 days is a `validation_error`.

    `totals` is over the whole filter rather than over one page, one row per
    currency, and says how many postings each figure could not include.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PaginatedUnresolvedQueue | ProblemOut
     """


    return sync_detailed(
        client=client,
selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,
cursor=cursor,
limit=limit,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[PaginatedUnresolvedQueue | ProblemOut]:
    """ Get Unresolved Queue

     Everything UBB could not resolve: a supplier cost it never learned, a
    customer price it could not work out, or both.

    Each row carries the status that put it in the list and, for a supplier
    cost, the recorded reason the cost is missing. An amount UBB does not have
    is `null`, never a zero.

    These are exactly the postings a Resolution Run over the same filter would
    take up. The filter is the run's: a date range over the posting's own
    effective instant (half-open, `[selected_from, selected_to)`), a customer,
    and an Event Type, in any combination. A customer this tenant does not have
    is a 404; a stated window longer than 366 days is a `validation_error`.

    `totals` is over the whole filter rather than over one page, one row per
    currency, and says how many postings each figure could not include.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PaginatedUnresolvedQueue | ProblemOut]
     """


    kwargs = _get_kwargs(
        selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,
cursor=cursor,
limit=limit,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> PaginatedUnresolvedQueue | ProblemOut | None:
    """ Get Unresolved Queue

     Everything UBB could not resolve: a supplier cost it never learned, a
    customer price it could not work out, or both.

    Each row carries the status that put it in the list and, for a supplier
    cost, the recorded reason the cost is missing. An amount UBB does not have
    is `null`, never a zero.

    These are exactly the postings a Resolution Run over the same filter would
    take up. The filter is the run's: a date range over the posting's own
    effective instant (half-open, `[selected_from, selected_to)`), a customer,
    and an Event Type, in any combination. A customer this tenant does not have
    is a 404; a stated window longer than 366 days is a `validation_error`.

    `totals` is over the whole filter rather than over one page, one row per
    currency, and says how many postings each figure could not include.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PaginatedUnresolvedQueue | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,
cursor=cursor,
limit=limit,

    )).parsed
