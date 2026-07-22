from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.unprofitable_out import UnprofitableOut
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    period_start: datetime.date | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_period_start: None | str | Unset
    if isinstance(period_start, Unset):
        json_period_start = UNSET
    elif isinstance(period_start, datetime.date):
        json_period_start = period_start.isoformat()
    else:
        json_period_start = period_start
    params["period_start"] = json_period_start


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/margin/unprofitable",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> UnprofitableOut | None:
    if response.status_code == 200:
        response_200 = UnprofitableOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[UnprofitableOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    period_start: datetime.date | None | Unset = UNSET,

) -> Response[UnprofitableOut]:
    """ Margin Unprofitable

    Args:
        period_start (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UnprofitableOut]
     """


    kwargs = _get_kwargs(
        period_start=period_start,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    period_start: datetime.date | None | Unset = UNSET,

) -> UnprofitableOut | None:
    """ Margin Unprofitable

    Args:
        period_start (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UnprofitableOut
     """


    return sync_detailed(
        client=client,
period_start=period_start,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    period_start: datetime.date | None | Unset = UNSET,

) -> Response[UnprofitableOut]:
    """ Margin Unprofitable

    Args:
        period_start (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UnprofitableOut]
     """


    kwargs = _get_kwargs(
        period_start=period_start,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    period_start: datetime.date | None | Unset = UNSET,

) -> UnprofitableOut | None:
    """ Margin Unprofitable

    Args:
        period_start (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UnprofitableOut
     """


    return (await asyncio_detailed(
        client=client,
period_start=period_start,

    )).parsed
