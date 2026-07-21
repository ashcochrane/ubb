from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_platform_endpoints_resume_subscription_response import ApiV1PlatformEndpointsResumeSubscriptionResponse
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    external_id: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/platform/customers/{external_id}/subscription/resume".format(external_id=quote(str(external_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1PlatformEndpointsResumeSubscriptionResponse.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut]:
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

) -> Response[ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut]:
    """ Resume Subscription

     Resume billing: clears a pause AND any pending at-period-end cancel.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        external_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        external_id=external_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    external_id: str,
    *,
    client: AuthenticatedClient,

) -> ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut | None:
    """ Resume Subscription

     Resume billing: clears a pause AND any pending at-period-end cancel.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        external_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut
     """


    return sync_detailed(
        external_id=external_id,
client=client,

    ).parsed

async def asyncio_detailed(
    external_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut]:
    """ Resume Subscription

     Resume billing: clears a pause AND any pending at-period-end cancel.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        external_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut]
     """


    kwargs = _get_kwargs(
        external_id=external_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    external_id: str,
    *,
    client: AuthenticatedClient,

) -> ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut | None:
    """ Resume Subscription

     Resume billing: clears a pause AND any pending at-period-end cancel.

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        external_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlatformEndpointsResumeSubscriptionResponse | ProblemOut
     """


    return (await asyncio_detailed(
        external_id=external_id,
client=client,

    )).parsed
