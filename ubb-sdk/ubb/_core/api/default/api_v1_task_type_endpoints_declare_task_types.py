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
        "url": "/api/v1/task-types",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | TaskTypeRegistryOut | None:
    if response.status_code == 200:
        response_200 = TaskTypeRegistryOut.from_dict(response.json())



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

     Declare the kinds of work you meter, and the policy each one carries.

    Idempotent: send the whole vocabulary every time. A kind of work you have
    already declared has its ceiling, its two windows and its
    `required_dimensions` updated in place.

    `pricing_mode` CANNOT BE CHANGED once a kind of work exists. Sending a
    different one answers `409 pricing_mode_frozen`; to change how a kind of
    work is sold, retire it with `retired: true` and declare a replacement under
    a new key. A key change is an integration change for you, so choose the
    regime with that in mind. Omitting it leaves an existing kind of work
    exactly as it is, and declares a new one `event_priced`.

    `retired: true` stops new work of that kind being started and leaves the
    declaration readable; `retired: false` brings it back. Omitting `retired`
    leaves it exactly as it is.

    `422 validation_error` answers a kind this registry does not recognise or a
    `required_dimensions` entry you have not declared as a grouping field.

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

     Declare the kinds of work you meter, and the policy each one carries.

    Idempotent: send the whole vocabulary every time. A kind of work you have
    already declared has its ceiling, its two windows and its
    `required_dimensions` updated in place.

    `pricing_mode` CANNOT BE CHANGED once a kind of work exists. Sending a
    different one answers `409 pricing_mode_frozen`; to change how a kind of
    work is sold, retire it with `retired: true` and declare a replacement under
    a new key. A key change is an integration change for you, so choose the
    regime with that in mind. Omitting it leaves an existing kind of work
    exactly as it is, and declares a new one `event_priced`.

    `retired: true` stops new work of that kind being started and leaves the
    declaration readable; `retired: false` brings it back. Omitting `retired`
    leaves it exactly as it is.

    `422 validation_error` answers a kind this registry does not recognise or a
    `required_dimensions` entry you have not declared as a grouping field.

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

     Declare the kinds of work you meter, and the policy each one carries.

    Idempotent: send the whole vocabulary every time. A kind of work you have
    already declared has its ceiling, its two windows and its
    `required_dimensions` updated in place.

    `pricing_mode` CANNOT BE CHANGED once a kind of work exists. Sending a
    different one answers `409 pricing_mode_frozen`; to change how a kind of
    work is sold, retire it with `retired: true` and declare a replacement under
    a new key. A key change is an integration change for you, so choose the
    regime with that in mind. Omitting it leaves an existing kind of work
    exactly as it is, and declares a new one `event_priced`.

    `retired: true` stops new work of that kind being started and leaves the
    declaration readable; `retired: false` brings it back. Omitting `retired`
    leaves it exactly as it is.

    `422 validation_error` answers a kind this registry does not recognise or a
    `required_dimensions` entry you have not declared as a grouping field.

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

     Declare the kinds of work you meter, and the policy each one carries.

    Idempotent: send the whole vocabulary every time. A kind of work you have
    already declared has its ceiling, its two windows and its
    `required_dimensions` updated in place.

    `pricing_mode` CANNOT BE CHANGED once a kind of work exists. Sending a
    different one answers `409 pricing_mode_frozen`; to change how a kind of
    work is sold, retire it with `retired: true` and declare a replacement under
    a new key. A key change is an integration change for you, so choose the
    regime with that in mind. Omitting it leaves an existing kind of work
    exactly as it is, and declares a new one `event_priced`.

    `retired: true` stops new work of that kind being started and leaves the
    declaration readable; `retired: false` brings it back. Omitting `retired`
    leaves it exactly as it is.

    `422 validation_error` answers a kind this registry does not recognise or a
    `required_dimensions` entry you have not declared as a grouping field.

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
