from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.status_response import StatusResponse
from typing import cast



def _get_kwargs(
    referral_id: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/referrals/referrals/{referral_id}".format(referral_id=quote(str(referral_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> StatusResponse | None:
    if response.status_code == 200:
        response_200 = StatusResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[StatusResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    referral_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[StatusResponse]:
    """ Revoke Referral

    Args:
        referral_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[StatusResponse]
     """


    kwargs = _get_kwargs(
        referral_id=referral_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    referral_id: str,
    *,
    client: AuthenticatedClient,

) -> StatusResponse | None:
    """ Revoke Referral

    Args:
        referral_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        StatusResponse
     """


    return sync_detailed(
        referral_id=referral_id,
client=client,

    ).parsed

async def asyncio_detailed(
    referral_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[StatusResponse]:
    """ Revoke Referral

    Args:
        referral_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[StatusResponse]
     """


    kwargs = _get_kwargs(
        referral_id=referral_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    referral_id: str,
    *,
    client: AuthenticatedClient,

) -> StatusResponse | None:
    """ Revoke Referral

    Args:
        referral_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        StatusResponse
     """


    return (await asyncio_detailed(
        referral_id=referral_id,
client=client,

    )).parsed
