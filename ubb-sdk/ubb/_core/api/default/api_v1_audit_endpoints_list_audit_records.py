from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.audit_record_list_response import AuditRecordListResponse
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    action: None | str | Unset = UNSET,
    resource_type: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_action: None | str | Unset
    if isinstance(action, Unset):
        json_action = UNSET
    else:
        json_action = action
    params["action"] = json_action

    json_resource_type: None | str | Unset
    if isinstance(resource_type, Unset):
        json_resource_type = UNSET
    else:
        json_resource_type = resource_type
    params["resource_type"] = json_resource_type

    json_resource_id: None | str | Unset
    if isinstance(resource_id, Unset):
        json_resource_id = UNSET
    else:
        json_resource_id = resource_id
    params["resource_id"] = json_resource_id

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
        "url": "/api/v1/audit/records",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> AuditRecordListResponse | None:
    if response.status_code == 200:
        response_200 = AuditRecordListResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[AuditRecordListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    action: None | str | Unset = UNSET,
    resource_type: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[AuditRecordListResponse]:
    r""" List Audit Records

     This account's audit entries, newest first (cursor-paginated, #78 envelope).

    Optional exact-match filters narrow the feed: ``action`` (e.g.
    ``rate_card.published``), or ``resource_type`` + ``resource_id`` together to
    answer \"who changed THIS rate card?\" — both served by the ledger's indexes.
    Not product-gated: the trail spans every product a tenant uses.

    Args:
        action (None | str | Unset):
        resource_type (None | str | Unset):
        resource_id (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuditRecordListResponse]
     """


    kwargs = _get_kwargs(
        action=action,
resource_type=resource_type,
resource_id=resource_id,
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
    action: None | str | Unset = UNSET,
    resource_type: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> AuditRecordListResponse | None:
    r""" List Audit Records

     This account's audit entries, newest first (cursor-paginated, #78 envelope).

    Optional exact-match filters narrow the feed: ``action`` (e.g.
    ``rate_card.published``), or ``resource_type`` + ``resource_id`` together to
    answer \"who changed THIS rate card?\" — both served by the ledger's indexes.
    Not product-gated: the trail spans every product a tenant uses.

    Args:
        action (None | str | Unset):
        resource_type (None | str | Unset):
        resource_id (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuditRecordListResponse
     """


    return sync_detailed(
        client=client,
action=action,
resource_type=resource_type,
resource_id=resource_id,
cursor=cursor,
limit=limit,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    action: None | str | Unset = UNSET,
    resource_type: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[AuditRecordListResponse]:
    r""" List Audit Records

     This account's audit entries, newest first (cursor-paginated, #78 envelope).

    Optional exact-match filters narrow the feed: ``action`` (e.g.
    ``rate_card.published``), or ``resource_type`` + ``resource_id`` together to
    answer \"who changed THIS rate card?\" — both served by the ledger's indexes.
    Not product-gated: the trail spans every product a tenant uses.

    Args:
        action (None | str | Unset):
        resource_type (None | str | Unset):
        resource_id (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuditRecordListResponse]
     """


    kwargs = _get_kwargs(
        action=action,
resource_type=resource_type,
resource_id=resource_id,
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
    action: None | str | Unset = UNSET,
    resource_type: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> AuditRecordListResponse | None:
    r""" List Audit Records

     This account's audit entries, newest first (cursor-paginated, #78 envelope).

    Optional exact-match filters narrow the feed: ``action`` (e.g.
    ``rate_card.published``), or ``resource_type`` + ``resource_id`` together to
    answer \"who changed THIS rate card?\" — both served by the ledger's indexes.
    Not product-gated: the trail spans every product a tenant uses.

    Args:
        action (None | str | Unset):
        resource_type (None | str | Unset):
        resource_id (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuditRecordListResponse
     """


    return (await asyncio_detailed(
        client=client,
action=action,
resource_type=resource_type,
resource_id=resource_id,
cursor=cursor,
limit=limit,

    )).parsed
