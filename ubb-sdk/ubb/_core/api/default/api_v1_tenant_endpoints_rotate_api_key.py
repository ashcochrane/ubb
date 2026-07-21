from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_tenant_endpoints_rotate_api_key_response import ApiV1TenantEndpointsRotateApiKeyResponse
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    key_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/tenant/api-keys/{key_id}/rotate".format(key_id=quote(str(key_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1TenantEndpointsRotateApiKeyResponse.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    key_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut]:
    r""" Rotate Api Key

     Replace a key in one transaction: mint successor, deactivate old.

    The successor keeps the old label (+ \" (rotated)\") and the tenant's own
    mode (a sandbox tenant rotates to a ubb_test_ key, a live tenant to a
    ubb_live_ key — never re-routed). The old key 401s on its next request;
    the new RAW key is returned exactly once.

    Args:
        key_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        key_id=key_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    key_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut | None:
    r""" Rotate Api Key

     Replace a key in one transaction: mint successor, deactivate old.

    The successor keeps the old label (+ \" (rotated)\") and the tenant's own
    mode (a sandbox tenant rotates to a ubb_test_ key, a live tenant to a
    ubb_live_ key — never re-routed). The old key 401s on its next request;
    the new RAW key is returned exactly once.

    Args:
        key_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut
     """


    return sync_detailed(
        key_id=key_id,
client=client,

    ).parsed

async def asyncio_detailed(
    key_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut]:
    r""" Rotate Api Key

     Replace a key in one transaction: mint successor, deactivate old.

    The successor keeps the old label (+ \" (rotated)\") and the tenant's own
    mode (a sandbox tenant rotates to a ubb_test_ key, a live tenant to a
    ubb_live_ key — never re-routed). The old key 401s on its next request;
    the new RAW key is returned exactly once.

    Args:
        key_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        key_id=key_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    key_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut | None:
    r""" Rotate Api Key

     Replace a key in one transaction: mint successor, deactivate old.

    The successor keeps the old label (+ \" (rotated)\") and the tenant's own
    mode (a sandbox tenant rotates to a ubb_test_ key, a live tenant to a
    ubb_live_ key — never re-routed). The old key 401s on its next request;
    the new RAW key is returned exactly once.

    Args:
        key_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsRotateApiKeyResponse | ProblemOut
     """


    return (await asyncio_detailed(
        key_id=key_id,
client=client,

    )).parsed
