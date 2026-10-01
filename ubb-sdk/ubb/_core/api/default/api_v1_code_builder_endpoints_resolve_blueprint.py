from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.integration_blueprint_selection_in import IntegrationBlueprintSelectionIn
from ...models.problem_out import ProblemOut
from ...models.resolved_integration_blueprint import ResolvedIntegrationBlueprint
from typing import cast



def _get_kwargs(
    *,
    body: IntegrationBlueprintSelectionIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/code-builder/blueprints",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | ResolvedIntegrationBlueprint | None:
    if response.status_code == 200:
        response_200 = ResolvedIntegrationBlueprint.from_dict(response.json())



        return response_200

    if response.status_code == 403:
        response_403 = ProblemOut.from_dict(response.json())



        return response_403

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | ResolvedIntegrationBlueprint]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: IntegrationBlueprintSelectionIn,

) -> Response[ProblemOut | ResolvedIntegrationBlueprint]:
    """ Resolve Blueprint

     Resolve a selection into an Integration Blueprint.

    The Blueprint says what your integration code must mean: every call, each
    token of each call with where its value comes from, how ready each call
    is, and what stands in the way.

    Resolved from PUBLISHED configuration: an Event Type revised since it was
    published resolves from what it last published. The resolved content is
    stored, and `configuration_fingerprint` identifies it — the same selection
    answers the same fingerprint for as long as the configuration in force is
    the same. Nothing else is written, and no configuration is changed.

    With `draft_preview: true` the Blueprint resolves from draft declarations
    instead. That requires the admin role, stores nothing and answers
    `configuration_fingerprint: null`.

    `422 validation_error` answers a `target` that is not one of the published
    targets, or a selection naming more than 50 distinct Event Types or more
    than 50 distinct Subtask kinds.
    `403 forbidden` answers a draft preview asked for below the admin role.

    Args:
        body (IntegrationBlueprintSelectionIn): What an integration does, as far as it has to be
            said.

            Three things every integration states — the target it is written for, the
            kind of work it performs and the Event Types that happen inside it — and
            one it states only if it applies: the Subtask kinds it explicitly creates.
            Everything else is read from what you have already declared.

            `task_type` and `event_types` may be left out. The Blueprint is then a
            scaffold that shows the lifecycle's shape and says what is missing.

            Where an Event Type reads a supplier's response and declares no response
            shape, the Blueprint does not take a path here: it answers with a blocking
            diagnostic carrying the request that declares the shape.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ResolvedIntegrationBlueprint]
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
    body: IntegrationBlueprintSelectionIn,

) -> ProblemOut | ResolvedIntegrationBlueprint | None:
    """ Resolve Blueprint

     Resolve a selection into an Integration Blueprint.

    The Blueprint says what your integration code must mean: every call, each
    token of each call with where its value comes from, how ready each call
    is, and what stands in the way.

    Resolved from PUBLISHED configuration: an Event Type revised since it was
    published resolves from what it last published. The resolved content is
    stored, and `configuration_fingerprint` identifies it — the same selection
    answers the same fingerprint for as long as the configuration in force is
    the same. Nothing else is written, and no configuration is changed.

    With `draft_preview: true` the Blueprint resolves from draft declarations
    instead. That requires the admin role, stores nothing and answers
    `configuration_fingerprint: null`.

    `422 validation_error` answers a `target` that is not one of the published
    targets, or a selection naming more than 50 distinct Event Types or more
    than 50 distinct Subtask kinds.
    `403 forbidden` answers a draft preview asked for below the admin role.

    Args:
        body (IntegrationBlueprintSelectionIn): What an integration does, as far as it has to be
            said.

            Three things every integration states — the target it is written for, the
            kind of work it performs and the Event Types that happen inside it — and
            one it states only if it applies: the Subtask kinds it explicitly creates.
            Everything else is read from what you have already declared.

            `task_type` and `event_types` may be left out. The Blueprint is then a
            scaffold that shows the lifecycle's shape and says what is missing.

            Where an Event Type reads a supplier's response and declares no response
            shape, the Blueprint does not take a path here: it answers with a blocking
            diagnostic carrying the request that declares the shape.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ResolvedIntegrationBlueprint
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: IntegrationBlueprintSelectionIn,

) -> Response[ProblemOut | ResolvedIntegrationBlueprint]:
    """ Resolve Blueprint

     Resolve a selection into an Integration Blueprint.

    The Blueprint says what your integration code must mean: every call, each
    token of each call with where its value comes from, how ready each call
    is, and what stands in the way.

    Resolved from PUBLISHED configuration: an Event Type revised since it was
    published resolves from what it last published. The resolved content is
    stored, and `configuration_fingerprint` identifies it — the same selection
    answers the same fingerprint for as long as the configuration in force is
    the same. Nothing else is written, and no configuration is changed.

    With `draft_preview: true` the Blueprint resolves from draft declarations
    instead. That requires the admin role, stores nothing and answers
    `configuration_fingerprint: null`.

    `422 validation_error` answers a `target` that is not one of the published
    targets, or a selection naming more than 50 distinct Event Types or more
    than 50 distinct Subtask kinds.
    `403 forbidden` answers a draft preview asked for below the admin role.

    Args:
        body (IntegrationBlueprintSelectionIn): What an integration does, as far as it has to be
            said.

            Three things every integration states — the target it is written for, the
            kind of work it performs and the Event Types that happen inside it — and
            one it states only if it applies: the Subtask kinds it explicitly creates.
            Everything else is read from what you have already declared.

            `task_type` and `event_types` may be left out. The Blueprint is then a
            scaffold that shows the lifecycle's shape and says what is missing.

            Where an Event Type reads a supplier's response and declares no response
            shape, the Blueprint does not take a path here: it answers with a blocking
            diagnostic carrying the request that declares the shape.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ResolvedIntegrationBlueprint]
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
    body: IntegrationBlueprintSelectionIn,

) -> ProblemOut | ResolvedIntegrationBlueprint | None:
    """ Resolve Blueprint

     Resolve a selection into an Integration Blueprint.

    The Blueprint says what your integration code must mean: every call, each
    token of each call with where its value comes from, how ready each call
    is, and what stands in the way.

    Resolved from PUBLISHED configuration: an Event Type revised since it was
    published resolves from what it last published. The resolved content is
    stored, and `configuration_fingerprint` identifies it — the same selection
    answers the same fingerprint for as long as the configuration in force is
    the same. Nothing else is written, and no configuration is changed.

    With `draft_preview: true` the Blueprint resolves from draft declarations
    instead. That requires the admin role, stores nothing and answers
    `configuration_fingerprint: null`.

    `422 validation_error` answers a `target` that is not one of the published
    targets, or a selection naming more than 50 distinct Event Types or more
    than 50 distinct Subtask kinds.
    `403 forbidden` answers a draft preview asked for below the admin role.

    Args:
        body (IntegrationBlueprintSelectionIn): What an integration does, as far as it has to be
            said.

            Three things every integration states — the target it is written for, the
            kind of work it performs and the Event Types that happen inside it — and
            one it states only if it applies: the Subtask kinds it explicitly creates.
            Everything else is read from what you have already declared.

            `task_type` and `event_types` may be left out. The Blueprint is then a
            scaffold that shows the lifecycle's shape and says what is missing.

            Where an Event Type reads a supplier's response and declares no response
            shape, the Blueprint does not take a path here: it answers with a blocking
            diagnostic carrying the request that declares the shape.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ResolvedIntegrationBlueprint
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
