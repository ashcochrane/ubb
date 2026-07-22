from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.create_top_up_request import CreateTopUpRequest
from ...models.top_up_checkout_response import TopUpCheckoutResponse
from typing import cast



def _get_kwargs(
    customer_id: str,
    *,
    body: CreateTopUpRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/billing/customers/{customer_id}/top-up".format(customer_id=quote(str(customer_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> TopUpCheckoutResponse | None:
    if response.status_code == 200:
        response_200 = TopUpCheckoutResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[TopUpCheckoutResponse]:
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
    body: CreateTopUpRequest,

) -> Response[TopUpCheckoutResponse]:
    """ Create Top Up

     Start a top-up. Replay-safe: idempotency_key is required and unique
    per customer — a retried call re-uses the original attempt and never
    starts a second charge.

    Args:
        customer_id (str):
        body (CreateTopUpRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TopUpCheckoutResponse]
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
    customer_id: str,
    *,
    client: AuthenticatedClient,
    body: CreateTopUpRequest,

) -> TopUpCheckoutResponse | None:
    """ Create Top Up

     Start a top-up. Replay-safe: idempotency_key is required and unique
    per customer — a retried call re-uses the original attempt and never
    starts a second charge.

    Args:
        customer_id (str):
        body (CreateTopUpRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TopUpCheckoutResponse
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    body: CreateTopUpRequest,

) -> Response[TopUpCheckoutResponse]:
    """ Create Top Up

     Start a top-up. Replay-safe: idempotency_key is required and unique
    per customer — a retried call re-uses the original attempt and never
    starts a second charge.

    Args:
        customer_id (str):
        body (CreateTopUpRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TopUpCheckoutResponse]
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
    customer_id: str,
    *,
    client: AuthenticatedClient,
    body: CreateTopUpRequest,

) -> TopUpCheckoutResponse | None:
    """ Create Top Up

     Start a top-up. Replay-safe: idempotency_key is required and unique
    per customer — a retried call re-uses the original attempt and never
    starts a second charge.

    Args:
        customer_id (str):
        body (CreateTopUpRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TopUpCheckoutResponse
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
body=body,

    )).parsed
