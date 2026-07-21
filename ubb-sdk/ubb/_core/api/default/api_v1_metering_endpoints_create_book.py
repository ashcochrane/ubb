from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.book_in import BookIn
from ...models.book_out import BookOut
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    *,
    body: BookIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/rate-cards",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> BookOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = BookOut.from_dict(response.json())



        return response_200

    if response.status_code == 409:
        response_409 = ProblemOut.from_dict(response.json())



        return response_409

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[BookOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: BookIn,

) -> Response[BookOut | ProblemOut]:
    """ Create Book

     Create a rate-card BOOK. Rates are added under it (so every API-created
    rate is book-scoped and therefore resolvable). Creates dedupe on natural
    identity (#78): a duplicate book answers 409.

    Args:
        body (BookIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookOut | ProblemOut]
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
    body: BookIn,

) -> BookOut | ProblemOut | None:
    """ Create Book

     Create a rate-card BOOK. Rates are added under it (so every API-created
    rate is book-scoped and therefore resolvable). Creates dedupe on natural
    identity (#78): a duplicate book answers 409.

    Args:
        body (BookIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookOut | ProblemOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: BookIn,

) -> Response[BookOut | ProblemOut]:
    """ Create Book

     Create a rate-card BOOK. Rates are added under it (so every API-created
    rate is book-scoped and therefore resolvable). Creates dedupe on natural
    identity (#78): a duplicate book answers 409.

    Args:
        body (BookIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookOut | ProblemOut]
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
    body: BookIn,

) -> BookOut | ProblemOut | None:
    """ Create Book

     Create a rate-card BOOK. Rates are added under it (so every API-created
    rate is book-scoped and therefore resolvable). Creates dedupe on natural
    identity (#78): a duplicate book answers 409.

    Args:
        body (BookIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookOut | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
