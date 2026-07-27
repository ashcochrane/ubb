from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.task_analytics_out import TaskAnalyticsOut
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    group_by: str | Unset = 'task_type',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["group_by"] = group_by

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


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/analytics/tasks",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | TaskAnalyticsOut | None:
    if response.status_code == 200:
        response_200 = TaskAnalyticsOut.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | TaskAnalyticsOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    group_by: str | Unset = 'task_type',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> Response[ProblemOut | TaskAnalyticsOut]:
    """ Task Analytics

     Cost per KIND of job: run count, mean, p95, and limit hits.

    A p95 approaching the type's ceiling is the signal that the limit is about
    to start biting real customers.

    Args:
        group_by (str | Unset):  Default: 'task_type'.
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | TaskAnalyticsOut]
     """


    kwargs = _get_kwargs(
        group_by=group_by,
start_date=start_date,
end_date=end_date,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    group_by: str | Unset = 'task_type',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> ProblemOut | TaskAnalyticsOut | None:
    """ Task Analytics

     Cost per KIND of job: run count, mean, p95, and limit hits.

    A p95 approaching the type's ceiling is the signal that the limit is about
    to start biting real customers.

    Args:
        group_by (str | Unset):  Default: 'task_type'.
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | TaskAnalyticsOut
     """


    return sync_detailed(
        client=client,
group_by=group_by,
start_date=start_date,
end_date=end_date,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    group_by: str | Unset = 'task_type',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> Response[ProblemOut | TaskAnalyticsOut]:
    """ Task Analytics

     Cost per KIND of job: run count, mean, p95, and limit hits.

    A p95 approaching the type's ceiling is the signal that the limit is about
    to start biting real customers.

    Args:
        group_by (str | Unset):  Default: 'task_type'.
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | TaskAnalyticsOut]
     """


    kwargs = _get_kwargs(
        group_by=group_by,
start_date=start_date,
end_date=end_date,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    group_by: str | Unset = 'task_type',
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> ProblemOut | TaskAnalyticsOut | None:
    """ Task Analytics

     Cost per KIND of job: run count, mean, p95, and limit hits.

    A p95 approaching the type's ceiling is the signal that the limit is about
    to start biting real customers.

    Args:
        group_by (str | Unset):  Default: 'task_type'.
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | TaskAnalyticsOut
     """


    return (await asyncio_detailed(
        client=client,
group_by=group_by,
start_date=start_date,
end_date=end_date,

    )).parsed
