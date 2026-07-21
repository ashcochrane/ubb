from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.usage_analytics_response import UsageAnalyticsResponse
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    dimensions: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_start_date: None | str | Unset
    if isinstance(start_date, Unset):
        json_start_date = UNSET
    elif isinstance(start_date, datetime.date):
        json_start_date = start_date.isoformat()
    else:
        json_start_date = start_date
    params["start_date"] = json_start_date

    json_end_date: None | str | Unset
    if isinstance(end_date, Unset):
        json_end_date = UNSET
    elif isinstance(end_date, datetime.date):
        json_end_date = end_date.isoformat()
    else:
        json_end_date = end_date
    params["end_date"] = json_end_date

    json_customer_id: None | str | Unset
    if isinstance(customer_id, Unset):
        json_customer_id = UNSET
    else:
        json_customer_id = customer_id
    params["customer_id"] = json_customer_id

    json_tag_key: None | str | Unset
    if isinstance(tag_key, Unset):
        json_tag_key = UNSET
    else:
        json_tag_key = tag_key
    params["tag_key"] = json_tag_key

    json_dimensions: list[str] | Unset = UNSET
    if not isinstance(dimensions, Unset):
        json_dimensions = dimensions


    params["dimensions"] = json_dimensions

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
        "url": "/api/v1/metering/analytics/usage",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | UsageAnalyticsResponse | None:
    if response.status_code == 200:
        response_200 = UsageAnalyticsResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | UsageAnalyticsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    dimensions: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> Response[ProblemOut | UsageAnalyticsResponse]:
    """ Usage Analytics

     Usage analytics with markup margin and customer/product/tag breakdowns.

    The #41 past-limit filters (past_limit / stop_scope / episode_seq)
    compose with every breakdown — e.g. past_limit=true totals exactly what
    was spent past a stop, in both denominations.

    Args:
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        customer_id (None | str | Unset):
        tag_key (None | str | Unset):
        dimensions (list[str] | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | UsageAnalyticsResponse]
     """


    kwargs = _get_kwargs(
        start_date=start_date,
end_date=end_date,
customer_id=customer_id,
tag_key=tag_key,
dimensions=dimensions,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    dimensions: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> ProblemOut | UsageAnalyticsResponse | None:
    """ Usage Analytics

     Usage analytics with markup margin and customer/product/tag breakdowns.

    The #41 past-limit filters (past_limit / stop_scope / episode_seq)
    compose with every breakdown — e.g. past_limit=true totals exactly what
    was spent past a stop, in both denominations.

    Args:
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        customer_id (None | str | Unset):
        tag_key (None | str | Unset):
        dimensions (list[str] | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | UsageAnalyticsResponse
     """


    return sync_detailed(
        client=client,
start_date=start_date,
end_date=end_date,
customer_id=customer_id,
tag_key=tag_key,
dimensions=dimensions,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    dimensions: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> Response[ProblemOut | UsageAnalyticsResponse]:
    """ Usage Analytics

     Usage analytics with markup margin and customer/product/tag breakdowns.

    The #41 past-limit filters (past_limit / stop_scope / episode_seq)
    compose with every breakdown — e.g. past_limit=true totals exactly what
    was spent past a stop, in both denominations.

    Args:
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        customer_id (None | str | Unset):
        tag_key (None | str | Unset):
        dimensions (list[str] | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | UsageAnalyticsResponse]
     """


    kwargs = _get_kwargs(
        start_date=start_date,
end_date=end_date,
customer_id=customer_id,
tag_key=tag_key,
dimensions=dimensions,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    dimensions: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> ProblemOut | UsageAnalyticsResponse | None:
    """ Usage Analytics

     Usage analytics with markup margin and customer/product/tag breakdowns.

    The #41 past-limit filters (past_limit / stop_scope / episode_seq)
    compose with every breakdown — e.g. past_limit=true totals exactly what
    was spent past a stop, in both denominations.

    Args:
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        customer_id (None | str | Unset):
        tag_key (None | str | Unset):
        dimensions (list[str] | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | UsageAnalyticsResponse
     """


    return (await asyncio_detailed(
        client=client,
start_date=start_date,
end_date=end_date,
customer_id=customer_id,
tag_key=tag_key,
dimensions=dimensions,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    )).parsed
