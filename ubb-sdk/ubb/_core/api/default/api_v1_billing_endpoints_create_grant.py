from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.create_grant_request import CreateGrantRequest
from ...models.grant_out import GrantOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,
    *,
    body: CreateGrantRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/billing/customers/{customer_id}/grants".format(customer_id=quote(str(customer_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> GrantOut | None:
    if response.status_code == 200:
        response_200 = GrantOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[GrantOut]:
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
    body: CreateGrantRequest,

) -> Response[GrantOut]:
    """ Create Grant

     Create an expiring (or non-expiring) credit grant lot on the billing
    owner's wallet. Exactly-once via grant:{idempotency_key} — the GRANT
    WalletTransaction and the CreditGrant share one savepoint.

    Args:
        customer_id (UUID):
        body (CreateGrantRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GrantOut]
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
    body: CreateGrantRequest,

) -> GrantOut | None:
    """ Create Grant

     Create an expiring (or non-expiring) credit grant lot on the billing
    owner's wallet. Exactly-once via grant:{idempotency_key} — the GRANT
    WalletTransaction and the CreditGrant share one savepoint.

    Args:
        customer_id (UUID):
        body (CreateGrantRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GrantOut
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
    body: CreateGrantRequest,

) -> Response[GrantOut]:
    """ Create Grant

     Create an expiring (or non-expiring) credit grant lot on the billing
    owner's wallet. Exactly-once via grant:{idempotency_key} — the GRANT
    WalletTransaction and the CreditGrant share one savepoint.

    Args:
        customer_id (UUID):
        body (CreateGrantRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GrantOut]
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
    body: CreateGrantRequest,

) -> GrantOut | None:
    """ Create Grant

     Create an expiring (or non-expiring) credit grant lot on the billing
    owner's wallet. Exactly-once via grant:{idempotency_key} — the GRANT
    WalletTransaction and the CreditGrant share one savepoint.

    Args:
        customer_id (UUID):
        body (CreateGrantRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GrantOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
body=body,

    )).parsed
