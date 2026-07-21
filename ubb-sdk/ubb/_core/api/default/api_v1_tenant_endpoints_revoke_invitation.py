from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_tenant_endpoints_revoke_invitation_response import ApiV1TenantEndpointsRevokeInvitationResponse
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    invitation_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/tenant/invitations/{invitation_id}".format(invitation_id=quote(str(invitation_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1TenantEndpointsRevokeInvitationResponse.from_dict(response.json())



        return response_200

    if response.status_code == 403:
        response_403 = ProblemOut.from_dict(response.json())



        return response_403

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    invitation_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut]:
    """ Revoke Invitation

     Revoke a still-pending invitation (Admin only). Idempotent on an
    already-revoked invite; 409 if it was already accepted (removing an active
    member is member removal — DELETE /members/{id}).

    Args:
        invitation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        invitation_id=invitation_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    invitation_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut | None:
    """ Revoke Invitation

     Revoke a still-pending invitation (Admin only). Idempotent on an
    already-revoked invite; 409 if it was already accepted (removing an active
    member is member removal — DELETE /members/{id}).

    Args:
        invitation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut
     """


    return sync_detailed(
        invitation_id=invitation_id,
client=client,

    ).parsed

async def asyncio_detailed(
    invitation_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut]:
    """ Revoke Invitation

     Revoke a still-pending invitation (Admin only). Idempotent on an
    already-revoked invite; 409 if it was already accepted (removing an active
    member is member removal — DELETE /members/{id}).

    Args:
        invitation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        invitation_id=invitation_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    invitation_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut | None:
    """ Revoke Invitation

     Revoke a still-pending invitation (Admin only). Idempotent on an
    already-revoked invite; 409 if it was already accepted (removing an active
    member is member removal — DELETE /members/{id}).

    Args:
        invitation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsRevokeInvitationResponse | ProblemOut
     """


    return (await asyncio_detailed(
        invitation_id=invitation_id,
client=client,

    )).parsed
