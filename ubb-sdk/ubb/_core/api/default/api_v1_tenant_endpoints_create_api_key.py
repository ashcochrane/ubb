from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_key_create_in import ApiKeyCreateIn
from ...models.api_v1_tenant_endpoints_create_api_key_response import ApiV1TenantEndpointsCreateApiKeyResponse
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    *,
    body: ApiKeyCreateIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/tenant/api-keys",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut | None:
    if response.status_code == 201:
        response_201 = ApiV1TenantEndpointsCreateApiKeyResponse.from_dict(response.json())



        return response_201

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ApiKeyCreateIn,

) -> Response[ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut]:
    """ Create Api Key

     Mint a new API key. The RAW key is returned exactly once, here.

    is_test=True on a live key routes the mint to the tenant's sandbox
    sibling (TenantApiKey.create_key lazily provisions it, F4.4) — the new
    ubb_test_ key lives ON the sandbox tenant, so it appears in the sandbox's
    key list and is managed with a sandbox key; response tenant_id tells you
    where it landed. is_test=False on a sandbox key is a mode mismatch (422).

    Args:
        body (ApiKeyCreateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut]
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
    body: ApiKeyCreateIn,

) -> ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut | None:
    """ Create Api Key

     Mint a new API key. The RAW key is returned exactly once, here.

    is_test=True on a live key routes the mint to the tenant's sandbox
    sibling (TenantApiKey.create_key lazily provisions it, F4.4) — the new
    ubb_test_ key lives ON the sandbox tenant, so it appears in the sandbox's
    key list and is managed with a sandbox key; response tenant_id tells you
    where it landed. is_test=False on a sandbox key is a mode mismatch (422).

    Args:
        body (ApiKeyCreateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ApiKeyCreateIn,

) -> Response[ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut]:
    """ Create Api Key

     Mint a new API key. The RAW key is returned exactly once, here.

    is_test=True on a live key routes the mint to the tenant's sandbox
    sibling (TenantApiKey.create_key lazily provisions it, F4.4) — the new
    ubb_test_ key lives ON the sandbox tenant, so it appears in the sandbox's
    key list and is managed with a sandbox key; response tenant_id tells you
    where it landed. is_test=False on a sandbox key is a mode mismatch (422).

    Args:
        body (ApiKeyCreateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut]
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
    body: ApiKeyCreateIn,

) -> ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut | None:
    """ Create Api Key

     Mint a new API key. The RAW key is returned exactly once, here.

    is_test=True on a live key routes the mint to the tenant's sandbox
    sibling (TenantApiKey.create_key lazily provisions it, F4.4) — the new
    ubb_test_ key lives ON the sandbox tenant, so it appears in the sandbox's
    key list and is managed with a sandbox key; response tenant_id tells you
    where it landed. is_test=False on a sandbox key is a mode mismatch (422).

    Args:
        body (ApiKeyCreateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsCreateApiKeyResponse | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
