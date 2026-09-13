from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.utilisation_and_headroom_response import UtilisationAndHeadroomResponse
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    customer_id: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,

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


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/spend-controls/utilisation-and-headroom",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> UtilisationAndHeadroomResponse | None:
    if response.status_code == 200:
        response_200 = UtilisationAndHeadroomResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[UtilisationAndHeadroomResponse]:
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

) -> Response[UtilisationAndHeadroomResponse]:
    """ Utilisation And Headroom

     How much of each ceiling was used, and how often it could not be
    evaluated: one row per unit of work that completed in the window (at
    either altitude) with its ceiling status, utilisation and headroom as
    they stood at completion, and the aggregate — the average utilisation
    computed per unit and then across every unit, the share and count that
    reached their ceiling, the share and count that were indeterminate, the
    average unused headroom. Averages are null where no unit contributes,
    never zero. `customer_spend_pool` is that customer's pool status pair
    when `customer_id` names one and a pool applies, otherwise null. The
    filters and the window are `stops-and-breaches`'s, on the instant each
    unit completed.

    Args:
        customer_id (None | str | Unset):
        task_type (None | str | Unset):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UtilisationAndHeadroomResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
task_type=task_type,
since=since,
until=until,

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

) -> UtilisationAndHeadroomResponse | None:
    """ Utilisation And Headroom

     How much of each ceiling was used, and how often it could not be
    evaluated: one row per unit of work that completed in the window (at
    either altitude) with its ceiling status, utilisation and headroom as
    they stood at completion, and the aggregate — the average utilisation
    computed per unit and then across every unit, the share and count that
    reached their ceiling, the share and count that were indeterminate, the
    average unused headroom. Averages are null where no unit contributes,
    never zero. `customer_spend_pool` is that customer's pool status pair
    when `customer_id` names one and a pool applies, otherwise null. The
    filters and the window are `stops-and-breaches`'s, on the instant each
    unit completed.

    Args:
        customer_id (None | str | Unset):
        task_type (None | str | Unset):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UtilisationAndHeadroomResponse
     """


    return sync_detailed(
        client=client,
customer_id=customer_id,
task_type=task_type,
since=since,
until=until,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    customer_id: None | str | Unset = UNSET,
    task_type: None | str | Unset = UNSET,
    since: datetime.datetime | None | Unset = UNSET,
    until: datetime.datetime | None | Unset = UNSET,

) -> Response[UtilisationAndHeadroomResponse]:
    """ Utilisation And Headroom

     How much of each ceiling was used, and how often it could not be
    evaluated: one row per unit of work that completed in the window (at
    either altitude) with its ceiling status, utilisation and headroom as
    they stood at completion, and the aggregate — the average utilisation
    computed per unit and then across every unit, the share and count that
    reached their ceiling, the share and count that were indeterminate, the
    average unused headroom. Averages are null where no unit contributes,
    never zero. `customer_spend_pool` is that customer's pool status pair
    when `customer_id` names one and a pool applies, otherwise null. The
    filters and the window are `stops-and-breaches`'s, on the instant each
    unit completed.

    Args:
        customer_id (None | str | Unset):
        task_type (None | str | Unset):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UtilisationAndHeadroomResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
task_type=task_type,
since=since,
until=until,

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

) -> UtilisationAndHeadroomResponse | None:
    """ Utilisation And Headroom

     How much of each ceiling was used, and how often it could not be
    evaluated: one row per unit of work that completed in the window (at
    either altitude) with its ceiling status, utilisation and headroom as
    they stood at completion, and the aggregate — the average utilisation
    computed per unit and then across every unit, the share and count that
    reached their ceiling, the share and count that were indeterminate, the
    average unused headroom. Averages are null where no unit contributes,
    never zero. `customer_spend_pool` is that customer's pool status pair
    when `customer_id` names one and a pool applies, otherwise null. The
    filters and the window are `stops-and-breaches`'s, on the instant each
    unit completed.

    Args:
        customer_id (None | str | Unset):
        task_type (None | str | Unset):
        since (datetime.datetime | None | Unset):
        until (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UtilisationAndHeadroomResponse
     """


    return (await asyncio_detailed(
        client=client,
customer_id=customer_id,
task_type=task_type,
since=since,
until=until,

    )).parsed
