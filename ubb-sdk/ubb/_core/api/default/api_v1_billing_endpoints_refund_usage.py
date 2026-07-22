from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.refund_request import RefundRequest
from ...models.refund_response import RefundResponse
from typing import cast



def _get_kwargs(
    customer_id: str,
    *,
    body: RefundRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/billing/customers/{customer_id}/refund".format(customer_id=quote(str(customer_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> RefundResponse | None:
    if response.status_code == 200:
        response_200 = RefundResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[RefundResponse]:
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
    body: RefundRequest,

) -> Response[RefundResponse]:
    """ Refund Usage

     Refund a usage charge. LOT-AWARE (F4.3): the slices of the original
    USAGE_DEDUCTION that were funded by still-live grant lots are re-funded
    back into those lots (promo refunds restore the promo lot — they never
    become withdrawable cash); only the base-funded remainder, plus shares
    from since-expired/voided lots, lands as base credit.

    Args:
        customer_id (str):
        body (RefundRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[RefundResponse]
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
    body: RefundRequest,

) -> RefundResponse | None:
    """ Refund Usage

     Refund a usage charge. LOT-AWARE (F4.3): the slices of the original
    USAGE_DEDUCTION that were funded by still-live grant lots are re-funded
    back into those lots (promo refunds restore the promo lot — they never
    become withdrawable cash); only the base-funded remainder, plus shares
    from since-expired/voided lots, lands as base credit.

    Args:
        customer_id (str):
        body (RefundRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        RefundResponse
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
    body: RefundRequest,

) -> Response[RefundResponse]:
    """ Refund Usage

     Refund a usage charge. LOT-AWARE (F4.3): the slices of the original
    USAGE_DEDUCTION that were funded by still-live grant lots are re-funded
    back into those lots (promo refunds restore the promo lot — they never
    become withdrawable cash); only the base-funded remainder, plus shares
    from since-expired/voided lots, lands as base credit.

    Args:
        customer_id (str):
        body (RefundRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[RefundResponse]
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
    body: RefundRequest,

) -> RefundResponse | None:
    """ Refund Usage

     Refund a usage charge. LOT-AWARE (F4.3): the slices of the original
    USAGE_DEDUCTION that were funded by still-live grant lots are re-funded
    back into those lots (promo refunds restore the promo lot — they never
    become withdrawable cash); only the base-funded remainder, plus shares
    from since-expired/voided lots, lands as base credit.

    Args:
        customer_id (str):
        body (RefundRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        RefundResponse
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
body=body,

    )).parsed
