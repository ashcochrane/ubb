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

     Cost per KIND of work: run count, mean and p95, over the work created in
    the window.

    A p95 approaching the kind's ceiling is the signal that the ceiling is
    about to start biting real customers; how much work reached it is
    `GET /spend-controls/utilisation-and-headroom`'s figure.

    **The window.** `start_date` and `end_date` are calendar dates in UTC, and both are inclusive: the
    window runs from the start of `start_date` to the end of `end_date`. Send `start_date` alone and the
    window runs to today; send `end_date` alone and it starts on the first day of that date's month;
    send neither and it is the current UTC month to date. A supplied date is never ignored. One request
    spans at most 366 calendar dates, and `start_date` may not fall after `end_date`; either is refused
    with `validation_error`. Longer retained history is read through consecutive, non-overlapping
    windows: the next window starts on the calendar day after the previous window's `end_date`.

    Args:
        group_by (str | Unset):  Default: 'task_type'.
        start_date (datetime.date | None | Unset): The first calendar date (UTC) in the window,
            inclusive.
        end_date (datetime.date | None | Unset): The last calendar date (UTC) in the window,
            inclusive.

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

     Cost per KIND of work: run count, mean and p95, over the work created in
    the window.

    A p95 approaching the kind's ceiling is the signal that the ceiling is
    about to start biting real customers; how much work reached it is
    `GET /spend-controls/utilisation-and-headroom`'s figure.

    **The window.** `start_date` and `end_date` are calendar dates in UTC, and both are inclusive: the
    window runs from the start of `start_date` to the end of `end_date`. Send `start_date` alone and the
    window runs to today; send `end_date` alone and it starts on the first day of that date's month;
    send neither and it is the current UTC month to date. A supplied date is never ignored. One request
    spans at most 366 calendar dates, and `start_date` may not fall after `end_date`; either is refused
    with `validation_error`. Longer retained history is read through consecutive, non-overlapping
    windows: the next window starts on the calendar day after the previous window's `end_date`.

    Args:
        group_by (str | Unset):  Default: 'task_type'.
        start_date (datetime.date | None | Unset): The first calendar date (UTC) in the window,
            inclusive.
        end_date (datetime.date | None | Unset): The last calendar date (UTC) in the window,
            inclusive.

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

     Cost per KIND of work: run count, mean and p95, over the work created in
    the window.

    A p95 approaching the kind's ceiling is the signal that the ceiling is
    about to start biting real customers; how much work reached it is
    `GET /spend-controls/utilisation-and-headroom`'s figure.

    **The window.** `start_date` and `end_date` are calendar dates in UTC, and both are inclusive: the
    window runs from the start of `start_date` to the end of `end_date`. Send `start_date` alone and the
    window runs to today; send `end_date` alone and it starts on the first day of that date's month;
    send neither and it is the current UTC month to date. A supplied date is never ignored. One request
    spans at most 366 calendar dates, and `start_date` may not fall after `end_date`; either is refused
    with `validation_error`. Longer retained history is read through consecutive, non-overlapping
    windows: the next window starts on the calendar day after the previous window's `end_date`.

    Args:
        group_by (str | Unset):  Default: 'task_type'.
        start_date (datetime.date | None | Unset): The first calendar date (UTC) in the window,
            inclusive.
        end_date (datetime.date | None | Unset): The last calendar date (UTC) in the window,
            inclusive.

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

     Cost per KIND of work: run count, mean and p95, over the work created in
    the window.

    A p95 approaching the kind's ceiling is the signal that the ceiling is
    about to start biting real customers; how much work reached it is
    `GET /spend-controls/utilisation-and-headroom`'s figure.

    **The window.** `start_date` and `end_date` are calendar dates in UTC, and both are inclusive: the
    window runs from the start of `start_date` to the end of `end_date`. Send `start_date` alone and the
    window runs to today; send `end_date` alone and it starts on the first day of that date's month;
    send neither and it is the current UTC month to date. A supplied date is never ignored. One request
    spans at most 366 calendar dates, and `start_date` may not fall after `end_date`; either is refused
    with `validation_error`. Longer retained history is read through consecutive, non-overlapping
    windows: the next window starts on the calendar day after the previous window's `end_date`.

    Args:
        group_by (str | Unset):  Default: 'task_type'.
        start_date (datetime.date | None | Unset): The first calendar date (UTC) in the window,
            inclusive.
        end_date (datetime.date | None | Unset): The last calendar date (UTC) in the window,
            inclusive.

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
