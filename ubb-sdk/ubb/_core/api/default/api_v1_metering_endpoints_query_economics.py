from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.economics_out import EconomicsOut
from ...models.problem_out import ProblemOut
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    measures: list[str] | Unset = UNSET,
    group_by: list[str] | Unset = UNSET,
    bucket: None | str | Unset = UNSET,
    basis: None | str | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    task_id: None | str | Unset = UNSET,
    include_subtasks: bool | Unset = False,
    where: list[str] | Unset = UNSET,
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

    json_measures: list[str] | Unset = UNSET
    if not isinstance(measures, Unset):
        json_measures = measures


    params["measures"] = json_measures

    json_group_by: list[str] | Unset = UNSET
    if not isinstance(group_by, Unset):
        json_group_by = group_by


    params["group_by"] = json_group_by

    json_bucket: None | str | Unset
    if isinstance(bucket, Unset):
        json_bucket = UNSET
    else:
        json_bucket = bucket
    params["bucket"] = json_bucket

    json_basis: None | str | Unset
    if isinstance(basis, Unset):
        json_basis = UNSET
    else:
        json_basis = basis
    params["basis"] = json_basis

    json_customer_id: None | str | Unset
    if isinstance(customer_id, Unset):
        json_customer_id = UNSET
    else:
        json_customer_id = customer_id
    params["customer_id"] = json_customer_id

    json_event_type: None | str | Unset
    if isinstance(event_type, Unset):
        json_event_type = UNSET
    else:
        json_event_type = event_type
    params["event_type"] = json_event_type

    json_task_type: None | str | Unset
    if isinstance(task_type, Unset):
        json_task_type = UNSET
    else:
        json_task_type = task_type
    params["task_type"] = json_task_type

    json_task_id: None | str | Unset
    if isinstance(task_id, Unset):
        json_task_id = UNSET
    else:
        json_task_id = task_id
    params["task_id"] = json_task_id

    params["include_subtasks"] = include_subtasks

    json_where: list[str] | Unset = UNSET
    if not isinstance(where, Unset):
        json_where = where


    params["where"] = json_where

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
        "url": "/api/v1/metering/analytics/economics",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> EconomicsOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = EconomicsOut.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[EconomicsOut | ProblemOut]:
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
    measures: list[str] | Unset = UNSET,
    group_by: list[str] | Unset = UNSET,
    bucket: None | str | Unset = UNSET,
    basis: None | str | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    task_id: None | str | Unset = UNSET,
    include_subtasks: bool | Unset = False,
    where: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> Response[EconomicsOut | ProblemOut]:
    """ Query Economics

     What your AI work cost, what it earned, and the difference — one answer
    from one definition.

    Ask for one or more `measures`, group by zero or more axes from
    `/metering/analytics/grouping-options`, and bucket by `hour`, `day` or
    `month`. Every filter composes with every grouping.

    **Requesting no measure is refused rather than defaulted**: a default
    measure set is how a caller ends up aggregating three different things to
    draw one line.

    **A row's grouped values are positional**, in the order the axes were sent,
    and the response echoes `group_by` so the alignment is readable from the
    answer alone. Where a row has no value on an axis, the entry beside it says
    whether the value was never recorded or whether the question does not apply
    to that kind of row.

    **Each measure carries its own state and the state is part of the answer.**
    A margin UBB cannot attribute at the grain you asked for is absent rather
    than small, and the revenue that could not be placed is listed under
    `context` with the axes at which asking again would produce one.

    `basis` picks how revenue a tenant supplied is spread over the span it
    declares: `recorded` places each amount whole on the day its record opens
    and is the default, `recognised` spreads it by the record's own method. The
    answer always states which it served.

    Explicit date windows are bounded: 366 days, and 92 for an hourly question,
    because the ceiling is about how many buckets one answer may carry. The
    response echoes the period it applied, so a caller who left the window to
    the default can see what it was.

    Codes: `validation_error` for a request that will not parse or a window past
    the bound; `unanswerable_combination` for a well-formed question this
    surface declines to answer subtly wrongly, whose message says what to ask
    instead.

    Args:
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        measures (list[str] | Unset):
        group_by (list[str] | Unset):
        bucket (None | str | Unset):
        basis (None | str | Unset):
        customer_id (None | str | Unset):
        event_type (None | str | Unset):
        task_type (None | str | Unset):
        task_id (None | str | Unset):
        include_subtasks (bool | Unset):  Default: False.
        where (list[str] | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EconomicsOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        start_date=start_date,
end_date=end_date,
measures=measures,
group_by=group_by,
bucket=bucket,
basis=basis,
customer_id=customer_id,
event_type=event_type,
task_type=task_type,
task_id=task_id,
include_subtasks=include_subtasks,
where=where,
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
    measures: list[str] | Unset = UNSET,
    group_by: list[str] | Unset = UNSET,
    bucket: None | str | Unset = UNSET,
    basis: None | str | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    task_id: None | str | Unset = UNSET,
    include_subtasks: bool | Unset = False,
    where: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> EconomicsOut | ProblemOut | None:
    """ Query Economics

     What your AI work cost, what it earned, and the difference — one answer
    from one definition.

    Ask for one or more `measures`, group by zero or more axes from
    `/metering/analytics/grouping-options`, and bucket by `hour`, `day` or
    `month`. Every filter composes with every grouping.

    **Requesting no measure is refused rather than defaulted**: a default
    measure set is how a caller ends up aggregating three different things to
    draw one line.

    **A row's grouped values are positional**, in the order the axes were sent,
    and the response echoes `group_by` so the alignment is readable from the
    answer alone. Where a row has no value on an axis, the entry beside it says
    whether the value was never recorded or whether the question does not apply
    to that kind of row.

    **Each measure carries its own state and the state is part of the answer.**
    A margin UBB cannot attribute at the grain you asked for is absent rather
    than small, and the revenue that could not be placed is listed under
    `context` with the axes at which asking again would produce one.

    `basis` picks how revenue a tenant supplied is spread over the span it
    declares: `recorded` places each amount whole on the day its record opens
    and is the default, `recognised` spreads it by the record's own method. The
    answer always states which it served.

    Explicit date windows are bounded: 366 days, and 92 for an hourly question,
    because the ceiling is about how many buckets one answer may carry. The
    response echoes the period it applied, so a caller who left the window to
    the default can see what it was.

    Codes: `validation_error` for a request that will not parse or a window past
    the bound; `unanswerable_combination` for a well-formed question this
    surface declines to answer subtly wrongly, whose message says what to ask
    instead.

    Args:
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        measures (list[str] | Unset):
        group_by (list[str] | Unset):
        bucket (None | str | Unset):
        basis (None | str | Unset):
        customer_id (None | str | Unset):
        event_type (None | str | Unset):
        task_type (None | str | Unset):
        task_id (None | str | Unset):
        include_subtasks (bool | Unset):  Default: False.
        where (list[str] | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EconomicsOut | ProblemOut
     """


    return sync_detailed(
        client=client,
start_date=start_date,
end_date=end_date,
measures=measures,
group_by=group_by,
bucket=bucket,
basis=basis,
customer_id=customer_id,
event_type=event_type,
task_type=task_type,
task_id=task_id,
include_subtasks=include_subtasks,
where=where,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    measures: list[str] | Unset = UNSET,
    group_by: list[str] | Unset = UNSET,
    bucket: None | str | Unset = UNSET,
    basis: None | str | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    task_id: None | str | Unset = UNSET,
    include_subtasks: bool | Unset = False,
    where: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> Response[EconomicsOut | ProblemOut]:
    """ Query Economics

     What your AI work cost, what it earned, and the difference — one answer
    from one definition.

    Ask for one or more `measures`, group by zero or more axes from
    `/metering/analytics/grouping-options`, and bucket by `hour`, `day` or
    `month`. Every filter composes with every grouping.

    **Requesting no measure is refused rather than defaulted**: a default
    measure set is how a caller ends up aggregating three different things to
    draw one line.

    **A row's grouped values are positional**, in the order the axes were sent,
    and the response echoes `group_by` so the alignment is readable from the
    answer alone. Where a row has no value on an axis, the entry beside it says
    whether the value was never recorded or whether the question does not apply
    to that kind of row.

    **Each measure carries its own state and the state is part of the answer.**
    A margin UBB cannot attribute at the grain you asked for is absent rather
    than small, and the revenue that could not be placed is listed under
    `context` with the axes at which asking again would produce one.

    `basis` picks how revenue a tenant supplied is spread over the span it
    declares: `recorded` places each amount whole on the day its record opens
    and is the default, `recognised` spreads it by the record's own method. The
    answer always states which it served.

    Explicit date windows are bounded: 366 days, and 92 for an hourly question,
    because the ceiling is about how many buckets one answer may carry. The
    response echoes the period it applied, so a caller who left the window to
    the default can see what it was.

    Codes: `validation_error` for a request that will not parse or a window past
    the bound; `unanswerable_combination` for a well-formed question this
    surface declines to answer subtly wrongly, whose message says what to ask
    instead.

    Args:
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        measures (list[str] | Unset):
        group_by (list[str] | Unset):
        bucket (None | str | Unset):
        basis (None | str | Unset):
        customer_id (None | str | Unset):
        event_type (None | str | Unset):
        task_type (None | str | Unset):
        task_id (None | str | Unset):
        include_subtasks (bool | Unset):  Default: False.
        where (list[str] | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EconomicsOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        start_date=start_date,
end_date=end_date,
measures=measures,
group_by=group_by,
bucket=bucket,
basis=basis,
customer_id=customer_id,
event_type=event_type,
task_type=task_type,
task_id=task_id,
include_subtasks=include_subtasks,
where=where,
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
    measures: list[str] | Unset = UNSET,
    group_by: list[str] | Unset = UNSET,
    bucket: None | str | Unset = UNSET,
    basis: None | str | Unset = UNSET,
    customer_id: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    task_id: None | str | Unset = UNSET,
    include_subtasks: bool | Unset = False,
    where: list[str] | Unset = UNSET,
    past_limit: bool | None | Unset = UNSET,
    stop_scope: None | str | Unset = UNSET,
    episode_seq: int | None | Unset = UNSET,

) -> EconomicsOut | ProblemOut | None:
    """ Query Economics

     What your AI work cost, what it earned, and the difference — one answer
    from one definition.

    Ask for one or more `measures`, group by zero or more axes from
    `/metering/analytics/grouping-options`, and bucket by `hour`, `day` or
    `month`. Every filter composes with every grouping.

    **Requesting no measure is refused rather than defaulted**: a default
    measure set is how a caller ends up aggregating three different things to
    draw one line.

    **A row's grouped values are positional**, in the order the axes were sent,
    and the response echoes `group_by` so the alignment is readable from the
    answer alone. Where a row has no value on an axis, the entry beside it says
    whether the value was never recorded or whether the question does not apply
    to that kind of row.

    **Each measure carries its own state and the state is part of the answer.**
    A margin UBB cannot attribute at the grain you asked for is absent rather
    than small, and the revenue that could not be placed is listed under
    `context` with the axes at which asking again would produce one.

    `basis` picks how revenue a tenant supplied is spread over the span it
    declares: `recorded` places each amount whole on the day its record opens
    and is the default, `recognised` spreads it by the record's own method. The
    answer always states which it served.

    Explicit date windows are bounded: 366 days, and 92 for an hourly question,
    because the ceiling is about how many buckets one answer may carry. The
    response echoes the period it applied, so a caller who left the window to
    the default can see what it was.

    Codes: `validation_error` for a request that will not parse or a window past
    the bound; `unanswerable_combination` for a well-formed question this
    surface declines to answer subtly wrongly, whose message says what to ask
    instead.

    Args:
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        measures (list[str] | Unset):
        group_by (list[str] | Unset):
        bucket (None | str | Unset):
        basis (None | str | Unset):
        customer_id (None | str | Unset):
        event_type (None | str | Unset):
        task_type (None | str | Unset):
        task_id (None | str | Unset):
        include_subtasks (bool | Unset):  Default: False.
        where (list[str] | Unset):
        past_limit (bool | None | Unset):
        stop_scope (None | str | Unset):
        episode_seq (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EconomicsOut | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
start_date=start_date,
end_date=end_date,
measures=measures,
group_by=group_by,
bucket=bucket,
basis=basis,
customer_id=customer_id,
event_type=event_type,
task_type=task_type,
task_id=task_id,
include_subtasks=include_subtasks,
where=where,
past_limit=past_limit,
stop_scope=stop_scope,
episode_seq=episode_seq,

    )).parsed
