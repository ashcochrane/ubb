from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.paginated_usage_response import PaginatedUsageResponse
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    customer_id: str,
    *,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    tag_key: None | str | Unset = UNSET,
    tag_value: None | str | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params["limit"] = limit

    json_tag_key: None | str | Unset
    if isinstance(tag_key, Unset):
        json_tag_key = UNSET
    else:
        json_tag_key = tag_key
    params["tag_key"] = json_tag_key

    json_tag_value: None | str | Unset
    if isinstance(tag_value, Unset):
        json_tag_value = UNSET
    else:
        json_tag_value = tag_value
    params["tag_value"] = json_tag_value

    json_past_limit: bool | None | Unset
    if isinstance(past_limit, Unset):
        json_past_limit = UNSET
    else:
        json_past_limit = past_limit
    params["past_limit"] = json_past_limit

    json_stop_scope: None | str | Unset
    if isinstance(stop_scope, Unset):
        json_stop_scope = UNSET
    else:
        json_stop_scope = stop_scope
    params["stop_scope"] = json_stop_scope

    json_episode_seq: int | None | Unset
    if isinstance(episode_seq, Unset):
        json_episode_seq = UNSET
    else:
        json_episode_seq = episode_seq
    params["episode_seq"] = json_episode_seq


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/customers/{customer_id}/usage".format(customer_id=quote(str(customer_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> PaginatedUsageResponse | None:
    if response.status_code == 200:
        response_200 = PaginatedUsageResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[PaginatedUsageResponse]:
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
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    tag_key: None | str | Unset = UNSET,
    tag_value: None | str | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> Response[PaginatedUsageResponse]:
    """ Get Usage

    Args:
        customer_id (str):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.
        tag_key (None | str | Unset):
        tag_value (None | str | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PaginatedUsageResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
cursor=cursor,
limit=limit,
tag_key=tag_key,
tag_value=tag_value,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    tag_key: None | str | Unset = UNSET,
    tag_value: None | str | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> PaginatedUsageResponse | None:
    """ Get Usage

    Args:
        customer_id (str):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.
        tag_key (None | str | Unset):
        tag_value (None | str | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PaginatedUsageResponse
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
cursor=cursor,
limit=limit,
tag_key=tag_key,
tag_value=tag_value,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    ).parsed

async def asyncio_detailed(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    tag_key: None | str | Unset = UNSET,
    tag_value: None | str | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> Response[PaginatedUsageResponse]:
    """ Get Usage

    Args:
        customer_id (str):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.
        tag_key (None | str | Unset):
        tag_value (None | str | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PaginatedUsageResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
cursor=cursor,
limit=limit,
tag_key=tag_key,
tag_value=tag_value,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    tag_key: None | str | Unset = UNSET,
    tag_value: None | str | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> PaginatedUsageResponse | None:
    """ Get Usage

    Args:
        customer_id (str):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.
        tag_key (None | str | Unset):
        tag_value (None | str | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PaginatedUsageResponse
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
cursor=cursor,
limit=limit,
tag_key=tag_key,
tag_value=tag_value,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    )).parsed
