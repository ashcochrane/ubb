from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_sandbox_endpoints_reset_sandbox_response import ApiV1SandboxEndpointsResetSandboxResponse
from ...models.problem_out import ProblemOut
from ...models.sandbox_reset_in import SandboxResetIn
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    body: None | SandboxResetIn | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/sandbox/reset",
    }

    
    if isinstance(body, SandboxResetIn):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut | None:
    if response.status_code == 202:
        response_202 = ApiV1SandboxEndpointsResetSandboxResponse.from_dict(response.json())



        return response_202

    if response.status_code == 403:
        response_403 = ProblemOut.from_dict(response.json())



        return response_403

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: None | SandboxResetIn | Unset = UNSET,

) -> Response[ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut]:
    """ Reset Sandbox

     Asynchronously wipe the calling SANDBOX tenant's domain data.

    keep_config=true (default) preserves rate cards, markups, plans, budget /
    billing / postpaid / webhook configs; the Tenant row and its API keys
    always survive. Returns 202 — the wipe runs as a Celery task and the
    sandbox 401s (deactivated) until it completes.

    The wipe clears the sandbox's own audit entries and records this reset as
    the first entry of the fresh history (ADR-004). The reset is async, so the
    acting principal — captured at the auth seam — is threaded to the task by
    value; ``record()`` in a worker has no request-scoped actor to read.

    Args:
        body (None | SandboxResetIn | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut]
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
    body: None | SandboxResetIn | Unset = UNSET,

) -> ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut | None:
    """ Reset Sandbox

     Asynchronously wipe the calling SANDBOX tenant's domain data.

    keep_config=true (default) preserves rate cards, markups, plans, budget /
    billing / postpaid / webhook configs; the Tenant row and its API keys
    always survive. Returns 202 — the wipe runs as a Celery task and the
    sandbox 401s (deactivated) until it completes.

    The wipe clears the sandbox's own audit entries and records this reset as
    the first entry of the fresh history (ADR-004). The reset is async, so the
    acting principal — captured at the auth seam — is threaded to the task by
    value; ``record()`` in a worker has no request-scoped actor to read.

    Args:
        body (None | SandboxResetIn | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: None | SandboxResetIn | Unset = UNSET,

) -> Response[ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut]:
    """ Reset Sandbox

     Asynchronously wipe the calling SANDBOX tenant's domain data.

    keep_config=true (default) preserves rate cards, markups, plans, budget /
    billing / postpaid / webhook configs; the Tenant row and its API keys
    always survive. Returns 202 — the wipe runs as a Celery task and the
    sandbox 401s (deactivated) until it completes.

    The wipe clears the sandbox's own audit entries and records this reset as
    the first entry of the fresh history (ADR-004). The reset is async, so the
    acting principal — captured at the auth seam — is threaded to the task by
    value; ``record()`` in a worker has no request-scoped actor to read.

    Args:
        body (None | SandboxResetIn | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut]
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
    body: None | SandboxResetIn | Unset = UNSET,

) -> ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut | None:
    """ Reset Sandbox

     Asynchronously wipe the calling SANDBOX tenant's domain data.

    keep_config=true (default) preserves rate cards, markups, plans, budget /
    billing / postpaid / webhook configs; the Tenant row and its API keys
    always survive. Returns 202 — the wipe runs as a Celery task and the
    sandbox 401s (deactivated) until it completes.

    The wipe clears the sandbox's own audit entries and records this reset as
    the first entry of the fresh history (ADR-004). The reset is async, so the
    acting principal — captured at the auth seam — is threaded to the task by
    value; ``record()`` in a worker has no request-scoped actor to read.

    Args:
        body (None | SandboxResetIn | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1SandboxEndpointsResetSandboxResponse | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
