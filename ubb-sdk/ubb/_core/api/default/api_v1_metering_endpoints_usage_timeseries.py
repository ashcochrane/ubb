from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.usage_timeseries_response import UsageTimeseriesResponse
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    granularity: str | Unset = 'day',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    group_by: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["granularity"] = granularity

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

    json_group_by: None | str | Unset
    if isinstance(group_by, Unset):
        json_group_by = UNSET
    else:
        json_group_by = group_by
    params["group_by"] = json_group_by


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/analytics/usage/timeseries",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | UsageTimeseriesResponse | None:
    if response.status_code == 200:
        response_200 = UsageTimeseriesResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | UsageTimeseriesResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    granularity: str | Unset = 'day',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    group_by: None | str | Unset = UNSET,

) -> Response[ProblemOut | UsageTimeseriesResponse]:
    """ Usage Timeseries

     Time-series spend rollup: daily or hourly COGS per tenant/customer.

    start_date and end_date are both INCLUSIVE calendar dates, matching the
    /analytics/usage rollup so the same inputs cover the same window on both.

    Args:
        granularity (str | Unset):  Default: 'day'.
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        customer_id (None | str | Unset):
        group_by (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | UsageTimeseriesResponse]
     """


    kwargs = _get_kwargs(
        granularity=granularity,
start_date=start_date,
end_date=end_date,
customer_id=customer_id,
group_by=group_by,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    granularity: str | Unset = 'day',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    group_by: None | str | Unset = UNSET,

) -> ProblemOut | UsageTimeseriesResponse | None:
    """ Usage Timeseries

     Time-series spend rollup: daily or hourly COGS per tenant/customer.

    start_date and end_date are both INCLUSIVE calendar dates, matching the
    /analytics/usage rollup so the same inputs cover the same window on both.

    Args:
        granularity (str | Unset):  Default: 'day'.
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        customer_id (None | str | Unset):
        group_by (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | UsageTimeseriesResponse
     """


    return sync_detailed(
        client=client,
granularity=granularity,
start_date=start_date,
end_date=end_date,
customer_id=customer_id,
group_by=group_by,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    granularity: str | Unset = 'day',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    group_by: None | str | Unset = UNSET,

) -> Response[ProblemOut | UsageTimeseriesResponse]:
    """ Usage Timeseries

     Time-series spend rollup: daily or hourly COGS per tenant/customer.

    start_date and end_date are both INCLUSIVE calendar dates, matching the
    /analytics/usage rollup so the same inputs cover the same window on both.

    Args:
        granularity (str | Unset):  Default: 'day'.
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        customer_id (None | str | Unset):
        group_by (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | UsageTimeseriesResponse]
     """


    kwargs = _get_kwargs(
        granularity=granularity,
start_date=start_date,
end_date=end_date,
customer_id=customer_id,
group_by=group_by,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    granularity: str | Unset = 'day',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    group_by: None | str | Unset = UNSET,

) -> ProblemOut | UsageTimeseriesResponse | None:
    """ Usage Timeseries

     Time-series spend rollup: daily or hourly COGS per tenant/customer.

    start_date and end_date are both INCLUSIVE calendar dates, matching the
    /analytics/usage rollup so the same inputs cover the same window on both.

    Args:
        granularity (str | Unset):  Default: 'day'.
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        customer_id (None | str | Unset):
        group_by (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | UsageTimeseriesResponse
     """


    return (await asyncio_detailed(
        client=client,
granularity=granularity,
start_date=start_date,
end_date=end_date,
customer_id=customer_id,
group_by=group_by,

    )).parsed
