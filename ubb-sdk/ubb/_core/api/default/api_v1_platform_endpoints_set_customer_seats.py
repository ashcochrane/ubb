from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_platform_endpoints_set_customer_seats_response import ApiV1PlatformEndpointsSetCustomerSeatsResponse
from ...models.problem_out import ProblemOut
from ...models.seats_in import SeatsIn
from typing import cast



def _get_kwargs(
    external_id: str,
    *,
    body: SeatsIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/platform/customers/{external_id}/seats".format(external_id=quote(str(external_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1PlatformEndpointsSetCustomerSeatsResponse.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    external_id: str,
    *,
    client: AuthenticatedClient,
    body: SeatsIn,

) -> Response[ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut]:
    """ Set Customer Seats

    Args:
        external_id (str):
        body (SeatsIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        external_id=external_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    external_id: str,
    *,
    client: AuthenticatedClient,
    body: SeatsIn,

) -> ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut | None:
    """ Set Customer Seats

    Args:
        external_id (str):
        body (SeatsIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut
     """


    return sync_detailed(
        external_id=external_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    external_id: str,
    *,
    client: AuthenticatedClient,
    body: SeatsIn,

) -> Response[ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut]:
    """ Set Customer Seats

    Args:
        external_id (str):
        body (SeatsIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        external_id=external_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    external_id: str,
    *,
    client: AuthenticatedClient,
    body: SeatsIn,

) -> ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut | None:
    """ Set Customer Seats

    Args:
        external_id (str):
        body (SeatsIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlatformEndpointsSetCustomerSeatsResponse | ProblemOut
     """


    return (await asyncio_detailed(
        external_id=external_id,
client=client,
body=body,

    )).parsed
