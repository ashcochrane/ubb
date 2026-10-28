from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.analytics_earnings_out import AnalyticsEarningsOut
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    period_start: None | str | Unset = UNSET,
    period_end: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_period_start: None | str | Unset
    if isinstance(period_start, Unset):
        json_period_start = UNSET
    else:
        json_period_start = period_start
    params["period_start"] = json_period_start

    json_period_end: None | str | Unset
    if isinstance(period_end, Unset):
        json_period_end = UNSET
    else:
        json_period_end = period_end
    params["period_end"] = json_period_end


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/referrals/analytics/earnings",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> AnalyticsEarningsOut | None:
    if response.status_code == 200:
        response_200 = AnalyticsEarningsOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[AnalyticsEarningsOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    period_start: None | str | Unset = UNSET,
    period_end: None | str | Unset = UNSET,

) -> Response[AnalyticsEarningsOut]:
    """ Analytics Earnings

     What each referrer earned in the window, from the reconciliation ledger:
    a ledger period counts where it overlaps the window.

    **The window.** `period_start` and `period_end` are calendar dates in UTC, and both are inclusive:
    the window runs from the start of `period_start` to the end of `period_end`. Send `period_start`
    alone and the window runs to today; send `period_end` alone and it starts on the first day of that
    date's month; send neither and it is the current UTC month to date. A supplied date is never
    ignored. One request spans at most 366 calendar dates, and `period_start` may not fall after
    `period_end`; either is refused with `validation_error`. Longer retained history is read through
    consecutive, non-overlapping windows: the next window starts on the calendar day after the previous
    window's `period_end`.

    Args:
        period_start (None | str | Unset): The first calendar date (UTC) in the window, inclusive.
        period_end (None | str | Unset): The last calendar date (UTC) in the window, inclusive.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AnalyticsEarningsOut]
     """


    kwargs = _get_kwargs(
        period_start=period_start,
period_end=period_end,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    period_start: None | str | Unset = UNSET,
    period_end: None | str | Unset = UNSET,

) -> AnalyticsEarningsOut | None:
    """ Analytics Earnings

     What each referrer earned in the window, from the reconciliation ledger:
    a ledger period counts where it overlaps the window.

    **The window.** `period_start` and `period_end` are calendar dates in UTC, and both are inclusive:
    the window runs from the start of `period_start` to the end of `period_end`. Send `period_start`
    alone and the window runs to today; send `period_end` alone and it starts on the first day of that
    date's month; send neither and it is the current UTC month to date. A supplied date is never
    ignored. One request spans at most 366 calendar dates, and `period_start` may not fall after
    `period_end`; either is refused with `validation_error`. Longer retained history is read through
    consecutive, non-overlapping windows: the next window starts on the calendar day after the previous
    window's `period_end`.

    Args:
        period_start (None | str | Unset): The first calendar date (UTC) in the window, inclusive.
        period_end (None | str | Unset): The last calendar date (UTC) in the window, inclusive.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AnalyticsEarningsOut
     """


    return sync_detailed(
        client=client,
period_start=period_start,
period_end=period_end,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    period_start: None | str | Unset = UNSET,
    period_end: None | str | Unset = UNSET,

) -> Response[AnalyticsEarningsOut]:
    """ Analytics Earnings

     What each referrer earned in the window, from the reconciliation ledger:
    a ledger period counts where it overlaps the window.

    **The window.** `period_start` and `period_end` are calendar dates in UTC, and both are inclusive:
    the window runs from the start of `period_start` to the end of `period_end`. Send `period_start`
    alone and the window runs to today; send `period_end` alone and it starts on the first day of that
    date's month; send neither and it is the current UTC month to date. A supplied date is never
    ignored. One request spans at most 366 calendar dates, and `period_start` may not fall after
    `period_end`; either is refused with `validation_error`. Longer retained history is read through
    consecutive, non-overlapping windows: the next window starts on the calendar day after the previous
    window's `period_end`.

    Args:
        period_start (None | str | Unset): The first calendar date (UTC) in the window, inclusive.
        period_end (None | str | Unset): The last calendar date (UTC) in the window, inclusive.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AnalyticsEarningsOut]
     """


    kwargs = _get_kwargs(
        period_start=period_start,
period_end=period_end,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    period_start: None | str | Unset = UNSET,
    period_end: None | str | Unset = UNSET,

) -> AnalyticsEarningsOut | None:
    """ Analytics Earnings

     What each referrer earned in the window, from the reconciliation ledger:
    a ledger period counts where it overlaps the window.

    **The window.** `period_start` and `period_end` are calendar dates in UTC, and both are inclusive:
    the window runs from the start of `period_start` to the end of `period_end`. Send `period_start`
    alone and the window runs to today; send `period_end` alone and it starts on the first day of that
    date's month; send neither and it is the current UTC month to date. A supplied date is never
    ignored. One request spans at most 366 calendar dates, and `period_start` may not fall after
    `period_end`; either is refused with `validation_error`. Longer retained history is read through
    consecutive, non-overlapping windows: the next window starts on the calendar day after the previous
    window's `period_end`.

    Args:
        period_start (None | str | Unset): The first calendar date (UTC) in the window, inclusive.
        period_end (None | str | Unset): The last calendar date (UTC) in the window, inclusive.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AnalyticsEarningsOut
     """


    return (await asyncio_detailed(
        client=client,
period_start=period_start,
period_end=period_end,

    )).parsed
