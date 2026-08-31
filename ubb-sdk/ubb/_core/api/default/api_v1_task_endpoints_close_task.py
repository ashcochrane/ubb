from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.close_task_request import CloseTaskRequest
from ...models.close_task_response import CloseTaskResponse
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    task_id: UUID,
    *,
    body: CloseTaskRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/tasks/{task_id}/close".format(task_id=quote(str(task_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> CloseTaskResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = CloseTaskResponse.from_dict(response.json())



        return response_200

    if response.status_code == 409:
        response_409 = ProblemOut.from_dict(response.json())



        return response_409

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[CloseTaskResponse | ProblemOut]:
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
    body: CloseTaskRequest,

) -> Response[CloseTaskResponse | ProblemOut]:
    """ Close Task

     Close a unit of work, DECLARING HOW IT ENDED.

    The outcome is required. Declaring delivery on work sold at one agreed
    price creates its charge, exactly once — `charge_created` says whether this
    call created one. No other ending creates one. Closing a parent withdraws
    its still-running contained work in the same transaction — cleanup is one
    call — and closing contained work closes it alone.

    ⚠ THIS DOES NOT TOUCH THE USAGE RAIL. A terminal state prevents a customer
    charge; it never rejects, deletes or zeroes genuine operational usage,
    including usage that arrives after termination. A late report on a closed
    unit still lands, costs and rolls up.

    Args:
        task_id (UUID):
        body (CloseTaskRequest): The declaration that ends a unit of work.

            ONE call and ONE mandatory field. Two endpoints (`/close` and `/fail`) was
            rejected as two of everything, and optional-with-a-delivered-default was
            rejected on the strongest rule available: THE FORGIVING PATH MUST NEVER BE
            THE MONEY-MOVING ONE. A dropped field, a stale example or an old client
            would otherwise bill a customer for work that failed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CloseTaskResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        task_id=task_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CloseTaskRequest,

) -> CloseTaskResponse | ProblemOut | None:
    """ Close Task

     Close a unit of work, DECLARING HOW IT ENDED.

    The outcome is required. Declaring delivery on work sold at one agreed
    price creates its charge, exactly once — `charge_created` says whether this
    call created one. No other ending creates one. Closing a parent withdraws
    its still-running contained work in the same transaction — cleanup is one
    call — and closing contained work closes it alone.

    ⚠ THIS DOES NOT TOUCH THE USAGE RAIL. A terminal state prevents a customer
    charge; it never rejects, deletes or zeroes genuine operational usage,
    including usage that arrives after termination. A late report on a closed
    unit still lands, costs and rolls up.

    Args:
        task_id (UUID):
        body (CloseTaskRequest): The declaration that ends a unit of work.

            ONE call and ONE mandatory field. Two endpoints (`/close` and `/fail`) was
            rejected as two of everything, and optional-with-a-delivered-default was
            rejected on the strongest rule available: THE FORGIVING PATH MUST NEVER BE
            THE MONEY-MOVING ONE. A dropped field, a stale example or an old client
            would otherwise bill a customer for work that failed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CloseTaskResponse | ProblemOut
     """


    return sync_detailed(
        task_id=task_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CloseTaskRequest,

) -> Response[CloseTaskResponse | ProblemOut]:
    """ Close Task

     Close a unit of work, DECLARING HOW IT ENDED.

    The outcome is required. Declaring delivery on work sold at one agreed
    price creates its charge, exactly once — `charge_created` says whether this
    call created one. No other ending creates one. Closing a parent withdraws
    its still-running contained work in the same transaction — cleanup is one
    call — and closing contained work closes it alone.

    ⚠ THIS DOES NOT TOUCH THE USAGE RAIL. A terminal state prevents a customer
    charge; it never rejects, deletes or zeroes genuine operational usage,
    including usage that arrives after termination. A late report on a closed
    unit still lands, costs and rolls up.

    Args:
        task_id (UUID):
        body (CloseTaskRequest): The declaration that ends a unit of work.

            ONE call and ONE mandatory field. Two endpoints (`/close` and `/fail`) was
            rejected as two of everything, and optional-with-a-delivered-default was
            rejected on the strongest rule available: THE FORGIVING PATH MUST NEVER BE
            THE MONEY-MOVING ONE. A dropped field, a stale example or an old client
            would otherwise bill a customer for work that failed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CloseTaskResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        task_id=task_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CloseTaskRequest,

) -> CloseTaskResponse | ProblemOut | None:
    """ Close Task

     Close a unit of work, DECLARING HOW IT ENDED.

    The outcome is required. Declaring delivery on work sold at one agreed
    price creates its charge, exactly once — `charge_created` says whether this
    call created one. No other ending creates one. Closing a parent withdraws
    its still-running contained work in the same transaction — cleanup is one
    call — and closing contained work closes it alone.

    ⚠ THIS DOES NOT TOUCH THE USAGE RAIL. A terminal state prevents a customer
    charge; it never rejects, deletes or zeroes genuine operational usage,
    including usage that arrives after termination. A late report on a closed
    unit still lands, costs and rolls up.

    Args:
        task_id (UUID):
        body (CloseTaskRequest): The declaration that ends a unit of work.

            ONE call and ONE mandatory field. Two endpoints (`/close` and `/fail`) was
            rejected as two of everything, and optional-with-a-delivered-default was
            rejected on the strongest rule available: THE FORGIVING PATH MUST NEVER BE
            THE MONEY-MOVING ONE. A dropped field, a stale example or an old client
            would otherwise bill a customer for work that failed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CloseTaskResponse | ProblemOut
     """


    return (await asyncio_detailed(
        task_id=task_id,
client=client,
body=body,

    )).parsed
