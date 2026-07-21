from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.tenant_usage_invoice_list_response import TenantUsageInvoiceListResponse
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    period: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_period: None | str | Unset
    if isinstance(period, Unset):
        json_period = UNSET
    else:
        json_period = period
    params["period"] = json_period

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
        "url": "/api/v1/billing/tenant/usage-invoices",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> TenantUsageInvoiceListResponse | None:
    if response.status_code == 200:
        response_200 = TenantUsageInvoiceListResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[TenantUsageInvoiceListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    period: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[TenantUsageInvoiceListResponse]:
    """ List Tenant Usage Invoices

    Args:
        period (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TenantUsageInvoiceListResponse]
     """


    kwargs = _get_kwargs(
        period=period,
cursor=cursor,
limit=limit,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    period: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> TenantUsageInvoiceListResponse | None:
    """ List Tenant Usage Invoices

    Args:
        period (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TenantUsageInvoiceListResponse
     """


    return sync_detailed(
        client=client,
period=period,
cursor=cursor,
limit=limit,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    period: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[TenantUsageInvoiceListResponse]:
    """ List Tenant Usage Invoices

    Args:
        period (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TenantUsageInvoiceListResponse]
     """


    kwargs = _get_kwargs(
        period=period,
cursor=cursor,
limit=limit,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    period: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> TenantUsageInvoiceListResponse | None:
    """ List Tenant Usage Invoices

    Args:
        period (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TenantUsageInvoiceListResponse
     """


    return (await asyncio_detailed(
        client=client,
period=period,
cursor=cursor,
limit=limit,

    )).parsed
