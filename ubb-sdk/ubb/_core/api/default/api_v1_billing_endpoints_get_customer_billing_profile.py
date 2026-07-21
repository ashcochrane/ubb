from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.customer_billing_profile_out import CustomerBillingProfileOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/billing/customers/{customer_id}/billing-profile".format(customer_id=quote(str(customer_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> CustomerBillingProfileOut | None:
    if response.status_code == 200:
        response_200 = CustomerBillingProfileOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[CustomerBillingProfileOut]:
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

) -> Response[CustomerBillingProfileOut]:
    """ Get Customer Billing Profile

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerBillingProfileOut]
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

) -> CustomerBillingProfileOut | None:
    """ Get Customer Billing Profile

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerBillingProfileOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[CustomerBillingProfileOut]:
    """ Get Customer Billing Profile

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerBillingProfileOut]
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

) -> CustomerBillingProfileOut | None:
    """ Get Customer Billing Profile

    Args:
        customer_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerBillingProfileOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,

    )).parsed
