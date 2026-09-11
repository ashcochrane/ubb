from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.customer_spend_pool_in import CustomerSpendPoolIn
from ...models.customer_spend_pool_out import CustomerSpendPoolOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,
    *,
    body: CustomerSpendPoolIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/billing/customers/{customer_id}/customer-spend-pool".format(customer_id=quote(str(customer_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    body: CustomerSpendPoolIn,

) -> Response[CustomerSpendPoolOut]:
    """ Put Customer Spend Pool

    Args:
        customer_id (UUID):
        body (CustomerSpendPoolIn): Declare a customer spend pool — a bound on the customer's
            period
            charges (#150 §7). On the tenant route this is the default every seat
            inherits; on the customer route it is that customer's own pool. A row on
            a business is the owner-level pool and a row on a seat the seat-level
            pool, so the level is where the row is declared and needs no field.
            `cap_micros` of 0 declares no pool.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerSpendPoolOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CustomerSpendPoolIn,

) -> CustomerSpendPoolOut | None:
    """ Put Customer Spend Pool

    Args:
        customer_id (UUID):
        body (CustomerSpendPoolIn): Declare a customer spend pool — a bound on the customer's
            period
            charges (#150 §7). On the tenant route this is the default every seat
            inherits; on the customer route it is that customer's own pool. A row on
            a business is the owner-level pool and a row on a seat the seat-level
            pool, so the level is where the row is declared and needs no field.
            `cap_micros` of 0 declares no pool.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerSpendPoolOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CustomerSpendPoolIn,

) -> Response[CustomerSpendPoolOut]:
    """ Put Customer Spend Pool

    Args:
        customer_id (UUID):
        body (CustomerSpendPoolIn): Declare a customer spend pool — a bound on the customer's
            period
            charges (#150 §7). On the tenant route this is the default every seat
            inherits; on the customer route it is that customer's own pool. A row on
            a business is the owner-level pool and a row on a seat the seat-level
            pool, so the level is where the row is declared and needs no field.
            `cap_micros` of 0 declares no pool.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerSpendPoolOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CustomerSpendPoolIn,

) -> CustomerSpendPoolOut | None:
    """ Put Customer Spend Pool

    Args:
        customer_id (UUID):
        body (CustomerSpendPoolIn): Declare a customer spend pool — a bound on the customer's
            period
            charges (#150 §7). On the tenant route this is the default every seat
            inherits; on the customer route it is that customer's own pool. A row on
            a business is the owner-level pool and a row on a seat the seat-level
            pool, so the level is where the row is declared and needs no field.
            `cap_micros` of 0 declares no pool.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerSpendPoolOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
body=body,

    )).parsed
