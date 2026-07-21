from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_platform_endpoints_update_plan_response import ApiV1PlatformEndpointsUpdatePlanResponse
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
        "url": "/api/v1/platform/plans/{key}".format(key=quote(str(key), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1PlatformEndpointsUpdatePlanResponse.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut]:
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

) -> Response[ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut]:
    r""" Update Plan

     Edit plan fees (F5.4). Provisioned axes get a NEW versioned Stripe Price;
    existing subscriptions are grandfathered on their old price unless
    migrate_existing=true (repointed with proration_behavior=\"none\").

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        key (str):
        body (PlanUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut]
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

) -> ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut | None:
    r""" Update Plan

     Edit plan fees (F5.4). Provisioned axes get a NEW versioned Stripe Price;
    existing subscriptions are grandfathered on their old price unless
    migrate_existing=true (repointed with proration_behavior=\"none\").

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        key (str):
        body (PlanUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut
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

) -> Response[ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut]:
    r""" Update Plan

     Edit plan fees (F5.4). Provisioned axes get a NEW versioned Stripe Price;
    existing subscriptions are grandfathered on their old price unless
    migrate_existing=true (repointed with proration_behavior=\"none\").

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        key (str):
        body (PlanUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut]
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

) -> ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut | None:
    r""" Update Plan

     Edit plan fees (F5.4). Provisioned axes get a NEW versioned Stripe Price;
    existing subscriptions are grandfathered on their old price unless
    migrate_existing=true (repointed with proration_behavior=\"none\").

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        key (str):
        body (PlanUpdateIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlatformEndpointsUpdatePlanResponse | ProblemOut
     """


    return (await asyncio_detailed(
        key=key,
client=client,
body=body,

    )).parsed
