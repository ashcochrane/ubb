from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_plan_endpoints_assign_plan_response import ApiV1PlanEndpointsAssignPlanResponse
from ...models.assign_plan_in import AssignPlanIn
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    external_id: str,
    *,
    body: AssignPlanIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/customers/{external_id}/plan".format(external_id=quote(str(external_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1PlanEndpointsAssignPlanResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1PlanEndpointsAssignPlanResponse.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1PlanEndpointsAssignPlanResponse | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    external_id: str,
    *,
    client: AuthenticatedClient,
    body: AssignPlanIn,

) -> Response[ApiV1PlanEndpointsAssignPlanResponse | ProblemOut]:
    """ Assign Plan

     Put a customer on a plan.

    This is the plan-membership write and it never touches Stripe. Starting the
    Stripe subscription for a plan's fee axes is a separate call
    (POST /subscriptions/customers/{external_id}/subscribe), because a
    markup-only plan has no Stripe subscription to start.

    Args:
        external_id (str):
        body (AssignPlanIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlanEndpointsAssignPlanResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        external_id=external_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    external_id: str,
    *,
    client: AuthenticatedClient,
    body: AssignPlanIn,

) -> ApiV1PlanEndpointsAssignPlanResponse | ProblemOut | None:
    """ Assign Plan

     Put a customer on a plan.

    This is the plan-membership write and it never touches Stripe. Starting the
    Stripe subscription for a plan's fee axes is a separate call
    (POST /subscriptions/customers/{external_id}/subscribe), because a
    markup-only plan has no Stripe subscription to start.

    Args:
        external_id (str):
        body (AssignPlanIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlanEndpointsAssignPlanResponse | ProblemOut
     """


    return sync_detailed(
        external_id=external_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    external_id: str,
    *,
    client: AuthenticatedClient,
    body: AssignPlanIn,

) -> Response[ApiV1PlanEndpointsAssignPlanResponse | ProblemOut]:
    """ Assign Plan

     Put a customer on a plan.

    This is the plan-membership write and it never touches Stripe. Starting the
    Stripe subscription for a plan's fee axes is a separate call
    (POST /subscriptions/customers/{external_id}/subscribe), because a
    markup-only plan has no Stripe subscription to start.

    Args:
        external_id (str):
        body (AssignPlanIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlanEndpointsAssignPlanResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        external_id=external_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    external_id: str,
    *,
    client: AuthenticatedClient,
    body: AssignPlanIn,

) -> ApiV1PlanEndpointsAssignPlanResponse | ProblemOut | None:
    """ Assign Plan

     Put a customer on a plan.

    This is the plan-membership write and it never touches Stripe. Starting the
    Stripe subscription for a plan's fee axes is a separate call
    (POST /subscriptions/customers/{external_id}/subscribe), because a
    markup-only plan has no Stripe subscription to start.

    Args:
        external_id (str):
        body (AssignPlanIn):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlanEndpointsAssignPlanResponse | ProblemOut
     """


    return (await asyncio_detailed(
        external_id=external_id,
client=client,
body=body,

    )).parsed
