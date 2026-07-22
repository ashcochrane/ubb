from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.margin_by_dimension_out import MarginByDimensionOut
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    provider: int | None | Unset = UNSET,
    product: int | None | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_provider: int | None | Unset
    if isinstance(provider, Unset):
        json_provider = UNSET
    else:
        json_provider = provider
    params["provider"] = json_provider

    json_product: int | None | Unset
    if isinstance(product, Unset):
        json_product = UNSET
    else:
        json_product = product
    params["product"] = json_product

    json_tag_key: None | str | Unset
    if isinstance(tag_key, Unset):
        json_tag_key = UNSET
    else:
        json_tag_key = tag_key
    params["tag_key"] = json_tag_key

    json_start_date: None | str | Unset
    if isinstance(start_date, Unset):
        json_start_date = UNSET
    elif isinstance(start_date, datetime.date):
        json_start_date = start_date.isoformat()
    else:
        json_start_date = start_date
    params["start_date"] = json_start_date

    json_end_date: None | str | Unset
    if isinstance(end_date, Unset):
        json_end_date = UNSET
    elif isinstance(end_date, datetime.date):
        json_end_date = end_date.isoformat()
    else:
        json_end_date = end_date
    params["end_date"] = json_end_date


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/margin/by-dimension",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> MarginByDimensionOut | None:
    if response.status_code == 200:
        response_200 = MarginByDimensionOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[MarginByDimensionOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    provider: int | None | Unset = UNSET,
    product: int | None | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> Response[MarginByDimensionOut]:
    """ Margin By Dimension

    Args:
        provider (int | None | Unset):
        product (int | None | Unset):
        tag_key (None | str | Unset):
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MarginByDimensionOut]
     """


    kwargs = _get_kwargs(
        provider=provider,
product=product,
tag_key=tag_key,
start_date=start_date,
end_date=end_date,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    provider: int | None | Unset = UNSET,
    product: int | None | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> MarginByDimensionOut | None:
    """ Margin By Dimension

    Args:
        provider (int | None | Unset):
        product (int | None | Unset):
        tag_key (None | str | Unset):
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MarginByDimensionOut
     """


    return sync_detailed(
        client=client,
provider=provider,
product=product,
tag_key=tag_key,
start_date=start_date,
end_date=end_date,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    provider: int | None | Unset = UNSET,
    product: int | None | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> Response[MarginByDimensionOut]:
    """ Margin By Dimension

    Args:
        provider (int | None | Unset):
        product (int | None | Unset):
        tag_key (None | str | Unset):
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MarginByDimensionOut]
     """


    kwargs = _get_kwargs(
        provider=provider,
product=product,
tag_key=tag_key,
start_date=start_date,
end_date=end_date,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    provider: int | None | Unset = UNSET,
    product: int | None | Unset = UNSET,
    tag_key: None | str | Unset = UNSET,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> MarginByDimensionOut | None:
    """ Margin By Dimension

    Args:
        provider (int | None | Unset):
        product (int | None | Unset):
        tag_key (None | str | Unset):
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MarginByDimensionOut
     """


    return (await asyncio_detailed(
        client=client,
provider=provider,
product=product,
tag_key=tag_key,
start_date=start_date,
end_date=end_date,

    )).parsed
