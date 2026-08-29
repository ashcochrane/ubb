from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.paginated_tasks import PaginatedTasks
from ...models.problem_out import ProblemOut
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID



def _get_kwargs(
    task_id: UUID,
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
        "url": "/api/v1/tasks/{task_id}/subtasks".format(task_id=quote(str(task_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> PaginatedTasks | ProblemOut | None:
    if response.status_code == 200:
        response_200 = PaginatedTasks.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[PaginatedTasks | ProblemOut]:
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
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[PaginatedTasks | ProblemOut]:
    """ List Subtasks

     The work contained in one unit.

    A unit with nothing inside it answers an empty collection, not a 404: the
    unit exists, and *nothing is contained in it* is the true answer about it.
    An unknown unit — or one belonging to another tenant — is a 404.

    Registering contained work is not here. A contained start is a start and
    goes through `POST /tasks` with `parent_task_id` named, so there is one
    registration shape at either altitude and this collection is purely the
    read side of it.

    Args:
        task_id (UUID):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PaginatedTasks | ProblemOut]
     """


    kwargs = _get_kwargs(
        task_id=task_id,
cursor=cursor,
limit=limit,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> PaginatedTasks | ProblemOut | None:
    """ List Subtasks

     The work contained in one unit.

    A unit with nothing inside it answers an empty collection, not a 404: the
    unit exists, and *nothing is contained in it* is the true answer about it.
    An unknown unit — or one belonging to another tenant — is a 404.

    Registering contained work is not here. A contained start is a start and
    goes through `POST /tasks` with `parent_task_id` named, so there is one
    registration shape at either altitude and this collection is purely the
    read side of it.

    Args:
        task_id (UUID):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PaginatedTasks | ProblemOut
     """


    return sync_detailed(
        task_id=task_id,
client=client,
cursor=cursor,
limit=limit,

    ).parsed

async def asyncio_detailed(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[PaginatedTasks | ProblemOut]:
    """ List Subtasks

     The work contained in one unit.

    A unit with nothing inside it answers an empty collection, not a 404: the
    unit exists, and *nothing is contained in it* is the true answer about it.
    An unknown unit — or one belonging to another tenant — is a 404.

    Registering contained work is not here. A contained start is a start and
    goes through `POST /tasks` with `parent_task_id` named, so there is one
    registration shape at either altitude and this collection is purely the
    read side of it.

    Args:
        task_id (UUID):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PaginatedTasks | ProblemOut]
     """


    kwargs = _get_kwargs(
        task_id=task_id,
cursor=cursor,
limit=limit,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> PaginatedTasks | ProblemOut | None:
    """ List Subtasks

     The work contained in one unit.

    A unit with nothing inside it answers an empty collection, not a 404: the
    unit exists, and *nothing is contained in it* is the true answer about it.
    An unknown unit — or one belonging to another tenant — is a 404.

    Registering contained work is not here. A contained start is a start and
    goes through `POST /tasks` with `parent_task_id` named, so there is one
    registration shape at either altitude and this collection is purely the
    read side of it.

    Args:
        task_id (UUID):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PaginatedTasks | ProblemOut
     """


    return (await asyncio_detailed(
        task_id=task_id,
client=client,
cursor=cursor,
limit=limit,

    )).parsed
