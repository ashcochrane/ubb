from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.member_out import MemberOut
from ...models.member_role_update_in import MemberRoleUpdateIn
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    member_id: UUID,
    *,
    body: MemberRoleUpdateIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v1/tenant/members/{member_id}".format(member_id=quote(str(member_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> MemberOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = MemberOut.from_dict(response.json())



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

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[MemberOut | ProblemOut]:
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
    body: MemberRoleUpdateIn,

) -> Response[MemberOut | ProblemOut]:
    """ Update Member Role

     Change a member's role (Admin only). 404 if unknown; 422 on an unknown
    role; 409 when the change would demote the tenant's last active Admin (the
    last-Admin guard — a tenant can never lock itself out).

    Args:
        member_id (UUID):
        body (MemberRoleUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MemberOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        member_id=member_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    member_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MemberRoleUpdateIn,

) -> MemberOut | ProblemOut | None:
    """ Update Member Role

     Change a member's role (Admin only). 404 if unknown; 422 on an unknown
    role; 409 when the change would demote the tenant's last active Admin (the
    last-Admin guard — a tenant can never lock itself out).

    Args:
        member_id (UUID):
        body (MemberRoleUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MemberOut | ProblemOut
     """


    return sync_detailed(
        member_id=member_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    member_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MemberRoleUpdateIn,

) -> Response[MemberOut | ProblemOut]:
    """ Update Member Role

     Change a member's role (Admin only). 404 if unknown; 422 on an unknown
    role; 409 when the change would demote the tenant's last active Admin (the
    last-Admin guard — a tenant can never lock itself out).

    Args:
        member_id (UUID):
        body (MemberRoleUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MemberOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        member_id=member_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    member_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MemberRoleUpdateIn,

) -> MemberOut | ProblemOut | None:
    """ Update Member Role

     Change a member's role (Admin only). 404 if unknown; 422 on an unknown
    role; 409 when the change would demote the tenant's last active Admin (the
    last-Admin guard — a tenant can never lock itself out).

    Args:
        member_id (UUID):
        body (MemberRoleUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MemberOut | ProblemOut
     """


    return (await asyncio_detailed(
        member_id=member_id,
client=client,
body=body,

    )).parsed
