from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.task_detail_out import TaskDetailOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    task_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/tasks/{task_id}".format(task_id=quote(str(task_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | TaskDetailOut | None:
    if response.status_code == 200:
        response_200 = TaskDetailOut.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | TaskDetailOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    task_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ProblemOut | TaskDetailOut]:
    """ Get Task

     One unit's cost receipt plus its subtask tree.

    Reads the rollups `TaskService.accumulate_cost` maintains — including
    events that landed after a kill — so this never aggregates
    ubb_usage_event. One indexed row read plus its children.

    Args:
        task_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | TaskDetailOut]
     """


    kwargs = _get_kwargs(
        task_id=task_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    task_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ProblemOut | TaskDetailOut | None:
    """ Get Task

     One unit's cost receipt plus its subtask tree.

    Reads the rollups `TaskService.accumulate_cost` maintains — including
    events that landed after a kill — so this never aggregates
    ubb_usage_event. One indexed row read plus its children.

    Args:
        task_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | TaskDetailOut
     """


    return sync_detailed(
        task_id=task_id,
client=client,

    ).parsed

async def asyncio_detailed(
    task_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ProblemOut | TaskDetailOut]:
    """ Get Task

     One unit's cost receipt plus its subtask tree.

    Reads the rollups `TaskService.accumulate_cost` maintains — including
    events that landed after a kill — so this never aggregates
    ubb_usage_event. One indexed row read plus its children.

    Args:
        task_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | TaskDetailOut]
     """


    kwargs = _get_kwargs(
        task_id=task_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    task_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ProblemOut | TaskDetailOut | None:
    """ Get Task

     One unit's cost receipt plus its subtask tree.

    Reads the rollups `TaskService.accumulate_cost` maintains — including
    events that landed after a kill — so this never aggregates
    ubb_usage_event. One indexed row read plus its children.

    Args:
        task_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | TaskDetailOut
     """


    return (await asyncio_detailed(
        task_id=task_id,
client=client,

    )).parsed
