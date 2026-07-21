from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_v1_platform_endpoints_cancel_subscription_response import ApiV1PlatformEndpointsCancelSubscriptionResponse
from ...models.problem_out import ProblemOut
from ...models.subscription_cancel_in import SubscriptionCancelIn
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    external_id: str,
    *,
    body: None | SubscriptionCancelIn | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/platform/customers/{external_id}/subscription/cancel".format(external_id=quote(str(external_id), safe=""),),
    }

    
    if isinstance(body, SubscriptionCancelIn):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = ApiV1PlatformEndpointsCancelSubscriptionResponse.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut]:
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
    body: None | SubscriptionCancelIn | Unset = UNSET,

) -> Response[ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut]:
    """ Cancel Subscription

     Cancel the customer's subscription (default: at period end).

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        external_id (str):
        body (None | SubscriptionCancelIn | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut]
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
    body: None | SubscriptionCancelIn | Unset = UNSET,

) -> ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut | None:
    """ Cancel Subscription

     Cancel the customer's subscription (default: at period end).

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        external_id (str):
        body (None | SubscriptionCancelIn | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut
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
    body: None | SubscriptionCancelIn | Unset = UNSET,

) -> Response[ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut]:
    """ Cancel Subscription

     Cancel the customer's subscription (default: at period end).

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        external_id (str):
        body (None | SubscriptionCancelIn | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut]
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
    body: None | SubscriptionCancelIn | Unset = UNSET,

) -> ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut | None:
    """ Cancel Subscription

     Cancel the customer's subscription (default: at period end).

    Trials and coupons are deliberate non-goals: Stripe owns those levers.

    Args:
        external_id (str):
        body (None | SubscriptionCancelIn | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiV1PlatformEndpointsCancelSubscriptionResponse | ProblemOut
     """


    return (await asyncio_detailed(
        external_id=external_id,
client=client,
body=body,

    )).parsed
