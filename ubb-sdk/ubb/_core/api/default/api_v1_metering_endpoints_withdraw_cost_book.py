from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.status_response import StatusResponse
from typing import cast
from uuid import UUID



def _get_kwargs(
    book_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/metering/pricing/cost-books/{book_id}".format(book_id=quote(str(book_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | StatusResponse | None:
    if response.status_code == 200:
        response_200 = StatusResponse.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if response.status_code == 409:
        response_409 = ProblemOut.from_dict(response.json())



        return response_409

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | StatusResponse]:
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

) -> Response[ProblemOut | StatusResponse]:
    """ Withdraw Cost Book

     Withdraw a cost book the tenant no longer records costs from.

    **A book that has EVER held a rule is not withdrawn, it answers 409**, for
    the reason `withdraw_pricing_book` gives in full: a retired rule is kept
    rather than removed, and the receipts explaining what past work cost point
    at it. So does a book with a change recorded against it.

    Args:
        book_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | StatusResponse]
     """


    kwargs = _get_kwargs(
        book_id=book_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    book_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ProblemOut | StatusResponse | None:
    """ Withdraw Cost Book

     Withdraw a cost book the tenant no longer records costs from.

    **A book that has EVER held a rule is not withdrawn, it answers 409**, for
    the reason `withdraw_pricing_book` gives in full: a retired rule is kept
    rather than removed, and the receipts explaining what past work cost point
    at it. So does a book with a change recorded against it.

    Args:
        book_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | StatusResponse
     """


    return sync_detailed(
        book_id=book_id,
client=client,

    ).parsed

async def asyncio_detailed(
    book_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ProblemOut | StatusResponse]:
    """ Withdraw Cost Book

     Withdraw a cost book the tenant no longer records costs from.

    **A book that has EVER held a rule is not withdrawn, it answers 409**, for
    the reason `withdraw_pricing_book` gives in full: a retired rule is kept
    rather than removed, and the receipts explaining what past work cost point
    at it. So does a book with a change recorded against it.

    Args:
        book_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | StatusResponse]
     """


    kwargs = _get_kwargs(
        book_id=book_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    book_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ProblemOut | StatusResponse | None:
    """ Withdraw Cost Book

     Withdraw a cost book the tenant no longer records costs from.

    **A book that has EVER held a rule is not withdrawn, it answers 409**, for
    the reason `withdraw_pricing_book` gives in full: a retired rule is kept
    rather than removed, and the receipts explaining what past work cost point
    at it. So does a book with a change recorded against it.

    Args:
        book_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | StatusResponse
     """


    return (await asyncio_detailed(
        book_id=book_id,
client=client,

    )).parsed
