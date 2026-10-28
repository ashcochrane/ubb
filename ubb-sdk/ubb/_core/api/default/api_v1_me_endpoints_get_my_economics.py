from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.me_economics_out import MeEconomicsOut
from ...models.problem_out import ProblemOut
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

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
        "url": "/api/v1/me/economics",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> MeEconomicsOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = MeEconomicsOut.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[MeEconomicsOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> Response[MeEconomicsOut | ProblemOut]:
    """ Get My Economics

     What your own usage earned and how many events it recorded.

    Scoped to the customer the widget token names, and to nothing else: there
    is no customer parameter, and a business's answer is the business's own
    usage, without its seats'. Revenue is stated under the basis the answer
    names, and where UBB cannot state a figure the amount is null, never zero.

    **The window.** `start_date` and `end_date` are calendar dates in UTC, and both are inclusive: the
    window runs from the start of `start_date` to the end of `end_date`. Send `start_date` alone and the
    window runs to today; send `end_date` alone and it starts on the first day of that date's month;
    send neither and it is the current UTC month to date. A supplied date is never ignored. One request
    spans at most 366 calendar dates, and `start_date` may not fall after `end_date`; either is refused
    with `validation_error`. Longer retained history is read through consecutive, non-overlapping
    windows: the next window starts on the calendar day after the previous window's `end_date`.

    Args:
        start_date (datetime.date | None | Unset): The first calendar date (UTC) in the window,
            inclusive.
        end_date (datetime.date | None | Unset): The last calendar date (UTC) in the window,
            inclusive.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MeEconomicsOut | ProblemOut]
     """


    kwargs = _get_kwargs(
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
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> MeEconomicsOut | ProblemOut | None:
    """ Get My Economics

     What your own usage earned and how many events it recorded.

    Scoped to the customer the widget token names, and to nothing else: there
    is no customer parameter, and a business's answer is the business's own
    usage, without its seats'. Revenue is stated under the basis the answer
    names, and where UBB cannot state a figure the amount is null, never zero.

    **The window.** `start_date` and `end_date` are calendar dates in UTC, and both are inclusive: the
    window runs from the start of `start_date` to the end of `end_date`. Send `start_date` alone and the
    window runs to today; send `end_date` alone and it starts on the first day of that date's month;
    send neither and it is the current UTC month to date. A supplied date is never ignored. One request
    spans at most 366 calendar dates, and `start_date` may not fall after `end_date`; either is refused
    with `validation_error`. Longer retained history is read through consecutive, non-overlapping
    windows: the next window starts on the calendar day after the previous window's `end_date`.

    Args:
        start_date (datetime.date | None | Unset): The first calendar date (UTC) in the window,
            inclusive.
        end_date (datetime.date | None | Unset): The last calendar date (UTC) in the window,
            inclusive.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MeEconomicsOut | ProblemOut
     """


    return sync_detailed(
        client=client,
start_date=start_date,
end_date=end_date,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> Response[MeEconomicsOut | ProblemOut]:
    """ Get My Economics

     What your own usage earned and how many events it recorded.

    Scoped to the customer the widget token names, and to nothing else: there
    is no customer parameter, and a business's answer is the business's own
    usage, without its seats'. Revenue is stated under the basis the answer
    names, and where UBB cannot state a figure the amount is null, never zero.

    **The window.** `start_date` and `end_date` are calendar dates in UTC, and both are inclusive: the
    window runs from the start of `start_date` to the end of `end_date`. Send `start_date` alone and the
    window runs to today; send `end_date` alone and it starts on the first day of that date's month;
    send neither and it is the current UTC month to date. A supplied date is never ignored. One request
    spans at most 366 calendar dates, and `start_date` may not fall after `end_date`; either is refused
    with `validation_error`. Longer retained history is read through consecutive, non-overlapping
    windows: the next window starts on the calendar day after the previous window's `end_date`.

    Args:
        start_date (datetime.date | None | Unset): The first calendar date (UTC) in the window,
            inclusive.
        end_date (datetime.date | None | Unset): The last calendar date (UTC) in the window,
            inclusive.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MeEconomicsOut | ProblemOut]
     """


    kwargs = _get_kwargs(
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
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,

) -> MeEconomicsOut | ProblemOut | None:
    """ Get My Economics

     What your own usage earned and how many events it recorded.

    Scoped to the customer the widget token names, and to nothing else: there
    is no customer parameter, and a business's answer is the business's own
    usage, without its seats'. Revenue is stated under the basis the answer
    names, and where UBB cannot state a figure the amount is null, never zero.

    **The window.** `start_date` and `end_date` are calendar dates in UTC, and both are inclusive: the
    window runs from the start of `start_date` to the end of `end_date`. Send `start_date` alone and the
    window runs to today; send `end_date` alone and it starts on the first day of that date's month;
    send neither and it is the current UTC month to date. A supplied date is never ignored. One request
    spans at most 366 calendar dates, and `start_date` may not fall after `end_date`; either is refused
    with `validation_error`. Longer retained history is read through consecutive, non-overlapping
    windows: the next window starts on the calendar day after the previous window's `end_date`.

    Args:
        start_date (datetime.date | None | Unset): The first calendar date (UTC) in the window,
            inclusive.
        end_date (datetime.date | None | Unset): The last calendar date (UTC) in the window,
            inclusive.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MeEconomicsOut | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
start_date=start_date,
end_date=end_date,

    )).parsed
