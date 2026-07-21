from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.past_limit_report_response import PastLimitReportResponse
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    customer_id: str,
    *,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_since: None | str | Unset
    if isinstance(since, Unset):
        json_since = UNSET
    elif isinstance(since, datetime.datetime):
        json_since = since.isoformat()
    else:
        json_since = since
    params["since"] = json_since

    json_until: None | str | Unset
    if isinstance(until, Unset):
        json_until = UNSET
    elif isinstance(until, datetime.datetime):
        json_until = until.isoformat()
    else:
        json_until = until
    params["until"] = json_until


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/customers/{customer_id}/past-limit-report".format(customer_id=quote(str(customer_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> PastLimitReportResponse | None:
    if response.status_code == 200:
        response_200 = PastLimitReportResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[PastLimitReportResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,

) -> Response[PastLimitReportResponse]:
    """ Past Limit Report

     The past-limit report (#41, spec §I): per-customer episodes — each
    with the tripping limit, tripped-at, resume time (if any), itemized
    events, and totals per limit in both denominations. Soft-floor episodes
    appear as crossed/cleared marker rows with no itemized events. since/
    until (ISO datetimes; naive = UTC) window episodes by tripped_at and
    itemized events by effective_at.

    Args:
        customer_id (str):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PastLimitReportResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
since=since,
until=until,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,

) -> PastLimitReportResponse | None:
    """ Past Limit Report

     The past-limit report (#41, spec §I): per-customer episodes — each
    with the tripping limit, tripped-at, resume time (if any), itemized
    events, and totals per limit in both denominations. Soft-floor episodes
    appear as crossed/cleared marker rows with no itemized events. since/
    until (ISO datetimes; naive = UTC) window episodes by tripped_at and
    itemized events by effective_at.

    Args:
        customer_id (str):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PastLimitReportResponse
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
since=since,
until=until,

    ).parsed

async def asyncio_detailed(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,

) -> Response[PastLimitReportResponse]:
    """ Past Limit Report

     The past-limit report (#41, spec §I): per-customer episodes — each
    with the tripping limit, tripped-at, resume time (if any), itemized
    events, and totals per limit in both denominations. Soft-floor episodes
    appear as crossed/cleared marker rows with no itemized events. since/
    until (ISO datetimes; naive = UTC) window episodes by tripped_at and
    itemized events by effective_at.

    Args:
        customer_id (str):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PastLimitReportResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
since=since,
until=until,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,

) -> PastLimitReportResponse | None:
    """ Past Limit Report

     The past-limit report (#41, spec §I): per-customer episodes — each
    with the tripping limit, tripped-at, resume time (if any), itemized
    events, and totals per limit in both denominations. Soft-floor episodes
    appear as crossed/cleared marker rows with no itemized events. since/
    until (ISO datetimes; naive = UTC) window episodes by tripped_at and
    itemized events by effective_at.

    Args:
        customer_id (str):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PastLimitReportResponse
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
since=since,
until=until,

    )).parsed
