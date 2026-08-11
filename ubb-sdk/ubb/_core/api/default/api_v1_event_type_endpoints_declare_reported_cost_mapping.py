from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.reported_cost_mapping_in import ReportedCostMappingIn
from ...models.reported_cost_mapping_out import ReportedCostMappingOut
from typing import cast



def _get_kwargs(
    key: str,
    *,
    body: ReportedCostMappingIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/event-types/{key}/reported-cost-mapping".format(key=quote(str(key), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | ReportedCostMappingOut | None:
    if response.status_code == 200:
        response_200 = ReportedCostMappingOut.from_dict(response.json())



        return response_200

    if response.status_code == 201:
        response_201 = ReportedCostMappingOut.from_dict(response.json())



        return response_201

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if response.status_code == 409:
        response_409 = ProblemOut.from_dict(response.json())



        return response_409

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | ReportedCostMappingOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    key: str,
    *,
    client: AuthenticatedClient,
    body: ReportedCostMappingIn,

) -> Response[ProblemOut | ReportedCostMappingOut]:
    """ Declare Reported Cost Mapping

     Declare where a supplier's own cost figure is read from. One per type.

    A sibling of the quantities rather than one of them, which is why it is a
    PUT on a singular path: money with a currency does not fit a shape built
    for a quantity and its unit, and there is exactly one such number per
    Event Type. It carries its own action for the reason each satellite does —
    the ledger's `resource_type` names which record moved, and an action
    naming the Event Type over a row that is the mapping would make the two
    disagree.

    Args:
        key (str):
        body (ReportedCostMappingIn): Where a supplier's own cost figure is read from. One per
            Event Type.

            A sibling of the declared quantities rather than one of them: money with a
            currency does not fit a shape built for a quantity and its unit.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ReportedCostMappingOut]
     """


    kwargs = _get_kwargs(
        key=key,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    key: str,
    *,
    client: AuthenticatedClient,
    body: ReportedCostMappingIn,

) -> ProblemOut | ReportedCostMappingOut | None:
    """ Declare Reported Cost Mapping

     Declare where a supplier's own cost figure is read from. One per type.

    A sibling of the quantities rather than one of them, which is why it is a
    PUT on a singular path: money with a currency does not fit a shape built
    for a quantity and its unit, and there is exactly one such number per
    Event Type. It carries its own action for the reason each satellite does —
    the ledger's `resource_type` names which record moved, and an action
    naming the Event Type over a row that is the mapping would make the two
    disagree.

    Args:
        key (str):
        body (ReportedCostMappingIn): Where a supplier's own cost figure is read from. One per
            Event Type.

            A sibling of the declared quantities rather than one of them: money with a
            currency does not fit a shape built for a quantity and its unit.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ReportedCostMappingOut
     """


    return sync_detailed(
        key=key,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    key: str,
    *,
    client: AuthenticatedClient,
    body: ReportedCostMappingIn,

) -> Response[ProblemOut | ReportedCostMappingOut]:
    """ Declare Reported Cost Mapping

     Declare where a supplier's own cost figure is read from. One per type.

    A sibling of the quantities rather than one of them, which is why it is a
    PUT on a singular path: money with a currency does not fit a shape built
    for a quantity and its unit, and there is exactly one such number per
    Event Type. It carries its own action for the reason each satellite does —
    the ledger's `resource_type` names which record moved, and an action
    naming the Event Type over a row that is the mapping would make the two
    disagree.

    Args:
        key (str):
        body (ReportedCostMappingIn): Where a supplier's own cost figure is read from. One per
            Event Type.

            A sibling of the declared quantities rather than one of them: money with a
            currency does not fit a shape built for a quantity and its unit.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ReportedCostMappingOut]
     """


    kwargs = _get_kwargs(
        key=key,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    key: str,
    *,
    client: AuthenticatedClient,
    body: ReportedCostMappingIn,

) -> ProblemOut | ReportedCostMappingOut | None:
    """ Declare Reported Cost Mapping

     Declare where a supplier's own cost figure is read from. One per type.

    A sibling of the quantities rather than one of them, which is why it is a
    PUT on a singular path: money with a currency does not fit a shape built
    for a quantity and its unit, and there is exactly one such number per
    Event Type. It carries its own action for the reason each satellite does —
    the ledger's `resource_type` names which record moved, and an action
    naming the Event Type over a row that is the mapping would make the two
    disagree.

    Args:
        key (str):
        body (ReportedCostMappingIn): Where a supplier's own cost figure is read from. One per
            Event Type.

            A sibling of the declared quantities rather than one of them: money with a
            currency does not fit a shape built for a quantity and its unit.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ReportedCostMappingOut
     """


    return (await asyncio_detailed(
        key=key,
client=client,
body=body,

    )).parsed
