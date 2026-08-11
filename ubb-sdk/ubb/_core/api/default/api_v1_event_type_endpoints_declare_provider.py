from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.provider_in import ProviderIn
from ...models.provider_out import ProviderOut
from typing import cast



def _get_kwargs(
    *,
    body: ProviderIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/providers",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | ProviderOut | None:
    if response.status_code == 201:
        response_201 = ProviderOut.from_dict(response.json())



        return response_201

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | ProviderOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ProviderIn,

) -> Response[ProblemOut | ProviderOut]:
    """ Declare Provider

     Declare a supplier. The key is the tenant's own handle for it.

    Args:
        body (ProviderIn): Declare a supplier. The key is the tenant's own handle for it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ProviderOut]
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
    body: ProviderIn,

) -> ProblemOut | ProviderOut | None:
    """ Declare Provider

     Declare a supplier. The key is the tenant's own handle for it.

    Args:
        body (ProviderIn): Declare a supplier. The key is the tenant's own handle for it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ProviderOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ProviderIn,

) -> Response[ProblemOut | ProviderOut]:
    """ Declare Provider

     Declare a supplier. The key is the tenant's own handle for it.

    Args:
        body (ProviderIn): Declare a supplier. The key is the tenant's own handle for it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ProviderOut]
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
    body: ProviderIn,

) -> ProblemOut | ProviderOut | None:
    """ Declare Provider

     Declare a supplier. The key is the tenant's own handle for it.

    Args:
        body (ProviderIn): Declare a supplier. The key is the tenant's own handle for it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ProviderOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
