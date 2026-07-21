from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_metering_endpoints_assign_book_response import ApiV1MeteringEndpointsAssignBookResponse
from ...models.assign_in import AssignIn
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,
    *,
    body: AssignIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/customers/{customer_id}/rate-card".format(customer_id=quote(str(customer_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1MeteringEndpointsAssignBookResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1MeteringEndpointsAssignBookResponse.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1MeteringEndpointsAssignBookResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: AssignIn,

) -> Response[ApiV1MeteringEndpointsAssignBookResponse | ProblemOut]:
    """ Assign Book

     Assign a PRICE book to a customer (one per customer per currency).
    Resolution consults the assigned book before the per-provider default.

    Args:
        customer_id (UUID):
        body (AssignIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1MeteringEndpointsAssignBookResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: AssignIn,

) -> ApiV1MeteringEndpointsAssignBookResponse | ProblemOut | None:
    """ Assign Book

     Assign a PRICE book to a customer (one per customer per currency).
    Resolution consults the assigned book before the per-provider default.

    Args:
        customer_id (UUID):
        body (AssignIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1MeteringEndpointsAssignBookResponse | ProblemOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: AssignIn,

) -> Response[ApiV1MeteringEndpointsAssignBookResponse | ProblemOut]:
    """ Assign Book

     Assign a PRICE book to a customer (one per customer per currency).
    Resolution consults the assigned book before the per-provider default.

    Args:
        customer_id (UUID):
        body (AssignIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1MeteringEndpointsAssignBookResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: AssignIn,

) -> ApiV1MeteringEndpointsAssignBookResponse | ProblemOut | None:
    """ Assign Book

     Assign a PRICE book to a customer (one per customer per currency).
    Resolution consults the assigned book before the per-provider default.

    Args:
        customer_id (UUID):
        body (AssignIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1MeteringEndpointsAssignBookResponse | ProblemOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
body=body,

    )).parsed
