from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.waived_loss_out import WaivedLossOut
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
        "url": "/api/v1/metering/pricing/waived-loss",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | WaivedLossOut | None:
    if response.status_code == 200:
        response_200 = WaivedLossOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | WaivedLossOut]:
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

) -> Response[ProblemOut | WaivedLossOut]:
    """ Get Waived Loss

     What waiving has cost you over a period, as money.

    A charge is waived where the margin rule had no supplier cost to take a
    margin over, so a waived posting never carried a price and this figure
    cannot be revenue forgone. `basis` states what it is instead, in the
    response itself.

    Waived postings whose own supplier cost UBB never learned are not in the
    figure and are counted beside it, so the total is a floor. Waived postings
    are never candidates for a Resolution Run: a decision somebody made is not
    information UBB is missing.

    Rows are per currency and there is no total across them. The filter is the
    Resolution Run's: a half-open date range, a customer and an Event Type, in
    any combination. A customer this tenant does not have is a 404; a stated
    window longer than 366 days is a `validation_error`.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | WaivedLossOut]
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

) -> ProblemOut | WaivedLossOut | None:
    """ Get Waived Loss

     What waiving has cost you over a period, as money.

    A charge is waived where the margin rule had no supplier cost to take a
    margin over, so a waived posting never carried a price and this figure
    cannot be revenue forgone. `basis` states what it is instead, in the
    response itself.

    Waived postings whose own supplier cost UBB never learned are not in the
    figure and are counted beside it, so the total is a floor. Waived postings
    are never candidates for a Resolution Run: a decision somebody made is not
    information UBB is missing.

    Rows are per currency and there is no total across them. The filter is the
    Resolution Run's: a half-open date range, a customer and an Event Type, in
    any combination. A customer this tenant does not have is a 404; a stated
    window longer than 366 days is a `validation_error`.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | WaivedLossOut
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

) -> Response[ProblemOut | WaivedLossOut]:
    """ Get Waived Loss

     What waiving has cost you over a period, as money.

    A charge is waived where the margin rule had no supplier cost to take a
    margin over, so a waived posting never carried a price and this figure
    cannot be revenue forgone. `basis` states what it is instead, in the
    response itself.

    Waived postings whose own supplier cost UBB never learned are not in the
    figure and are counted beside it, so the total is a floor. Waived postings
    are never candidates for a Resolution Run: a decision somebody made is not
    information UBB is missing.

    Rows are per currency and there is no total across them. The filter is the
    Resolution Run's: a half-open date range, a customer and an Event Type, in
    any combination. A customer this tenant does not have is a 404; a stated
    window longer than 366 days is a `validation_error`.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | WaivedLossOut]
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

) -> ProblemOut | WaivedLossOut | None:
    """ Get Waived Loss

     What waiving has cost you over a period, as money.

    A charge is waived where the margin rule had no supplier cost to take a
    margin over, so a waived posting never carried a price and this figure
    cannot be revenue forgone. `basis` states what it is instead, in the
    response itself.

    Waived postings whose own supplier cost UBB never learned are not in the
    figure and are counted beside it, so the total is a floor. Waived postings
    are never candidates for a Resolution Run: a decision somebody made is not
    information UBB is missing.

    Rows are per currency and there is no total across them. The filter is the
    Resolution Run's: a half-open date range, a customer and an Event Type, in
    any combination. A customer this tenant does not have is a 404; a stated
    window longer than 366 days is a `validation_error`.

    Args:
        selected_from (datetime.datetime | None | Unset):
        selected_to (datetime.datetime | None | Unset):
        selected_customer_id (None | Unset | UUID):
        selected_event_type (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | WaivedLossOut
     """


    return (await asyncio_detailed(
        client=client,
selected_from=selected_from,
selected_to=selected_to,
selected_customer_id=selected_customer_id,
selected_event_type=selected_event_type,

    )).parsed
