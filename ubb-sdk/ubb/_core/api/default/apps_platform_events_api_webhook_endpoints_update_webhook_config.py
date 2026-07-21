from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.webhook_config_response import WebhookConfigResponse
from ...models.webhook_config_update_request import WebhookConfigUpdateRequest
from typing import cast



def _get_kwargs(
    config_id: str,
    *,
    body: WebhookConfigUpdateRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v1/webhooks/configs/{config_id}".format(config_id=quote(str(config_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | WebhookConfigResponse | None:
    if response.status_code == 200:
        response_200 = WebhookConfigResponse.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | WebhookConfigResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    config_id: str,
    *,
    client: AuthenticatedClient,
    body: WebhookConfigUpdateRequest,

) -> Response[ProblemOut | WebhookConfigResponse]:
    """ Update Webhook Config

     Edit url / event_types / pause-resume in place — no delete-and-recreate.

    The secret is not a field here: it is untouchable via PATCH and moves only
    through the rotation endpoint (#83).

    Args:
        config_id (str):
        body (WebhookConfigUpdateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | WebhookConfigResponse]
     """


    kwargs = _get_kwargs(
        config_id=config_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    config_id: str,
    *,
    client: AuthenticatedClient,
    body: WebhookConfigUpdateRequest,

) -> ProblemOut | WebhookConfigResponse | None:
    """ Update Webhook Config

     Edit url / event_types / pause-resume in place — no delete-and-recreate.

    The secret is not a field here: it is untouchable via PATCH and moves only
    through the rotation endpoint (#83).

    Args:
        config_id (str):
        body (WebhookConfigUpdateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | WebhookConfigResponse
     """


    return sync_detailed(
        config_id=config_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    config_id: str,
    *,
    client: AuthenticatedClient,
    body: WebhookConfigUpdateRequest,

) -> Response[ProblemOut | WebhookConfigResponse]:
    """ Update Webhook Config

     Edit url / event_types / pause-resume in place — no delete-and-recreate.

    The secret is not a field here: it is untouchable via PATCH and moves only
    through the rotation endpoint (#83).

    Args:
        config_id (str):
        body (WebhookConfigUpdateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | WebhookConfigResponse]
     """


    kwargs = _get_kwargs(
        config_id=config_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    config_id: str,
    *,
    client: AuthenticatedClient,
    body: WebhookConfigUpdateRequest,

) -> ProblemOut | WebhookConfigResponse | None:
    """ Update Webhook Config

     Edit url / event_types / pause-resume in place — no delete-and-recreate.

    The secret is not a field here: it is untouchable via PATCH and moves only
    through the rotation endpoint (#83).

    Args:
        config_id (str):
        body (WebhookConfigUpdateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | WebhookConfigResponse
     """


    return (await asyncio_detailed(
        config_id=config_id,
client=client,
body=body,

    )).parsed
