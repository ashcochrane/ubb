from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.customer_spend_pool_status_out import CustomerSpendPoolStatusOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/billing/customers/{customer_id}/customer-spend-pool/status".format(customer_id=quote(str(customer_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> CustomerSpendPoolStatusOut | None:
    if response.status_code == 200:
        response_200 = CustomerSpendPoolStatusOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[CustomerSpendPoolStatusOut]:
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

) -> Response[CustomerSpendPoolStatusOut]:
    """ Get Customer Spend Pool Status

     Where this customer's known period charges stand against the pool that
    applies to them. The basis is the durable pair the pool is measured over —
    the figure the live counter rebuilds from and MAX-merges toward, never the
    counter itself — beside the configured amount and the assessment the
    kernel's crossing module composes over it (#456, slice 6 §13).

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerSpendPoolStatusOut]
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

) -> CustomerSpendPoolStatusOut | None:
    """ Get Customer Spend Pool Status

     Where this customer's known period charges stand against the pool that
    applies to them. The basis is the durable pair the pool is measured over —
    the figure the live counter rebuilds from and MAX-merges toward, never the
    counter itself — beside the configured amount and the assessment the
    kernel's crossing module composes over it (#456, slice 6 §13).

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerSpendPoolStatusOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[CustomerSpendPoolStatusOut]:
    """ Get Customer Spend Pool Status

     Where this customer's known period charges stand against the pool that
    applies to them. The basis is the durable pair the pool is measured over —
    the figure the live counter rebuilds from and MAX-merges toward, never the
    counter itself — beside the configured amount and the assessment the
    kernel's crossing module composes over it (#456, slice 6 §13).

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerSpendPoolStatusOut]
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

) -> CustomerSpendPoolStatusOut | None:
    """ Get Customer Spend Pool Status

     Where this customer's known period charges stand against the pool that
    applies to them. The basis is the durable pair the pool is measured over —
    the figure the live counter rebuilds from and MAX-merges toward, never the
    counter itself — beside the configured amount and the assessment the
    kernel's crossing module composes over it (#456, slice 6 §13).

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerSpendPoolStatusOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,

    )).parsed
