from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.plan_out import PlanOut
from ...models.plan_update_in import PlanUpdateIn
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    key: str,
    *,
    body: PlanUpdateIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v1/plans/{key}".format(key=quote(str(key), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> PlanOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = PlanOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[PlanOut | ProblemOut]:
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
    body: PlanUpdateIn,

) -> Response[PlanOut | ProblemOut]:
    """ Update Plan

     Edit a plan.

    FEE axes are grandfathered: Stripe Prices are immutable, so a fee edit
    mints a new versioned Price and existing subscribers keep the old one unless
    migrate_existing=true.

    What the plan's customers pay for usage is not edited here. It is the rules
    in the Pricing Book the plan names, changed through a publish on that book,
    which is what gives a tenant a diff to read before a price moves.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        key (str):
        body (PlanUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PlanOut | ProblemOut]
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
    body: PlanUpdateIn,

) -> PlanOut | ProblemOut | None:
    """ Update Plan

     Edit a plan.

    FEE axes are grandfathered: Stripe Prices are immutable, so a fee edit
    mints a new versioned Price and existing subscribers keep the old one unless
    migrate_existing=true.

    What the plan's customers pay for usage is not edited here. It is the rules
    in the Pricing Book the plan names, changed through a publish on that book,
    which is what gives a tenant a diff to read before a price moves.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        key (str):
        body (PlanUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PlanOut | ProblemOut
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
    body: PlanUpdateIn,

) -> Response[PlanOut | ProblemOut]:
    """ Update Plan

     Edit a plan.

    FEE axes are grandfathered: Stripe Prices are immutable, so a fee edit
    mints a new versioned Price and existing subscribers keep the old one unless
    migrate_existing=true.

    What the plan's customers pay for usage is not edited here. It is the rules
    in the Pricing Book the plan names, changed through a publish on that book,
    which is what gives a tenant a diff to read before a price moves.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        key (str):
        body (PlanUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PlanOut | ProblemOut]
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
    body: PlanUpdateIn,

) -> PlanOut | ProblemOut | None:
    """ Update Plan

     Edit a plan.

    FEE axes are grandfathered: Stripe Prices are immutable, so a fee edit
    mints a new versioned Price and existing subscribers keep the old one unless
    migrate_existing=true.

    What the plan's customers pay for usage is not edited here. It is the rules
    in the Pricing Book the plan names, changed through a publish on that book,
    which is what gives a tenant a diff to read before a price moves.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        key (str):
        body (PlanUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PlanOut | ProblemOut
     """


    return (await asyncio_detailed(
        key=key,
client=client,
body=body,

    )).parsed
