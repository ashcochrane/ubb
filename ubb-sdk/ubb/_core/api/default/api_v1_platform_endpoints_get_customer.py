from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.customer_identity_out import CustomerIdentityOut
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    customer_id: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/platform/customers/{customer_id}".format(customer_id=quote(str(customer_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> CustomerIdentityOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = CustomerIdentityOut.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[CustomerIdentityOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    customer_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[CustomerIdentityOut | ProblemOut]:
    """ Get Customer

     One customer's identity: who UBB knows them as, and who you call them.

    Read this where you hold UBB's id for a customer and need the id you gave
    them — the subscription lifecycle is addressed by your own external id while
    every metering and billing read is addressed by UBB's, and this is what
    bridges the two.

    It answers about identity and says nothing about money: what a customer cost
    or earned is one question asked at
    `GET /metering/analytics/economics`, filtered to them.

    Args:
        customer_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerIdentityOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: str,
    *,
    client: AuthenticatedClient,

) -> CustomerIdentityOut | ProblemOut | None:
    """ Get Customer

     One customer's identity: who UBB knows them as, and who you call them.

    Read this where you hold UBB's id for a customer and need the id you gave
    them — the subscription lifecycle is addressed by your own external id while
    every metering and billing read is addressed by UBB's, and this is what
    bridges the two.

    It answers about identity and says nothing about money: what a customer cost
    or earned is one question asked at
    `GET /metering/analytics/economics`, filtered to them.

    Args:
        customer_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerIdentityOut | ProblemOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,

    ).parsed

async def asyncio_detailed(
    customer_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[CustomerIdentityOut | ProblemOut]:
    """ Get Customer

     One customer's identity: who UBB knows them as, and who you call them.

    Read this where you hold UBB's id for a customer and need the id you gave
    them — the subscription lifecycle is addressed by your own external id while
    every metering and billing read is addressed by UBB's, and this is what
    bridges the two.

    It answers about identity and says nothing about money: what a customer cost
    or earned is one question asked at
    `GET /metering/analytics/economics`, filtered to them.

    Args:
        customer_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CustomerIdentityOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: str,
    *,
    client: AuthenticatedClient,

) -> CustomerIdentityOut | ProblemOut | None:
    """ Get Customer

     One customer's identity: who UBB knows them as, and who you call them.

    Read this where you hold UBB's id for a customer and need the id you gave
    them — the subscription lifecycle is addressed by your own external id while
    every metering and billing read is addressed by UBB's, and this is what
    bridges the two.

    It answers about identity and says nothing about money: what a customer cost
    or earned is one question asked at
    `GET /metering/analytics/economics`, filtered to them.

    Args:
        customer_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CustomerIdentityOut | ProblemOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,

    )).parsed
