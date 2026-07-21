from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.rate_in import RateIn
from ...models.rate_out import RateOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    book_id: UUID,
    *,
    body: RateIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/rate-cards/{book_id}/rates".format(book_id=quote(str(book_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | RateOut | None:
    if response.status_code == 200:
        response_200 = RateOut.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | RateOut]:
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
    body: RateIn,

) -> Response[ProblemOut | RateOut]:
    """ Add Rate

     Add a rate to a book. card_type and currency are inherited from the book
    (single source of truth); tier/enum validation mirrors the old flat create.
    Creates dedupe on natural identity (#78): a duplicate rate answers 409.

    Args:
        book_id (UUID):
        body (RateIn): A single Rate added under a book. card_type and currency are inherited
            from the book, so they are NOT accepted here (the book owns them).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | RateOut]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RateIn,

) -> ProblemOut | RateOut | None:
    """ Add Rate

     Add a rate to a book. card_type and currency are inherited from the book
    (single source of truth); tier/enum validation mirrors the old flat create.
    Creates dedupe on natural identity (#78): a duplicate rate answers 409.

    Args:
        book_id (UUID):
        body (RateIn): A single Rate added under a book. card_type and currency are inherited
            from the book, so they are NOT accepted here (the book owns them).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | RateOut
     """


    return sync_detailed(
        book_id=book_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RateIn,

) -> Response[ProblemOut | RateOut]:
    """ Add Rate

     Add a rate to a book. card_type and currency are inherited from the book
    (single source of truth); tier/enum validation mirrors the old flat create.
    Creates dedupe on natural identity (#78): a duplicate rate answers 409.

    Args:
        book_id (UUID):
        body (RateIn): A single Rate added under a book. card_type and currency are inherited
            from the book, so they are NOT accepted here (the book owns them).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | RateOut]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RateIn,

) -> ProblemOut | RateOut | None:
    """ Add Rate

     Add a rate to a book. card_type and currency are inherited from the book
    (single source of truth); tier/enum validation mirrors the old flat create.
    Creates dedupe on natural identity (#78): a duplicate rate answers 409.

    Args:
        book_id (UUID):
        body (RateIn): A single Rate added under a book. card_type and currency are inherited
            from the book, so they are NOT accepted here (the book owns them).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | RateOut
     """


    return (await asyncio_detailed(
        book_id=book_id,
client=client,
body=body,

    )).parsed
