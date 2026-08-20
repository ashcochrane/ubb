from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.projected_adjustment_out import ProjectedAdjustmentOut
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime



def _get_kwargs(
    *,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_selected_from: None | str | Unset
    if isinstance(selected_from, Unset):
        json_selected_from = UNSET
    elif isinstance(selected_from, datetime.datetime):
        json_selected_from = selected_from.isoformat()
    else:
        json_selected_from = selected_from
    params["selected_from"] = json_selected_from

    json_selected_to: None | str | Unset
    if isinstance(selected_to, Unset):
        json_selected_to = UNSET
    elif isinstance(selected_to, datetime.datetime):
        json_selected_to = selected_to.isoformat()
    else:
        json_selected_to = selected_to
    params["selected_to"] = json_selected_to

    json_selected_customer_id: None | str | Unset
    if isinstance(selected_customer_id, Unset):
        json_selected_customer_id = UNSET
    elif isinstance(selected_customer_id, UUID):
        json_selected_customer_id = str(selected_customer_id)
    else:
        json_selected_customer_id = selected_customer_id
    params["selected_customer_id"] = json_selected_customer_id

    params["selected_event_type"] = selected_event_type


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/pricing/projected-adjustment",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | ProjectedAdjustmentOut | None:
    if response.status_code == 200:
        response_200 = ProjectedAdjustmentOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | ProjectedAdjustmentOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',

) -> Response[ProblemOut | ProjectedAdjustmentOut]:
    """ Get Projected Adjustment

     What recovering this filter would be worth, per customer.

    A projection and not an instruction: reading it moves no money, creates no
    invoice, credit note, charge or refund, and UBB will not bill your customer
    for it. Deciding to go back to a customer stays yours, and you act on it
    through the billing path you already use.

    Each posting is re-resolved at its own effective instant, so nothing is
    repriced against today's rules. `usage_event_ids` names the postings behind
    each figure; each one's Pricing Receipt is at
    GET /metering/usage/{event_id}.

    One pass examines a bounded number of postings. `postings_not_examined`
    says how many the filter matched beyond it — narrow the date range to reach
    those — and `unpriced_event_count` says how many examined postings still
    resolve to no price. Both make the figures a floor.

    The filter is the Resolution Run's: a half-open date range, a customer and
    an Event Type, in any combination. A customer this tenant does not have is
    a 404; a stated window longer than 366 days is a `validation_error`.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ProjectedAdjustmentOut]
     """


    kwargs = _get_kwargs(
        selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',

) -> ProblemOut | ProjectedAdjustmentOut | None:
    """ Get Projected Adjustment

     What recovering this filter would be worth, per customer.

    A projection and not an instruction: reading it moves no money, creates no
    invoice, credit note, charge or refund, and UBB will not bill your customer
    for it. Deciding to go back to a customer stays yours, and you act on it
    through the billing path you already use.

    Each posting is re-resolved at its own effective instant, so nothing is
    repriced against today's rules. `usage_event_ids` names the postings behind
    each figure; each one's Pricing Receipt is at
    GET /metering/usage/{event_id}.

    One pass examines a bounded number of postings. `postings_not_examined`
    says how many the filter matched beyond it — narrow the date range to reach
    those — and `unpriced_event_count` says how many examined postings still
    resolve to no price. Both make the figures a floor.

    The filter is the Resolution Run's: a half-open date range, a customer and
    an Event Type, in any combination. A customer this tenant does not have is
    a 404; a stated window longer than 366 days is a `validation_error`.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ProjectedAdjustmentOut
     """


    return sync_detailed(
        client=client,
selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',

) -> Response[ProblemOut | ProjectedAdjustmentOut]:
    """ Get Projected Adjustment

     What recovering this filter would be worth, per customer.

    A projection and not an instruction: reading it moves no money, creates no
    invoice, credit note, charge or refund, and UBB will not bill your customer
    for it. Deciding to go back to a customer stays yours, and you act on it
    through the billing path you already use.

    Each posting is re-resolved at its own effective instant, so nothing is
    repriced against today's rules. `usage_event_ids` names the postings behind
    each figure; each one's Pricing Receipt is at
    GET /metering/usage/{event_id}.

    One pass examines a bounded number of postings. `postings_not_examined`
    says how many the filter matched beyond it — narrow the date range to reach
    those — and `unpriced_event_count` says how many examined postings still
    resolve to no price. Both make the figures a floor.

    The filter is the Resolution Run's: a half-open date range, a customer and
    an Event Type, in any combination. A customer this tenant does not have is
    a 404; a stated window longer than 366 days is a `validation_error`.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ProjectedAdjustmentOut]
     """


    kwargs = _get_kwargs(
        selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    selected_from: datetime.datetime | None | Unset = UNSET,
    selected_to: datetime.datetime | None | Unset = UNSET,
    selected_customer_id: None | Unset | UUID = UNSET,
    selected_event_type: str | Unset = '',

) -> ProblemOut | ProjectedAdjustmentOut | None:
    """ Get Projected Adjustment

     What recovering this filter would be worth, per customer.

    A projection and not an instruction: reading it moves no money, creates no
    invoice, credit note, charge or refund, and UBB will not bill your customer
    for it. Deciding to go back to a customer stays yours, and you act on it
    through the billing path you already use.

    Each posting is re-resolved at its own effective instant, so nothing is
    repriced against today's rules. `usage_event_ids` names the postings behind
    each figure; each one's Pricing Receipt is at
    GET /metering/usage/{event_id}.

    One pass examines a bounded number of postings. `postings_not_examined`
    says how many the filter matched beyond it — narrow the date range to reach
    those — and `unpriced_event_count` says how many examined postings still
    resolve to no price. Both make the figures a floor.

    The filter is the Resolution Run's: a half-open date range, a customer and
    an Event Type, in any combination. A customer this tenant does not have is
    a 404; a stated window longer than 366 days is a `validation_error`.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ProjectedAdjustmentOut
     """


    return (await asyncio_detailed(
        client=client,
selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,

    )).parsed
