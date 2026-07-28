from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.dimension_values_out import DimensionValuesOut
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    key: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/dimensions/{key}/values".format(key=quote(str(key), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> DimensionValuesOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = DimensionValuesOut.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[DimensionValuesOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    key: str,
    *,
    client: AuthenticatedClient,

) -> Response[DimensionValuesOut | ProblemOut]:
    """ List Dimension Values

     Every value admitted for one dimension — the read model a dashboard
    filter dropdown needs. Bounded by the key's max_cardinality (D4).

    Args:
        key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DimensionValuesOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        key=key,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    key: str,
    *,
    client: AuthenticatedClient,

) -> DimensionValuesOut | ProblemOut | None:
    """ List Dimension Values

     Every value admitted for one dimension — the read model a dashboard
    filter dropdown needs. Bounded by the key's max_cardinality (D4).

    Args:
        key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DimensionValuesOut | ProblemOut
     """


    return sync_detailed(
        key=key,
client=client,

    ).parsed

async def asyncio_detailed(
    key: str,
    *,
    client: AuthenticatedClient,

) -> Response[DimensionValuesOut | ProblemOut]:
    """ List Dimension Values

     Every value admitted for one dimension — the read model a dashboard
    filter dropdown needs. Bounded by the key's max_cardinality (D4).

    Args:
        key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DimensionValuesOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        key=key,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    key: str,
    *,
    client: AuthenticatedClient,

) -> DimensionValuesOut | ProblemOut | None:
    """ List Dimension Values

     Every value admitted for one dimension — the read model a dashboard
    filter dropdown needs. Bounded by the key's max_cardinality (D4).

    Args:
        key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DimensionValuesOut | ProblemOut
     """


    return (await asyncio_detailed(
        key=key,
client=client,

    )).parsed
