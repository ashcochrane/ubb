from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.webhook_config_response import WebhookConfigResponse
from ...models.webhook_secret_rotate_request import WebhookSecretRotateRequest
from typing import cast



def _get_kwargs(
    config_id: str,
    *,
    body: WebhookSecretRotateRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/webhooks/configs/{config_id}/rotate-secret".format(config_id=quote(str(config_id), safe=""),),
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
    body: WebhookSecretRotateRequest,

) -> Response[ProblemOut | WebhookConfigResponse]:
    """ Rotate Webhook Secret

     Two-secret overlap rotation: the current secret keeps signing a second
    `v1=` candidate for `overlap_hours` while the new one takes over, so a
    receiver verifies with zero downtime. Rotating again mid-window replaces
    the retiring secret (#83).

    Args:
        config_id (str):
        body (WebhookSecretRotateRequest):

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
    body: WebhookSecretRotateRequest,

) -> ProblemOut | WebhookConfigResponse | None:
    """ Rotate Webhook Secret

     Two-secret overlap rotation: the current secret keeps signing a second
    `v1=` candidate for `overlap_hours` while the new one takes over, so a
    receiver verifies with zero downtime. Rotating again mid-window replaces
    the retiring secret (#83).

    Args:
        config_id (str):
        body (WebhookSecretRotateRequest):

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
    body: WebhookSecretRotateRequest,

) -> Response[ProblemOut | WebhookConfigResponse]:
    """ Rotate Webhook Secret

     Two-secret overlap rotation: the current secret keeps signing a second
    `v1=` candidate for `overlap_hours` while the new one takes over, so a
    receiver verifies with zero downtime. Rotating again mid-window replaces
    the retiring secret (#83).

    Args:
        config_id (str):
        body (WebhookSecretRotateRequest):

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
    body: WebhookSecretRotateRequest,

) -> ProblemOut | WebhookConfigResponse | None:
    """ Rotate Webhook Secret

     Two-secret overlap rotation: the current secret keeps signing a second
    `v1=` candidate for `overlap_hours` while the new one takes over, so a
    receiver verifies with zero downtime. Rotating again mid-window replaces
    the retiring secret (#83).

    Args:
        config_id (str):
        body (WebhookSecretRotateRequest):

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
