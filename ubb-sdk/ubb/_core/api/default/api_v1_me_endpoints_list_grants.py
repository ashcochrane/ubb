from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.grant_list_response import GrantListResponse
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params["limit"] = limit


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/me/grants",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> GrantListResponse | None:
    if response.status_code == 200:
        response_200 = GrantListResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[GrantListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[GrantListResponse]:
    """ List Grants

     Active credit grant lots on the customer's own wallet (kind,
    remaining, expiry), newest first in the one cursor envelope (#78 — the
    envelope-less capped list died with the contract big-bang; ordering moved
    from soonest-expiring to the standard creation keyset so the cursor is
    real).

    Seat-scoping decision: own-wallet basis, matching the /me/balance
    precedent — a pooled seat (whose money lives on the business owner's
    wallet) sees an empty list here rather than the shared business lots,
    exactly as /me/balance shows the seat's own (empty) wallet.

    Args:
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GrantListResponse]
     """


    kwargs = _get_kwargs(
        cursor=cursor,
limit=limit,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> GrantListResponse | None:
    """ List Grants

     Active credit grant lots on the customer's own wallet (kind,
    remaining, expiry), newest first in the one cursor envelope (#78 — the
    envelope-less capped list died with the contract big-bang; ordering moved
    from soonest-expiring to the standard creation keyset so the cursor is
    real).

    Seat-scoping decision: own-wallet basis, matching the /me/balance
    precedent — a pooled seat (whose money lives on the business owner's
    wallet) sees an empty list here rather than the shared business lots,
    exactly as /me/balance shows the seat's own (empty) wallet.

    Args:
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GrantListResponse
     """


    return sync_detailed(
        client=client,
cursor=cursor,
limit=limit,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[GrantListResponse]:
    """ List Grants

     Active credit grant lots on the customer's own wallet (kind,
    remaining, expiry), newest first in the one cursor envelope (#78 — the
    envelope-less capped list died with the contract big-bang; ordering moved
    from soonest-expiring to the standard creation keyset so the cursor is
    real).

    Seat-scoping decision: own-wallet basis, matching the /me/balance
    precedent — a pooled seat (whose money lives on the business owner's
    wallet) sees an empty list here rather than the shared business lots,
    exactly as /me/balance shows the seat's own (empty) wallet.

    Args:
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GrantListResponse]
     """


    kwargs = _get_kwargs(
        cursor=cursor,
limit=limit,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> GrantListResponse | None:
    """ List Grants

     Active credit grant lots on the customer's own wallet (kind,
    remaining, expiry), newest first in the one cursor envelope (#78 — the
    envelope-less capped list died with the contract big-bang; ordering moved
    from soonest-expiring to the standard creation keyset so the cursor is
    real).

    Seat-scoping decision: own-wallet basis, matching the /me/balance
    precedent — a pooled seat (whose money lives on the business owner's
    wallet) sees an empty list here rather than the shared business lots,
    exactly as /me/balance shows the seat's own (empty) wallet.

    Args:
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GrantListResponse
     """


    return (await asyncio_detailed(
        client=client,
cursor=cursor,
limit=limit,

    )).parsed
