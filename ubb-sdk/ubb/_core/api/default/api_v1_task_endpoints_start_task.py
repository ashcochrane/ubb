from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.start_task_request import StartTaskRequest
from ...models.start_task_response import StartTaskResponse
from typing import cast



def _get_kwargs(
    *,
    body: StartTaskRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/tasks",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | StartTaskResponse | None:
    if response.status_code == 200:
        response_200 = StartTaskResponse.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | StartTaskResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: StartTaskRequest,

) -> Response[ProblemOut | StartTaskResponse]:
    """ Start Task

     Register a unit of work, and hand back the same one on a retry.

    `idempotency_key` is REQUIRED and is unique per customer. Send the same key
    again and you get the unit of work you already started, with
    `replayed: true` and nothing created a second time — no second ceiling, no
    second set of totals. Send the same key describing a DIFFERENT unit and the
    call answers `409 idempotency_key_conflict`, naming the request field that
    differs. A unit of work is pinned by its customer, its parent, its declared
    kind of work, the ceiling it resolved and the grouping values declared on
    it. `external_task_id` and `metadata` are not pinned — a replay carrying
    different values is still a replay, and the original's values stand.

    Naming `parent_task_id` registers contained work under a running unit.
    There is one start shape, not two.

    `409 task_start_refused` names, in `reason`, why the customer may not begin
    new work — a wallet below its floor, a stop in force, the concurrency cap,
    or a parent that is not a running top-level unit. `422 validation_error`
    answers a request that is wrong in itself: an undeclared or retired kind of
    work, a missing required grouping field, an undeclared grouping key, or a
    ceiling above the one the kind of work carries.

    Args:
        body (StartTaskRequest): The declaration that REGISTERS a unit of work (#410).

            There is one start call and one start shape, whichever altitude the work
            sits at: naming ``parent_task_id`` registers contained work under a running
            unit, and everything else about the call is identical. A contained start is
            a start, so it claims a key like any other.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | StartTaskResponse]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    body: StartTaskRequest,

) -> ProblemOut | StartTaskResponse | None:
    """ Start Task

     Register a unit of work, and hand back the same one on a retry.

    `idempotency_key` is REQUIRED and is unique per customer. Send the same key
    again and you get the unit of work you already started, with
    `replayed: true` and nothing created a second time — no second ceiling, no
    second set of totals. Send the same key describing a DIFFERENT unit and the
    call answers `409 idempotency_key_conflict`, naming the request field that
    differs. A unit of work is pinned by its customer, its parent, its declared
    kind of work, the ceiling it resolved and the grouping values declared on
    it. `external_task_id` and `metadata` are not pinned — a replay carrying
    different values is still a replay, and the original's values stand.

    Naming `parent_task_id` registers contained work under a running unit.
    There is one start shape, not two.

    `409 task_start_refused` names, in `reason`, why the customer may not begin
    new work — a wallet below its floor, a stop in force, the concurrency cap,
    or a parent that is not a running top-level unit. `422 validation_error`
    answers a request that is wrong in itself: an undeclared or retired kind of
    work, a missing required grouping field, an undeclared grouping key, or a
    ceiling above the one the kind of work carries.

    Args:
        body (StartTaskRequest): The declaration that REGISTERS a unit of work (#410).

            There is one start call and one start shape, whichever altitude the work
            sits at: naming ``parent_task_id`` registers contained work under a running
            unit, and everything else about the call is identical. A contained start is
            a start, so it claims a key like any other.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | StartTaskResponse
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: StartTaskRequest,

) -> Response[ProblemOut | StartTaskResponse]:
    """ Start Task

     Register a unit of work, and hand back the same one on a retry.

    `idempotency_key` is REQUIRED and is unique per customer. Send the same key
    again and you get the unit of work you already started, with
    `replayed: true` and nothing created a second time — no second ceiling, no
    second set of totals. Send the same key describing a DIFFERENT unit and the
    call answers `409 idempotency_key_conflict`, naming the request field that
    differs. A unit of work is pinned by its customer, its parent, its declared
    kind of work, the ceiling it resolved and the grouping values declared on
    it. `external_task_id` and `metadata` are not pinned — a replay carrying
    different values is still a replay, and the original's values stand.

    Naming `parent_task_id` registers contained work under a running unit.
    There is one start shape, not two.

    `409 task_start_refused` names, in `reason`, why the customer may not begin
    new work — a wallet below its floor, a stop in force, the concurrency cap,
    or a parent that is not a running top-level unit. `422 validation_error`
    answers a request that is wrong in itself: an undeclared or retired kind of
    work, a missing required grouping field, an undeclared grouping key, or a
    ceiling above the one the kind of work carries.

    Args:
        body (StartTaskRequest): The declaration that REGISTERS a unit of work (#410).

            There is one start call and one start shape, whichever altitude the work
            sits at: naming ``parent_task_id`` registers contained work under a running
            unit, and everything else about the call is identical. A contained start is
            a start, so it claims a key like any other.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | StartTaskResponse]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    body: StartTaskRequest,

) -> ProblemOut | StartTaskResponse | None:
    """ Start Task

     Register a unit of work, and hand back the same one on a retry.

    `idempotency_key` is REQUIRED and is unique per customer. Send the same key
    again and you get the unit of work you already started, with
    `replayed: true` and nothing created a second time — no second ceiling, no
    second set of totals. Send the same key describing a DIFFERENT unit and the
    call answers `409 idempotency_key_conflict`, naming the request field that
    differs. A unit of work is pinned by its customer, its parent, its declared
    kind of work, the ceiling it resolved and the grouping values declared on
    it. `external_task_id` and `metadata` are not pinned — a replay carrying
    different values is still a replay, and the original's values stand.

    Naming `parent_task_id` registers contained work under a running unit.
    There is one start shape, not two.

    `409 task_start_refused` names, in `reason`, why the customer may not begin
    new work — a wallet below its floor, a stop in force, the concurrency cap,
    or a parent that is not a running top-level unit. `422 validation_error`
    answers a request that is wrong in itself: an undeclared or retired kind of
    work, a missing required grouping field, an undeclared grouping key, or a
    ceiling above the one the kind of work carries.

    Args:
        body (StartTaskRequest): The declaration that REGISTERS a unit of work (#410).

            There is one start call and one start shape, whichever altitude the work
            sits at: naming ``parent_task_id`` registers contained work under a running
            unit, and everything else about the call is identical. A contained start is
            a start, so it claims a key like any other.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | StartTaskResponse
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
