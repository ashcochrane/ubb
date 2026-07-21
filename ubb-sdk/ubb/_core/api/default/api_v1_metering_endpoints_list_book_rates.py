from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.paginated_rates import PaginatedRates
from ...models.problem_out import ProblemOut
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime



def _get_kwargs(
    book_id: UUID,
    *,
    include_history: bool | Unset = False,
    as_of: datetime.datetime | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["include_history"] = include_history

    json_as_of: None | str | Unset
    if isinstance(as_of, Unset):
        json_as_of = UNSET
    elif isinstance(as_of, datetime.datetime):
        json_as_of = as_of.isoformat()
    else:
        json_as_of = as_of
    params["as_of"] = json_as_of

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
        "url": "/api/v1/metering/pricing/rate-cards/{book_id}/rates".format(book_id=quote(str(book_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> PaginatedRates | ProblemOut | None:
    if response.status_code == 200:
        response_200 = PaginatedRates.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[PaginatedRates | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    include_history: bool | Unset = False,
    as_of: datetime.datetime | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[PaginatedRates | ProblemOut]:
    """ List Book Rates

     List the rates in a book, newest first. Active-only by default;
    ``include_history`` returns every version (superseded rows carry a
    ``valid_to``), and ``as_of`` returns the version active at that instant
    (point-in-time).

    Args:
        book_id (UUID):
        include_history (bool | Unset):  Default: False.
        as_of (datetime.datetime | None | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PaginatedRates | ProblemOut]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
include_history=include_history,
as_of=as_of,
cursor=cursor,
limit=limit,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    include_history: bool | Unset = False,
    as_of: datetime.datetime | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> PaginatedRates | ProblemOut | None:
    """ List Book Rates

     List the rates in a book, newest first. Active-only by default;
    ``include_history`` returns every version (superseded rows carry a
    ``valid_to``), and ``as_of`` returns the version active at that instant
    (point-in-time).

    Args:
        book_id (UUID):
        include_history (bool | Unset):  Default: False.
        as_of (datetime.datetime | None | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PaginatedRates | ProblemOut
     """


    return sync_detailed(
        book_id=book_id,
client=client,
include_history=include_history,
as_of=as_of,
cursor=cursor,
limit=limit,

    ).parsed

async def asyncio_detailed(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    include_history: bool | Unset = False,
    as_of: datetime.datetime | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[PaginatedRates | ProblemOut]:
    """ List Book Rates

     List the rates in a book, newest first. Active-only by default;
    ``include_history`` returns every version (superseded rows carry a
    ``valid_to``), and ``as_of`` returns the version active at that instant
    (point-in-time).

    Args:
        book_id (UUID):
        include_history (bool | Unset):  Default: False.
        as_of (datetime.datetime | None | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PaginatedRates | ProblemOut]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
include_history=include_history,
as_of=as_of,
cursor=cursor,
limit=limit,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    include_history: bool | Unset = False,
    as_of: datetime.datetime | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> PaginatedRates | ProblemOut | None:
    """ List Book Rates

     List the rates in a book, newest first. Active-only by default;
    ``include_history`` returns every version (superseded rows carry a
    ``valid_to``), and ``as_of`` returns the version active at that instant
    (point-in-time).

    Args:
        book_id (UUID):
        include_history (bool | Unset):  Default: False.
        as_of (datetime.datetime | None | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PaginatedRates | ProblemOut
     """


    return (await asyncio_detailed(
        book_id=book_id,
client=client,
include_history=include_history,
as_of=as_of,
cursor=cursor,
limit=limit,

    )).parsed
