from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.margin_trend_out import MarginTrendOut
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,
    *,
    periods: int | Unset = 6,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["periods"] = periods


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/margin/customers/{customer_id}/trend".format(customer_id=quote(str(customer_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> MarginTrendOut | None:
    if response.status_code == 200:
        response_200 = MarginTrendOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[MarginTrendOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    periods: int | Unset = 6,

) -> Response[MarginTrendOut]:
    """ Margin Trend

    Args:
        customer_id (UUID):
        periods (int | Unset):  Default: 6.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MarginTrendOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
periods=periods,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    periods: int | Unset = 6,

) -> MarginTrendOut | None:
    """ Margin Trend

    Args:
        customer_id (UUID):
        periods (int | Unset):  Default: 6.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MarginTrendOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
periods=periods,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    periods: int | Unset = 6,

) -> Response[MarginTrendOut]:
    """ Margin Trend

    Args:
        customer_id (UUID):
        periods (int | Unset):  Default: 6.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MarginTrendOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
periods=periods,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    periods: int | Unset = 6,

) -> MarginTrendOut | None:
    """ Margin Trend

    Args:
        customer_id (UUID):
        periods (int | Unset):  Default: 6.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MarginTrendOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
periods=periods,

    )).parsed
