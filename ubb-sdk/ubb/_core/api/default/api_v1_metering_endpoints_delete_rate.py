from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.status_response import StatusResponse
from typing import cast
from uuid import UUID



def _get_kwargs(
    book_id: UUID,
    rate_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/metering/pricing/rate-cards/{book_id}/rates/{rate_id}".format(book_id=quote(str(book_id), safe=""),rate_id=quote(str(rate_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> StatusResponse | None:
    if response.status_code == 200:
        response_200 = StatusResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[StatusResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    book_id: UUID,
    rate_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[StatusResponse]:
    """ Delete Rate

     Retire (soft-expire) a single rate within its book. Addressed under its
    book — matching GET/POST /pricing/rate-cards/{book_id}/rates — so the path
    noun (``rates``) agrees with the identifier it takes (#86 sweep: this route
    previously took a rate id on a bare ``/pricing/rate-cards/{card_id}`` path).

    Args:
        book_id (UUID):
        rate_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[StatusResponse]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
rate_id=rate_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    book_id: UUID,
    rate_id: UUID,
    *,
    client: AuthenticatedClient,

) -> StatusResponse | None:
    """ Delete Rate

     Retire (soft-expire) a single rate within its book. Addressed under its
    book — matching GET/POST /pricing/rate-cards/{book_id}/rates — so the path
    noun (``rates``) agrees with the identifier it takes (#86 sweep: this route
    previously took a rate id on a bare ``/pricing/rate-cards/{card_id}`` path).

    Args:
        book_id (UUID):
        rate_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        StatusResponse
     """


    return sync_detailed(
        book_id=book_id,
rate_id=rate_id,
client=client,

    ).parsed

async def asyncio_detailed(
    book_id: UUID,
    rate_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[StatusResponse]:
    """ Delete Rate

     Retire (soft-expire) a single rate within its book. Addressed under its
    book — matching GET/POST /pricing/rate-cards/{book_id}/rates — so the path
    noun (``rates``) agrees with the identifier it takes (#86 sweep: this route
    previously took a rate id on a bare ``/pricing/rate-cards/{card_id}`` path).

    Args:
        book_id (UUID):
        rate_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[StatusResponse]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
rate_id=rate_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    book_id: UUID,
    rate_id: UUID,
    *,
    client: AuthenticatedClient,

) -> StatusResponse | None:
    """ Delete Rate

     Retire (soft-expire) a single rate within its book. Addressed under its
    book — matching GET/POST /pricing/rate-cards/{book_id}/rates — so the path
    noun (``rates``) agrees with the identifier it takes (#86 sweep: this route
    previously took a rate id on a bare ``/pricing/rate-cards/{card_id}`` path).

    Args:
        book_id (UUID):
        rate_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        StatusResponse
     """


    return (await asyncio_detailed(
        book_id=book_id,
rate_id=rate_id,
client=client,

    )).parsed
