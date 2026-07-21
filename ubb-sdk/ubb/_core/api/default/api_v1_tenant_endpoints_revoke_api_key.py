from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_tenant_endpoints_revoke_api_key_response import ApiV1TenantEndpointsRevokeApiKeyResponse
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    key_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/tenant/api-keys/{key_id}".format(key_id=quote(str(key_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1TenantEndpointsRevokeApiKeyResponse.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if response.status_code == 409:
        response_409 = ProblemOut.from_dict(response.json())



        return response_409

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut]:
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

) -> Response[ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut]:
    """ Revoke Api Key

     Soft-revoke a key (is_active=False). Idempotent on an inactive key.

    Lockout guard: revoking THIS tenant's last active key is refused with 409
    — with zero active keys the tenant could never call this API again to
    mint a replacement (rotate instead). All the tenant's key rows are locked
    in one deterministic-order query so two concurrent revokes cannot race
    past the guard together.

    Args:
        key_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut]
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

) -> ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut | None:
    """ Revoke Api Key

     Soft-revoke a key (is_active=False). Idempotent on an inactive key.

    Lockout guard: revoking THIS tenant's last active key is refused with 409
    — with zero active keys the tenant could never call this API again to
    mint a replacement (rotate instead). All the tenant's key rows are locked
    in one deterministic-order query so two concurrent revokes cannot race
    past the guard together.

    Args:
        key_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut
     """


    return sync_detailed(
        key_id=key_id,
client=client,

    ).parsed

async def asyncio_detailed(
    key_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut]:
    """ Revoke Api Key

     Soft-revoke a key (is_active=False). Idempotent on an inactive key.

    Lockout guard: revoking THIS tenant's last active key is refused with 409
    — with zero active keys the tenant could never call this API again to
    mint a replacement (rotate instead). All the tenant's key rows are locked
    in one deterministic-order query so two concurrent revokes cannot race
    past the guard together.

    Args:
        key_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut]
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

) -> ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut | None:
    """ Revoke Api Key

     Soft-revoke a key (is_active=False). Idempotent on an inactive key.

    Lockout guard: revoking THIS tenant's last active key is refused with 409
    — with zero active keys the tenant could never call this API again to
    mint a replacement (rotate instead). All the tenant's key rows are locked
    in one deterministic-order query so two concurrent revokes cannot race
    past the guard together.

    Args:
        key_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsRevokeApiKeyResponse | ProblemOut
     """


    return (await asyncio_detailed(
        key_id=key_id,
client=client,

    )).parsed
