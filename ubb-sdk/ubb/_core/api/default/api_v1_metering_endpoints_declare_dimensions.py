from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.dimension_registry_in import DimensionRegistryIn
from ...models.dimension_registry_out import DimensionRegistryOut
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    *,
    body: DimensionRegistryIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/metering/dimensions",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> DimensionRegistryOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = DimensionRegistryOut.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[DimensionRegistryOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: DimensionRegistryIn,

) -> Response[DimensionRegistryOut | ProblemOut]:
    """ Declare Dimensions

     Declare this tenant's slicing axes — the ONE vocabulary used by both
    analytics grouping and rate selection (design D1). Idempotent: re-PUTting
    an identical declaration is a no-op. `slot` and `scope` are immutable once
    bound and `max_cardinality` may only be raised (D8).

    Args:
        body (DimensionRegistryIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DimensionRegistryOut | ProblemOut]
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
    body: DimensionRegistryIn,

) -> DimensionRegistryOut | ProblemOut | None:
    """ Declare Dimensions

     Declare this tenant's slicing axes — the ONE vocabulary used by both
    analytics grouping and rate selection (design D1). Idempotent: re-PUTting
    an identical declaration is a no-op. `slot` and `scope` are immutable once
    bound and `max_cardinality` may only be raised (D8).

    Args:
        body (DimensionRegistryIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DimensionRegistryOut | ProblemOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: DimensionRegistryIn,

) -> Response[DimensionRegistryOut | ProblemOut]:
    """ Declare Dimensions

     Declare this tenant's slicing axes — the ONE vocabulary used by both
    analytics grouping and rate selection (design D1). Idempotent: re-PUTting
    an identical declaration is a no-op. `slot` and `scope` are immutable once
    bound and `max_cardinality` may only be raised (D8).

    Args:
        body (DimensionRegistryIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DimensionRegistryOut | ProblemOut]
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
    body: DimensionRegistryIn,

) -> DimensionRegistryOut | ProblemOut | None:
    """ Declare Dimensions

     Declare this tenant's slicing axes — the ONE vocabulary used by both
    analytics grouping and rate selection (design D1). Idempotent: re-PUTting
    an identical declaration is a no-op. `slot` and `scope` are immutable once
    bound and `max_cardinality` may only be raised (D8).

    Args:
        body (DimensionRegistryIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DimensionRegistryOut | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
