from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.affordability_response import AffordabilityResponse
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: str,
    *,
    parent_task_id: None | Unset | UUID = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_parent_task_id: None | str | Unset
    if isinstance(parent_task_id, Unset):
        json_parent_task_id = UNSET
    elif isinstance(parent_task_id, UUID):
        json_parent_task_id = str(parent_task_id)
    else:
        json_parent_task_id = parent_task_id
    params["parent_task_id"] = json_parent_task_id


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/billing/customers/{customer_id}/affordability".format(customer_id=quote(str(customer_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> AffordabilityResponse | None:
    if response.status_code == 200:
        response_200 = AffordabilityResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[AffordabilityResponse]:
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
    parent_task_id: None | Unset | UUID = UNSET,

) -> Response[AffordabilityResponse]:
    """ Affordability

     Ask whether this customer's spending state would let new work proceed.

    ADVISORY ONLY — this call registers nothing, moves no admission window,
    and is never the last word: `POST /api/v1/tasks` re-runs every check
    here when work is actually started. A denial is a `200` carrying
    `allowed: false` and a `reason`, not an error: the question was answered.

    `parent_task_id` names the running parent the work would be contained
    in, and is read for the soft floor only: past the wind-down line NEW
    top-level work is refused while contained work under a running parent
    passes, so the answer differs by altitude. Whether that parent is live
    is a start's question, not this one's.

    Requires the `billing` product: everything this reports is about a
    wallet — its balance, its floors, the customer's spend pool.

    Args:
        customer_id (str):
        parent_task_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AffordabilityResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
parent_task_id=parent_task_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    parent_task_id: None | Unset | UUID = UNSET,

) -> AffordabilityResponse | None:
    """ Affordability

     Ask whether this customer's spending state would let new work proceed.

    ADVISORY ONLY — this call registers nothing, moves no admission window,
    and is never the last word: `POST /api/v1/tasks` re-runs every check
    here when work is actually started. A denial is a `200` carrying
    `allowed: false` and a `reason`, not an error: the question was answered.

    `parent_task_id` names the running parent the work would be contained
    in, and is read for the soft floor only: past the wind-down line NEW
    top-level work is refused while contained work under a running parent
    passes, so the answer differs by altitude. Whether that parent is live
    is a start's question, not this one's.

    Requires the `billing` product: everything this reports is about a
    wallet — its balance, its floors, the customer's spend pool.

    Args:
        customer_id (str):
        parent_task_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AffordabilityResponse
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
parent_task_id=parent_task_id,

    ).parsed

async def asyncio_detailed(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    parent_task_id: None | Unset | UUID = UNSET,

) -> Response[AffordabilityResponse]:
    """ Affordability

     Ask whether this customer's spending state would let new work proceed.

    ADVISORY ONLY — this call registers nothing, moves no admission window,
    and is never the last word: `POST /api/v1/tasks` re-runs every check
    here when work is actually started. A denial is a `200` carrying
    `allowed: false` and a `reason`, not an error: the question was answered.

    `parent_task_id` names the running parent the work would be contained
    in, and is read for the soft floor only: past the wind-down line NEW
    top-level work is refused while contained work under a running parent
    passes, so the answer differs by altitude. Whether that parent is live
    is a start's question, not this one's.

    Requires the `billing` product: everything this reports is about a
    wallet — its balance, its floors, the customer's spend pool.

    Args:
        customer_id (str):
        parent_task_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AffordabilityResponse]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
parent_task_id=parent_task_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: str,
    *,
    client: AuthenticatedClient,
    parent_task_id: None | Unset | UUID = UNSET,

) -> AffordabilityResponse | None:
    """ Affordability

     Ask whether this customer's spending state would let new work proceed.

    ADVISORY ONLY — this call registers nothing, moves no admission window,
    and is never the last word: `POST /api/v1/tasks` re-runs every check
    here when work is actually started. A denial is a `200` carrying
    `allowed: false` and a `reason`, not an error: the question was answered.

    `parent_task_id` names the running parent the work would be contained
    in, and is read for the soft floor only: past the wind-down line NEW
    top-level work is refused while contained work under a running parent
    passes, so the answer differs by altitude. Whether that parent is live
    is a start's question, not this one's.

    Requires the `billing` product: everything this reports is about a
    wallet — its balance, its floors, the customer's spend pool.

    Args:
        customer_id (str):
        parent_task_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AffordabilityResponse
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
parent_task_id=parent_task_id,

    )).parsed
