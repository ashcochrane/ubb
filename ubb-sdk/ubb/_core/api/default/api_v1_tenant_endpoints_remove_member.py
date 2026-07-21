from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_tenant_endpoints_remove_member_response import ApiV1TenantEndpointsRemoveMemberResponse
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    member_id: UUID,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/tenant/members/{member_id}".format(member_id=quote(str(member_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1TenantEndpointsRemoveMemberResponse.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    member_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut]:
    """ Remove Member

     Remove a member (Admin only). 404 if unknown; 409 when removing the
    tenant's last active Admin (the last-Admin guard). The removed principal
    401s on its next request and its email is free to be re-invited.

    Args:
        member_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        member_id=member_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    member_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut | None:
    """ Remove Member

     Remove a member (Admin only). 404 if unknown; 409 when removing the
    tenant's last active Admin (the last-Admin guard). The removed principal
    401s on its next request and its email is free to be re-invited.

    Args:
        member_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut
     """


    return sync_detailed(
        member_id=member_id,
client=client,

    ).parsed

async def asyncio_detailed(
    member_id: UUID,
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut]:
    """ Remove Member

     Remove a member (Admin only). 404 if unknown; 409 when removing the
    tenant's last active Admin (the last-Admin guard). The removed principal
    401s on its next request and its email is free to be re-invited.

    Args:
        member_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        member_id=member_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    member_id: UUID,
    *,
    client: AuthenticatedClient,

) -> ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut | None:
    """ Remove Member

     Remove a member (Admin only). 404 if unknown; 409 when removing the
    tenant's last active Admin (the last-Admin guard). The removed principal
    401s on its next request and its email is free to be re-invited.

    Args:
        member_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1TenantEndpointsRemoveMemberResponse | ProblemOut
     """


    return (await asyncio_detailed(
        member_id=member_id,
client=client,

    )).parsed
