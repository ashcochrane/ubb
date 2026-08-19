from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.tenant_default_markup_in import TenantDefaultMarkupIn
from ...models.tenant_default_markup_out import TenantDefaultMarkupOut
from typing import cast



def _get_kwargs(
    *,
    body: TenantDefaultMarkupIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/metering/pricing/default-markup",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> TenantDefaultMarkupOut | None:
    if response.status_code == 200:
        response_200 = TenantDefaultMarkupOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[TenantDefaultMarkupOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: TenantDefaultMarkupIn,

) -> Response[TenantDefaultMarkupOut]:
    """ Declare Tenant Default Markup

     Declare the tenant's default markup rung, or re-declare it.

    Re-declaring is the same act as declaring — a correction to a declared
    percentage is still a declaration — which is why one action name covers
    both and why withdrawal is a different one.

    The ADMIN floor is the write default this surface already runs for
    everything that decides what a customer is charged.

    Args:
        body (TenantDefaultMarkupIn): The tenant's default markup rung, as the tenant declares it
            (#357).

            ⚠ **REQUIRED, WITH NO DEFAULT, WHICH IS THE WHOLE POINT.** UBB ships no
            catalogue: there is no starter percentage anywhere, and a tenant that has
            declared nothing has no markup rung at all. A default of zero here would let
            a caller declare a rung by accident, and a rung of zero is a decision — it
            says *charge my customer exactly what the call cost* — so it has to be
            stated.

            **ONE TERM, BECAUSE A MARGIN NEVER COMPOSES** (#147 §2). No floor, no cap
            and no flat addend beside the percentage: a resolved price is explicable by
            naming one thing, and a chain whose middle terms are on no record is what
            that rule exists to prevent.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TenantDefaultMarkupOut]
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
    body: TenantDefaultMarkupIn,

) -> TenantDefaultMarkupOut | None:
    """ Declare Tenant Default Markup

     Declare the tenant's default markup rung, or re-declare it.

    Re-declaring is the same act as declaring — a correction to a declared
    percentage is still a declaration — which is why one action name covers
    both and why withdrawal is a different one.

    The ADMIN floor is the write default this surface already runs for
    everything that decides what a customer is charged.

    Args:
        body (TenantDefaultMarkupIn): The tenant's default markup rung, as the tenant declares it
            (#357).

            ⚠ **REQUIRED, WITH NO DEFAULT, WHICH IS THE WHOLE POINT.** UBB ships no
            catalogue: there is no starter percentage anywhere, and a tenant that has
            declared nothing has no markup rung at all. A default of zero here would let
            a caller declare a rung by accident, and a rung of zero is a decision — it
            says *charge my customer exactly what the call cost* — so it has to be
            stated.

            **ONE TERM, BECAUSE A MARGIN NEVER COMPOSES** (#147 §2). No floor, no cap
            and no flat addend beside the percentage: a resolved price is explicable by
            naming one thing, and a chain whose middle terms are on no record is what
            that rule exists to prevent.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TenantDefaultMarkupOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: TenantDefaultMarkupIn,

) -> Response[TenantDefaultMarkupOut]:
    """ Declare Tenant Default Markup

     Declare the tenant's default markup rung, or re-declare it.

    Re-declaring is the same act as declaring — a correction to a declared
    percentage is still a declaration — which is why one action name covers
    both and why withdrawal is a different one.

    The ADMIN floor is the write default this surface already runs for
    everything that decides what a customer is charged.

    Args:
        body (TenantDefaultMarkupIn): The tenant's default markup rung, as the tenant declares it
            (#357).

            ⚠ **REQUIRED, WITH NO DEFAULT, WHICH IS THE WHOLE POINT.** UBB ships no
            catalogue: there is no starter percentage anywhere, and a tenant that has
            declared nothing has no markup rung at all. A default of zero here would let
            a caller declare a rung by accident, and a rung of zero is a decision — it
            says *charge my customer exactly what the call cost* — so it has to be
            stated.

            **ONE TERM, BECAUSE A MARGIN NEVER COMPOSES** (#147 §2). No floor, no cap
            and no flat addend beside the percentage: a resolved price is explicable by
            naming one thing, and a chain whose middle terms are on no record is what
            that rule exists to prevent.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TenantDefaultMarkupOut]
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
    body: TenantDefaultMarkupIn,

) -> TenantDefaultMarkupOut | None:
    """ Declare Tenant Default Markup

     Declare the tenant's default markup rung, or re-declare it.

    Re-declaring is the same act as declaring — a correction to a declared
    percentage is still a declaration — which is why one action name covers
    both and why withdrawal is a different one.

    The ADMIN floor is the write default this surface already runs for
    everything that decides what a customer is charged.

    Args:
        body (TenantDefaultMarkupIn): The tenant's default markup rung, as the tenant declares it
            (#357).

            ⚠ **REQUIRED, WITH NO DEFAULT, WHICH IS THE WHOLE POINT.** UBB ships no
            catalogue: there is no starter percentage anywhere, and a tenant that has
            declared nothing has no markup rung at all. A default of zero here would let
            a caller declare a rung by accident, and a rung of zero is a decision — it
            says *charge my customer exactly what the call cost* — so it has to be
            stated.

            **ONE TERM, BECAUSE A MARGIN NEVER COMPOSES** (#147 §2). No floor, no cap
            and no flat addend beside the percentage: a resolved price is explicable by
            naming one thing, and a chain whose middle terms are on no record is what
            that rule exists to prevent.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TenantDefaultMarkupOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
