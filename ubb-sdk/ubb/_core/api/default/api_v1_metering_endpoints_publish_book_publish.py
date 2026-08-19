from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.book_publish_out import BookPublishOut
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    book_id: UUID,
    publish_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/rate-cards/{book_id}/publishes/{publish_id}/publish".format(book_id=quote(str(book_id), safe=""),publish_id=quote(str(publish_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> BookPublishOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = BookPublishOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[BookPublishOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    book_id: UUID,
    publish_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[BookPublishOut | ProblemOut]:
    """ Publish Book Publish

     Publish a declared change: close each superseded rule, open its
    replacement, from one value.

    All-or-nothing, and nothing runs at the effective instant — the rows are
    written now, carrying the boundary as a value the resolver reads.

    Args:
        book_id (UUID):
        publish_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookPublishOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
publish_id=publish_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    book_id: UUID,
    publish_id: UUID,
    *,
    client: AuthenticatedClient,

) -> BookPublishOut | ProblemOut | None:
    """ Publish Book Publish

     Publish a declared change: close each superseded rule, open its
    replacement, from one value.

    All-or-nothing, and nothing runs at the effective instant — the rows are
    written now, carrying the boundary as a value the resolver reads.

    Args:
        book_id (UUID):
        publish_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookPublishOut | ProblemOut
     """


    return sync_detailed(
        book_id=book_id,
publish_id=publish_id,
client=client,

    ).parsed

async def asyncio_detailed(
    book_id: UUID,
    publish_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[BookPublishOut | ProblemOut]:
    """ Publish Book Publish

     Publish a declared change: close each superseded rule, open its
    replacement, from one value.

    All-or-nothing, and nothing runs at the effective instant — the rows are
    written now, carrying the boundary as a value the resolver reads.

    Args:
        book_id (UUID):
        publish_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookPublishOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
publish_id=publish_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    book_id: UUID,
    publish_id: UUID,
    *,
    client: AuthenticatedClient,

) -> BookPublishOut | ProblemOut | None:
    """ Publish Book Publish

     Publish a declared change: close each superseded rule, open its
    replacement, from one value.

    All-or-nothing, and nothing runs at the effective instant — the rows are
    written now, carrying the boundary as a value the resolver reads.

    Args:
        book_id (UUID):
        publish_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookPublishOut | ProblemOut
     """


    return (await asyncio_detailed(
        book_id=book_id,
publish_id=publish_id,
client=client,

    )).parsed
