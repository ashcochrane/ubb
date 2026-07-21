from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_tenant_endpoints_create_sandbox_response import ApiV1TenantEndpointsCreateSandboxResponse
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/tenant/sandbox",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1TenantEndpointsCreateSandboxResponse.from_dict(response.json())



        return response_200

    if response.status_code == 403:
        response_403 = ProblemOut.from_dict(response.json())



        return response_403

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut]:
    """ Create Sandbox

     Provision (or fetch) the sandbox sibling and mint a ubb_test_ API key.

    The RAW key is returned exactly once per call (each POST mints a fresh
    key — that is also the rotation path). 403 from a sandbox key: sandboxes
    cannot nest.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,

) -> ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut | None:
    """ Create Sandbox

     Provision (or fetch) the sandbox sibling and mint a ubb_test_ API key.

    The RAW key is returned exactly once per call (each POST mints a fresh
    key — that is also the rotation path). 403 from a sandbox key: sandboxes
    cannot nest.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut]:
    """ Create Sandbox

     Provision (or fetch) the sandbox sibling and mint a ubb_test_ API key.

    The RAW key is returned exactly once per call (each POST mints a fresh
    key — that is also the rotation path). 403 from a sandbox key: sandboxes
    cannot nest.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        
    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,

) -> ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut | None:
    """ Create Sandbox

     Provision (or fetch) the sandbox sibling and mint a ubb_test_ API key.

    The RAW key is returned exactly once per call (each POST mints a fresh
    key — that is also the rotation path). 403 from a sandbox key: sandboxes
    cannot nest.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsCreateSandboxResponse | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
