from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.provider_list_out import ProviderListOut
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/providers",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProviderListOut | None:
    if response.status_code == 200:
        response_200 = ProviderListOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProviderListOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[ProviderListOut]:
    """ List Providers

     Every supplier this tenant has declared, retired ones included.

    Retirement is about what may be ATTACHED next and never about what may be
    READ: hiding retired suppliers here would make reading last quarter the
    clever path and the wrong answer the easy one.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProviderListOut]
     """


    kwargs = _get_kwargs(
        
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,

) -> ProviderListOut | None:
    """ List Providers

     Every supplier this tenant has declared, retired ones included.

    Retirement is about what may be ATTACHED next and never about what may be
    READ: hiding retired suppliers here would make reading last quarter the
    clever path and the wrong answer the easy one.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProviderListOut
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[ProviderListOut]:
    """ List Providers

     Every supplier this tenant has declared, retired ones included.

    Retirement is about what may be ATTACHED next and never about what may be
    READ: hiding retired suppliers here would make reading last quarter the
    clever path and the wrong answer the easy one.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProviderListOut]
     """


    kwargs = _get_kwargs(
        
    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,

) -> ProviderListOut | None:
    """ List Providers

     Every supplier this tenant has declared, retired ones included.

    Retirement is about what may be ATTACHED next and never about what may be
    READ: hiding retired suppliers here would make reading last quarter the
    clever path and the wrong answer the easy one.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProviderListOut
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
