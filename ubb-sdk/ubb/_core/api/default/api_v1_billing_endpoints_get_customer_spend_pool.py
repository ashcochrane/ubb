from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.customer_spend_pool_out import CustomerSpendPoolOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/billing/customers/{customer_id}/customer-spend-pool".format(customer_id=quote(str(customer_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> CustomerSpendPoolOut | None:
    if response.status_code == 200:
        response_200 = CustomerSpendPoolOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[CustomerSpendPoolOut]:
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

) -> Response[CustomerSpendPoolOut]:
    """ Get Customer Spend Pool

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerSpendPoolOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,

) -> CustomerSpendPoolOut | None:
    """ Get Customer Spend Pool

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerSpendPoolOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[CustomerSpendPoolOut]:
    """ Get Customer Spend Pool

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerSpendPoolOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,

) -> CustomerSpendPoolOut | None:
    """ Get Customer Spend Pool

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerSpendPoolOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,

    )).parsed
