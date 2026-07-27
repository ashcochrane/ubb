from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.task_type_registry_in import TaskTypeRegistryIn
from ...models.task_type_registry_out import TaskTypeRegistryOut
from typing import cast



def _get_kwargs(
    *,
    body: TaskTypeRegistryIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/metering/task-types",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | TaskTypeRegistryOut | None:
    if response.status_code == 200:
        response_200 = TaskTypeRegistryOut.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | TaskTypeRegistryOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: TaskTypeRegistryIn,

) -> Response[ProblemOut | TaskTypeRegistryOut]:
    """ Declare Task Types

     Declare the tenant's work vocabulary and its per-kind COGS ceilings
    (design D7). Idempotent; the ceiling and required_dimensions may be updated
    on a re-PUT. Admin-floored: a task type's ceiling prices usage the same way
    markup.set/rate_card.* do, so it takes the write-default Admin floor rather
    than a Write carve-out.

    Args:
        body (TaskTypeRegistryIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | TaskTypeRegistryOut]
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
    body: TaskTypeRegistryIn,

) -> ProblemOut | TaskTypeRegistryOut | None:
    """ Declare Task Types

     Declare the tenant's work vocabulary and its per-kind COGS ceilings
    (design D7). Idempotent; the ceiling and required_dimensions may be updated
    on a re-PUT. Admin-floored: a task type's ceiling prices usage the same way
    markup.set/rate_card.* do, so it takes the write-default Admin floor rather
    than a Write carve-out.

    Args:
        body (TaskTypeRegistryIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | TaskTypeRegistryOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: TaskTypeRegistryIn,

) -> Response[ProblemOut | TaskTypeRegistryOut]:
    """ Declare Task Types

     Declare the tenant's work vocabulary and its per-kind COGS ceilings
    (design D7). Idempotent; the ceiling and required_dimensions may be updated
    on a re-PUT. Admin-floored: a task type's ceiling prices usage the same way
    markup.set/rate_card.* do, so it takes the write-default Admin floor rather
    than a Write carve-out.

    Args:
        body (TaskTypeRegistryIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | TaskTypeRegistryOut]
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
    body: TaskTypeRegistryIn,

) -> ProblemOut | TaskTypeRegistryOut | None:
    """ Declare Task Types

     Declare the tenant's work vocabulary and its per-kind COGS ceilings
    (design D7). Idempotent; the ceiling and required_dimensions may be updated
    on a re-PUT. Admin-floored: a task type's ceiling prices usage the same way
    markup.set/rate_card.* do, so it takes the write-default Admin floor rather
    than a Write carve-out.

    Args:
        body (TaskTypeRegistryIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | TaskTypeRegistryOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
