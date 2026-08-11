from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.event_type_out import EventTypeOut
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    key: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/event-types/{key}/publish".format(key=quote(str(key), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> EventTypeOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = EventTypeOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[EventTypeOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    key: str,
    *,
    client: AuthenticatedClient,

) -> Response[EventTypeOut | ProblemOut]:
    """ Publish Event Type

     Publish the declaration, or refuse and say what is missing.

    A refusal rather than a partial publication: the two outcomes a caller must
    tell apart are published and not-published, and an incomplete mapping
    published anyway generates an integration that computes no cost at all.
    What is missing travels on the 409 so the caller can say which.

    Args:
        key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EventTypeOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        key=key,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    key: str,
    *,
    client: AuthenticatedClient,

) -> EventTypeOut | ProblemOut | None:
    """ Publish Event Type

     Publish the declaration, or refuse and say what is missing.

    A refusal rather than a partial publication: the two outcomes a caller must
    tell apart are published and not-published, and an incomplete mapping
    published anyway generates an integration that computes no cost at all.
    What is missing travels on the 409 so the caller can say which.

    Args:
        key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EventTypeOut | ProblemOut
     """


    return sync_detailed(
        key=key,
client=client,

    ).parsed

async def asyncio_detailed(
    key: str,
    *,
    client: AuthenticatedClient,

) -> Response[EventTypeOut | ProblemOut]:
    """ Publish Event Type

     Publish the declaration, or refuse and say what is missing.

    A refusal rather than a partial publication: the two outcomes a caller must
    tell apart are published and not-published, and an incomplete mapping
    published anyway generates an integration that computes no cost at all.
    What is missing travels on the 409 so the caller can say which.

    Args:
        key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EventTypeOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        key=key,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    key: str,
    *,
    client: AuthenticatedClient,

) -> EventTypeOut | ProblemOut | None:
    """ Publish Event Type

     Publish the declaration, or refuse and say what is missing.

    A refusal rather than a partial publication: the two outcomes a caller must
    tell apart are published and not-published, and an incomplete mapping
    published anyway generates an integration that computes no cost at all.
    What is missing travels on the 409 so the caller can say which.

    Args:
        key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EventTypeOut | ProblemOut
     """


    return (await asyncio_detailed(
        key=key,
client=client,

    )).parsed
