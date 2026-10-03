from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.integration_blueprint_verification import IntegrationBlueprintVerification
from ...models.integration_blueprint_verification_in import IntegrationBlueprintVerificationIn
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    configuration_fingerprint: str,
    *,
    body: IntegrationBlueprintVerificationIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/code-builder/blueprints/{configuration_fingerprint}/verify".format(configuration_fingerprint=quote(str(configuration_fingerprint), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> IntegrationBlueprintVerification | ProblemOut | None:
    if response.status_code == 200:
        response_200 = IntegrationBlueprintVerification.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[IntegrationBlueprintVerification | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    configuration_fingerprint: str,
    *,
    client: AuthenticatedClient,
    body: IntegrationBlueprintVerificationIn,

) -> Response[IntegrationBlueprintVerification | ProblemOut]:
    """ Verify Blueprint

     Verify that the stored Blueprint a generated file was stamped with
    records and costs.

    The run builds the configuration stored under the fingerprint — never
    the configuration in force now — in a temporary tenant, starts the unit
    of work, starts each Subtask a recording names, makes each recording with
    the sample values you send and sends it a second time with the same
    idempotency key, then closes the work. Everything the run wrote is then
    discarded: nothing it records is kept, delivered or charged, and every id
    in the answer names a record that no longer exists. No API key is created
    and none is returned.

    `verified` is false where a recording has a gap or a call of the run was
    refused, and the answer names it: `missing_required_measurement_keys`, or
    the acknowledgement's `costing_status`, `unresolved_reason` and
    `uncosted_measurement_keys`, or `refusal`. A gap is a 200.

    `grouping_fields` carries a sample value for each Grouping Field the
    Blueprint's kinds of work require; one left out is started with
    `ubb-verification`, which matches no rule pinned to a value.

    `404 not_found` answers a fingerprint with no stored Blueprint — never
    resolved, or removed by the daily prune once 30 days have passed since it
    was last resolved: resolve the selection again. `422 event_type_not_available` answers a recording
    of an
    Event Type the stored Blueprint does not publish — one it did not select,
    or one that was undeclared or still a draft when it was resolved — and
    names each in `event_types`; nothing is run. `409 conflict` answers a
    stored Blueprint that is not `complete`. `422 validation_error` answers a
    `subtask_type` the Blueprint did not select, or a `grouping_fields` key no
    kind of work it selected requires.

    Args:
        configuration_fingerprint (str):
        body (IntegrationBlueprintVerificationIn): What one verification records, in order:
            between 1 and 50 events.

            `grouping_fields` is the sample value for each Grouping Field the
            Blueprint's kinds of work require, keyed as declared — the values a
            tenant's code passes when it starts the work. A required field left out
            is started with `ubb-verification`; a key no selected kind requires is
            refused.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IntegrationBlueprintVerification | ProblemOut]
     """


    kwargs = _get_kwargs(
        configuration_fingerprint=configuration_fingerprint,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    configuration_fingerprint: str,
    *,
    client: AuthenticatedClient,
    body: IntegrationBlueprintVerificationIn,

) -> IntegrationBlueprintVerification | ProblemOut | None:
    """ Verify Blueprint

     Verify that the stored Blueprint a generated file was stamped with
    records and costs.

    The run builds the configuration stored under the fingerprint — never
    the configuration in force now — in a temporary tenant, starts the unit
    of work, starts each Subtask a recording names, makes each recording with
    the sample values you send and sends it a second time with the same
    idempotency key, then closes the work. Everything the run wrote is then
    discarded: nothing it records is kept, delivered or charged, and every id
    in the answer names a record that no longer exists. No API key is created
    and none is returned.

    `verified` is false where a recording has a gap or a call of the run was
    refused, and the answer names it: `missing_required_measurement_keys`, or
    the acknowledgement's `costing_status`, `unresolved_reason` and
    `uncosted_measurement_keys`, or `refusal`. A gap is a 200.

    `grouping_fields` carries a sample value for each Grouping Field the
    Blueprint's kinds of work require; one left out is started with
    `ubb-verification`, which matches no rule pinned to a value.

    `404 not_found` answers a fingerprint with no stored Blueprint — never
    resolved, or removed by the daily prune once 30 days have passed since it
    was last resolved: resolve the selection again. `422 event_type_not_available` answers a recording
    of an
    Event Type the stored Blueprint does not publish — one it did not select,
    or one that was undeclared or still a draft when it was resolved — and
    names each in `event_types`; nothing is run. `409 conflict` answers a
    stored Blueprint that is not `complete`. `422 validation_error` answers a
    `subtask_type` the Blueprint did not select, or a `grouping_fields` key no
    kind of work it selected requires.

    Args:
        configuration_fingerprint (str):
        body (IntegrationBlueprintVerificationIn): What one verification records, in order:
            between 1 and 50 events.

            `grouping_fields` is the sample value for each Grouping Field the
            Blueprint's kinds of work require, keyed as declared — the values a
            tenant's code passes when it starts the work. A required field left out
            is started with `ubb-verification`; a key no selected kind requires is
            refused.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IntegrationBlueprintVerification | ProblemOut
     """


    return sync_detailed(
        configuration_fingerprint=configuration_fingerprint,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    configuration_fingerprint: str,
    *,
    client: AuthenticatedClient,
    body: IntegrationBlueprintVerificationIn,

) -> Response[IntegrationBlueprintVerification | ProblemOut]:
    """ Verify Blueprint

     Verify that the stored Blueprint a generated file was stamped with
    records and costs.

    The run builds the configuration stored under the fingerprint — never
    the configuration in force now — in a temporary tenant, starts the unit
    of work, starts each Subtask a recording names, makes each recording with
    the sample values you send and sends it a second time with the same
    idempotency key, then closes the work. Everything the run wrote is then
    discarded: nothing it records is kept, delivered or charged, and every id
    in the answer names a record that no longer exists. No API key is created
    and none is returned.

    `verified` is false where a recording has a gap or a call of the run was
    refused, and the answer names it: `missing_required_measurement_keys`, or
    the acknowledgement's `costing_status`, `unresolved_reason` and
    `uncosted_measurement_keys`, or `refusal`. A gap is a 200.

    `grouping_fields` carries a sample value for each Grouping Field the
    Blueprint's kinds of work require; one left out is started with
    `ubb-verification`, which matches no rule pinned to a value.

    `404 not_found` answers a fingerprint with no stored Blueprint — never
    resolved, or removed by the daily prune once 30 days have passed since it
    was last resolved: resolve the selection again. `422 event_type_not_available` answers a recording
    of an
    Event Type the stored Blueprint does not publish — one it did not select,
    or one that was undeclared or still a draft when it was resolved — and
    names each in `event_types`; nothing is run. `409 conflict` answers a
    stored Blueprint that is not `complete`. `422 validation_error` answers a
    `subtask_type` the Blueprint did not select, or a `grouping_fields` key no
    kind of work it selected requires.

    Args:
        configuration_fingerprint (str):
        body (IntegrationBlueprintVerificationIn): What one verification records, in order:
            between 1 and 50 events.

            `grouping_fields` is the sample value for each Grouping Field the
            Blueprint's kinds of work require, keyed as declared — the values a
            tenant's code passes when it starts the work. A required field left out
            is started with `ubb-verification`; a key no selected kind requires is
            refused.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IntegrationBlueprintVerification | ProblemOut]
     """


    kwargs = _get_kwargs(
        configuration_fingerprint=configuration_fingerprint,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    configuration_fingerprint: str,
    *,
    client: AuthenticatedClient,
    body: IntegrationBlueprintVerificationIn,

) -> IntegrationBlueprintVerification | ProblemOut | None:
    """ Verify Blueprint

     Verify that the stored Blueprint a generated file was stamped with
    records and costs.

    The run builds the configuration stored under the fingerprint — never
    the configuration in force now — in a temporary tenant, starts the unit
    of work, starts each Subtask a recording names, makes each recording with
    the sample values you send and sends it a second time with the same
    idempotency key, then closes the work. Everything the run wrote is then
    discarded: nothing it records is kept, delivered or charged, and every id
    in the answer names a record that no longer exists. No API key is created
    and none is returned.

    `verified` is false where a recording has a gap or a call of the run was
    refused, and the answer names it: `missing_required_measurement_keys`, or
    the acknowledgement's `costing_status`, `unresolved_reason` and
    `uncosted_measurement_keys`, or `refusal`. A gap is a 200.

    `grouping_fields` carries a sample value for each Grouping Field the
    Blueprint's kinds of work require; one left out is started with
    `ubb-verification`, which matches no rule pinned to a value.

    `404 not_found` answers a fingerprint with no stored Blueprint — never
    resolved, or removed by the daily prune once 30 days have passed since it
    was last resolved: resolve the selection again. `422 event_type_not_available` answers a recording
    of an
    Event Type the stored Blueprint does not publish — one it did not select,
    or one that was undeclared or still a draft when it was resolved — and
    names each in `event_types`; nothing is run. `409 conflict` answers a
    stored Blueprint that is not `complete`. `422 validation_error` answers a
    `subtask_type` the Blueprint did not select, or a `grouping_fields` key no
    kind of work it selected requires.

    Args:
        configuration_fingerprint (str):
        body (IntegrationBlueprintVerificationIn): What one verification records, in order:
            between 1 and 50 events.

            `grouping_fields` is the sample value for each Grouping Field the
            Blueprint's kinds of work require, keyed as declared — the values a
            tenant's code passes when it starts the work. A required field left out
            is started with `ubb-verification`; a key no selected kind requires is
            refused.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IntegrationBlueprintVerification | ProblemOut
     """


    return (await asyncio_detailed(
        configuration_fingerprint=configuration_fingerprint,
client=client,
body=body,

    )).parsed
