from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.tenant_default_markup_out import TenantDefaultMarkupOut
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/pricing/default-markup",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> TenantDefaultMarkupOut | None:
    if response.status_code == 200:
        response_200 = TenantDefaultMarkupOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[TenantDefaultMarkupOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[TenantDefaultMarkupOut]:
    """ Get Tenant Default Markup

     What the tenant has declared, or null if they have declared nothing.

    ⚠ **NULL, NOT ZERO.** UBB ships no catalogue, and a tenant with no
    declaration has no markup rung — every event they record with no matching
    rule prices to `unknown`. Answering `0` would say they had decided to charge
    exactly what their calls cost, which is a different decision and one nobody
    made.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TenantDefaultMarkupOut]
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

) -> TenantDefaultMarkupOut | None:
    """ Get Tenant Default Markup

     What the tenant has declared, or null if they have declared nothing.

    ⚠ **NULL, NOT ZERO.** UBB ships no catalogue, and a tenant with no
    declaration has no markup rung — every event they record with no matching
    rule prices to `unknown`. Answering `0` would say they had decided to charge
    exactly what their calls cost, which is a different decision and one nobody
    made.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TenantDefaultMarkupOut
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[TenantDefaultMarkupOut]:
    """ Get Tenant Default Markup

     What the tenant has declared, or null if they have declared nothing.

    ⚠ **NULL, NOT ZERO.** UBB ships no catalogue, and a tenant with no
    declaration has no markup rung — every event they record with no matching
    rule prices to `unknown`. Answering `0` would say they had decided to charge
    exactly what their calls cost, which is a different decision and one nobody
    made.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TenantDefaultMarkupOut]
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

) -> TenantDefaultMarkupOut | None:
    """ Get Tenant Default Markup

     What the tenant has declared, or null if they have declared nothing.

    ⚠ **NULL, NOT ZERO.** UBB ships no catalogue, and a tenant with no
    declaration has no markup rung — every event they record with no matching
    rule prices to `unknown`. Answering `0` would say they had decided to charge
    exactly what their calls cost, which is a different decision and one nobody
    made.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TenantDefaultMarkupOut
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
