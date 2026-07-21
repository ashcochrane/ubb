from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.budget_config_in import BudgetConfigIn
from ...models.budget_config_out import BudgetConfigOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,
    *,
    body: BudgetConfigIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/billing/customers/{customer_id}/budget".format(customer_id=quote(str(customer_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> BudgetConfigOut | None:
    if response.status_code == 200:
        response_200 = BudgetConfigOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[BudgetConfigOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: BudgetConfigIn,

) -> Response[BudgetConfigOut]:
    """ Put Customer Budget

    Args:
        customer_id (UUID):
        body (BudgetConfigIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BudgetConfigOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: BudgetConfigIn,

) -> BudgetConfigOut | None:
    """ Put Customer Budget

    Args:
        customer_id (UUID):
        body (BudgetConfigIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BudgetConfigOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: BudgetConfigIn,

) -> Response[BudgetConfigOut]:
    """ Put Customer Budget

    Args:
        customer_id (UUID):
        body (BudgetConfigIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BudgetConfigOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: BudgetConfigIn,

) -> BudgetConfigOut | None:
    """ Put Customer Budget

    Args:
        customer_id (UUID):
        body (BudgetConfigIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BudgetConfigOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
body=body,

    )).parsed
