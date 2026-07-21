from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.credit_request import CreditRequest
from ...models.debit_credit_response import DebitCreditResponse
from typing import cast



def _get_kwargs(
    *,
    body: CreditRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/billing/credit",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> DebitCreditResponse | None:
    if response.status_code == 200:
        response_200 = DebitCreditResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[DebitCreditResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: CreditRequest,

) -> Response[DebitCreditResponse]:
    """ Credit

     Credit the wallet with LEGACY BASE money (non-expiring, no grant lot).

    Deliberately untouched by F4.3: base is derived (balance minus active
    grant remainders), so an ADJUSTMENT credit simply grows base. Tenants who
    want expiring or promo credit use POST /customers/{id}/grants instead.

    Args:
        body (CreditRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DebitCreditResponse]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    body: CreditRequest,

) -> DebitCreditResponse | None:
    """ Credit

     Credit the wallet with LEGACY BASE money (non-expiring, no grant lot).

    Deliberately untouched by F4.3: base is derived (balance minus active
    grant remainders), so an ADJUSTMENT credit simply grows base. Tenants who
    want expiring or promo credit use POST /customers/{id}/grants instead.

    Args:
        body (CreditRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DebitCreditResponse
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: CreditRequest,

) -> Response[DebitCreditResponse]:
    """ Credit

     Credit the wallet with LEGACY BASE money (non-expiring, no grant lot).

    Deliberately untouched by F4.3: base is derived (balance minus active
    grant remainders), so an ADJUSTMENT credit simply grows base. Tenants who
    want expiring or promo credit use POST /customers/{id}/grants instead.

    Args:
        body (CreditRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DebitCreditResponse]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    body: CreditRequest,

) -> DebitCreditResponse | None:
    """ Credit

     Credit the wallet with LEGACY BASE money (non-expiring, no grant lot).

    Deliberately untouched by F4.3: base is derived (balance minus active
    grant remainders), so an ADJUSTMENT credit simply grows base. Tenants who
    want expiring or promo credit use POST /customers/{id}/grants instead.

    Args:
        body (CreditRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DebitCreditResponse
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
