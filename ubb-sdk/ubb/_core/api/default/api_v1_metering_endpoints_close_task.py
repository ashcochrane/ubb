from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.close_task_response import CloseTaskResponse
from typing import cast
from uuid import UUID



def _get_kwargs(
    task_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/tasks/{task_id}/close".format(task_id=quote(str(task_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> CloseTaskResponse | None:
    if response.status_code == 200:
        response_200 = CloseTaskResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[CloseTaskResponse]:
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

) -> Response[CloseTaskResponse]:
    """ Close Task

     Close (complete) a task or subtask. Closing a PARENT auto-completes
    its active subtasks in the same transaction (#38) — cleanup is one call;
    a killed subtask keeps its state. Closing a subtask completes it alone.

    Args:
        task_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CloseTaskResponse]
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

) -> CloseTaskResponse | None:
    """ Close Task

     Close (complete) a task or subtask. Closing a PARENT auto-completes
    its active subtasks in the same transaction (#38) — cleanup is one call;
    a killed subtask keeps its state. Closing a subtask completes it alone.

    Args:
        task_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CloseTaskResponse
     """


    return sync_detailed(
        task_id=task_id,
client=client,

    ).parsed

async def asyncio_detailed(
    task_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[CloseTaskResponse]:
    """ Close Task

     Close (complete) a task or subtask. Closing a PARENT auto-completes
    its active subtasks in the same transaction (#38) — cleanup is one call;
    a killed subtask keeps its state. Closing a subtask completes it alone.

    Args:
        task_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CloseTaskResponse]
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

) -> CloseTaskResponse | None:
    """ Close Task

     Close (complete) a task or subtask. Closing a PARENT auto-completes
    its active subtasks in the same transaction (#38) — cleanup is one call;
    a killed subtask keeps its state. Closing a subtask completes it alone.

    Args:
        task_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CloseTaskResponse
     """


    return (await asyncio_detailed(
        task_id=task_id,
client=client,

    )).parsed
