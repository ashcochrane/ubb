from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.status_response import StatusResponse
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/metering/pricing/default-markup",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> StatusResponse | None:
    if response.status_code == 200:
        response_200 = StatusResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[StatusResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[StatusResponse]:
    """ Withdraw Tenant Default Markup

     Withdraw the rung, leaving the tenant with none.

    ⚠ **THIS IS NOT THE SAME AS DECLARING ZERO**, and the difference is the one
    this rung exists to keep. A declared zero prices an event at exactly what
    the call cost and settles; no rung at all resolves to `unknown` with no
    amount, because nobody has said what to charge.

    Idempotent: withdrawing nothing answers `no_declaration` rather than 404,
    and writes no audit entry — there was no act.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[StatusResponse]
     """


    kwargs = _get_kwargs(
        
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,

) -> StatusResponse | None:
    """ Withdraw Tenant Default Markup

     Withdraw the rung, leaving the tenant with none.

    ⚠ **THIS IS NOT THE SAME AS DECLARING ZERO**, and the difference is the one
    this rung exists to keep. A declared zero prices an event at exactly what
    the call cost and settles; no rung at all resolves to `unknown` with no
    amount, because nobody has said what to charge.

    Idempotent: withdrawing nothing answers `no_declaration` rather than 404,
    and writes no audit entry — there was no act.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        StatusResponse
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[StatusResponse]:
    """ Withdraw Tenant Default Markup

     Withdraw the rung, leaving the tenant with none.

    ⚠ **THIS IS NOT THE SAME AS DECLARING ZERO**, and the difference is the one
    this rung exists to keep. A declared zero prices an event at exactly what
    the call cost and settles; no rung at all resolves to `unknown` with no
    amount, because nobody has said what to charge.

    Idempotent: withdrawing nothing answers `no_declaration` rather than 404,
    and writes no audit entry — there was no act.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[StatusResponse]
     """


    kwargs = _get_kwargs(
        
    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,

) -> StatusResponse | None:
    """ Withdraw Tenant Default Markup

     Withdraw the rung, leaving the tenant with none.

    ⚠ **THIS IS NOT THE SAME AS DECLARING ZERO**, and the difference is the one
    this rung exists to keep. A declared zero prices an event at exactly what
    the call cost and settles; no rung at all resolves to `unknown` with no
    amount, because nobody has said what to charge.

    Idempotent: withdrawing nothing answers `no_declaration` rather than 404,
    and writes no audit entry — there was no act.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        StatusResponse
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
