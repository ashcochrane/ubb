from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.invitation_list_response import InvitationListResponse
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
        "url": "/api/v1/tenant/invitations",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> InvitationListResponse | None:
    if response.status_code == 200:
        response_200 = InvitationListResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[InvitationListResponse]:
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

) -> Response[InvitationListResponse]:
    r""" List Invitations

     This tenant's invitations (pending, accepted, and revoked), newest first.

    Admin floor — the one deliberate exception to \"every GET floors at Read\"
    (#62's literal \"invitations create/list/revoke, Admin-gated\"; the members
    list beside it stays Read). Flagged for review on #80; kept as specified.

    Args:
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[InvitationListResponse]
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

) -> InvitationListResponse | None:
    r""" List Invitations

     This tenant's invitations (pending, accepted, and revoked), newest first.

    Admin floor — the one deliberate exception to \"every GET floors at Read\"
    (#62's literal \"invitations create/list/revoke, Admin-gated\"; the members
    list beside it stays Read). Flagged for review on #80; kept as specified.

    Args:
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        InvitationListResponse
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

) -> Response[InvitationListResponse]:
    r""" List Invitations

     This tenant's invitations (pending, accepted, and revoked), newest first.

    Admin floor — the one deliberate exception to \"every GET floors at Read\"
    (#62's literal \"invitations create/list/revoke, Admin-gated\"; the members
    list beside it stays Read). Flagged for review on #80; kept as specified.

    Args:
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[InvitationListResponse]
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

) -> InvitationListResponse | None:
    r""" List Invitations

     This tenant's invitations (pending, accepted, and revoked), newest first.

    Admin floor — the one deliberate exception to \"every GET floors at Read\"
    (#62's literal \"invitations create/list/revoke, Admin-gated\"; the members
    list beside it stays Read). Flagged for review on #80; kept as specified.

    Args:
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        InvitationListResponse
     """


    return (await asyncio_detailed(
        client=client,
cursor=cursor,
limit=limit,

    )).parsed
