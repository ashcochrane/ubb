from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_spend_control_endpoints_stops_and_breaches_control_family_type_0 import ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0
from ...models.stops_and_breaches_response import StopsAndBreachesResponse
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    customer_id: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,
    control_family: ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_customer_id: None | str | Unset
    if isinstance(customer_id, Unset):
        json_customer_id = UNSET
    else:
        json_customer_id = customer_id
    params["customer_id"] = json_customer_id

    json_task_type: None | str | Unset
    if isinstance(task_type, Unset):
        json_task_type = UNSET
    else:
        json_task_type = task_type
    params["task_type"] = json_task_type

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

    json_control_family: None | str | Unset
    if isinstance(control_family, Unset):
        json_control_family = UNSET
    elif isinstance(control_family, ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0):
        json_control_family = control_family.value
    else:
        json_control_family = control_family
    params["control_family"] = json_control_family


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/spend-controls/stops-and-breaches",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> StopsAndBreachesResponse | None:
    if response.status_code == 200:
        response_200 = StopsAndBreachesResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[StopsAndBreachesResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    customer_id: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,
    control_family: ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None | Unset = UNSET,

) -> Response[StopsAndBreachesResponse]:
    """ Stops And Breaches

     What was spent past a stop, and why: every spend control that fired
    and had an enforcement consequence, in the window, as typed rows — a
    Ceiling row per unit stopped on its own ceiling, a Customer spend pool
    row per pool episode (explained by the Charge that crossed it), a Wallet
    policy row per floor episode (a soft-floor row is a marker with no
    events). Tenant-wide; `customer_id` narrows to one customer's work and
    its billing owner's customer-wide episodes, `task_type` to one kind of
    work (customer-wide episodes have no kind and drop out), `since`/`until`
    (ISO datetimes; naive = UTC) to the instant each episode opened, and
    `control_family` to one family — a family this workspace lacks answers
    no rows, never an error. Expiries and admission control appear in
    neither report. A window left open covers the 366 days ending now; the
    response echoes the window applied.

    Args:
        customer_id (None | str | Unset):
        task_type (None | str | Unset):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):
        control_family (ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None |
            Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[StopsAndBreachesResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
task_type=task_type,
since=since,
until=until,
control_family=control_family,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    customer_id: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,
    control_family: ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None | Unset = UNSET,

) -> StopsAndBreachesResponse | None:
    """ Stops And Breaches

     What was spent past a stop, and why: every spend control that fired
    and had an enforcement consequence, in the window, as typed rows — a
    Ceiling row per unit stopped on its own ceiling, a Customer spend pool
    row per pool episode (explained by the Charge that crossed it), a Wallet
    policy row per floor episode (a soft-floor row is a marker with no
    events). Tenant-wide; `customer_id` narrows to one customer's work and
    its billing owner's customer-wide episodes, `task_type` to one kind of
    work (customer-wide episodes have no kind and drop out), `since`/`until`
    (ISO datetimes; naive = UTC) to the instant each episode opened, and
    `control_family` to one family — a family this workspace lacks answers
    no rows, never an error. Expiries and admission control appear in
    neither report. A window left open covers the 366 days ending now; the
    response echoes the window applied.

    Args:
        customer_id (None | str | Unset):
        task_type (None | str | Unset):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):
        control_family (ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None |
            Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        StopsAndBreachesResponse
     """


    return sync_detailed(
        client=client,
customer_id=customer_id,
task_type=task_type,
since=since,
until=until,
control_family=control_family,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    customer_id: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,
    control_family: ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None | Unset = UNSET,

) -> Response[StopsAndBreachesResponse]:
    """ Stops And Breaches

     What was spent past a stop, and why: every spend control that fired
    and had an enforcement consequence, in the window, as typed rows — a
    Ceiling row per unit stopped on its own ceiling, a Customer spend pool
    row per pool episode (explained by the Charge that crossed it), a Wallet
    policy row per floor episode (a soft-floor row is a marker with no
    events). Tenant-wide; `customer_id` narrows to one customer's work and
    its billing owner's customer-wide episodes, `task_type` to one kind of
    work (customer-wide episodes have no kind and drop out), `since`/`until`
    (ISO datetimes; naive = UTC) to the instant each episode opened, and
    `control_family` to one family — a family this workspace lacks answers
    no rows, never an error. Expiries and admission control appear in
    neither report. A window left open covers the 366 days ending now; the
    response echoes the window applied.

    Args:
        customer_id (None | str | Unset):
        task_type (None | str | Unset):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):
        control_family (ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None |
            Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[StopsAndBreachesResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
task_type=task_type,
since=since,
until=until,
control_family=control_family,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    customer_id: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,
    control_family: ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None | Unset = UNSET,

) -> StopsAndBreachesResponse | None:
    """ Stops And Breaches

     What was spent past a stop, and why: every spend control that fired
    and had an enforcement consequence, in the window, as typed rows — a
    Ceiling row per unit stopped on its own ceiling, a Customer spend pool
    row per pool episode (explained by the Charge that crossed it), a Wallet
    policy row per floor episode (a soft-floor row is a marker with no
    events). Tenant-wide; `customer_id` narrows to one customer's work and
    its billing owner's customer-wide episodes, `task_type` to one kind of
    work (customer-wide episodes have no kind and drop out), `since`/`until`
    (ISO datetimes; naive = UTC) to the instant each episode opened, and
    `control_family` to one family — a family this workspace lacks answers
    no rows, never an error. Expiries and admission control appear in
    neither report. A window left open covers the 366 days ending now; the
    response echoes the window applied.

    Args:
        customer_id (None | str | Unset):
        task_type (None | str | Unset):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):
        control_family (ApiV1SpendControlEndpointsStopsAndBreachesControlFamilyType0 | None |
            Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        StopsAndBreachesResponse
     """


    return (await asyncio_detailed(
        client=client,
customer_id=customer_id,
task_type=task_type,
since=since,
until=until,
control_family=control_family,

    )).parsed
