from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.apps_subscriptions_api_endpoints_pause_subscription_response import AppsSubscriptionsApiEndpointsPauseSubscriptionResponse
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    external_id: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/subscriptions/customers/{external_id}/subscription/pause".format(external_id=quote(str(external_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut | None:
    if response.status_code == 200:
        response_200 = AppsSubscriptionsApiEndpointsPauseSubscriptionResponse.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut]:
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

) -> Response[AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut]:
    """ Pause Subscription

     Pause collection (void) — the subscription stays active but stops billing.

    Args:
        external_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut]
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

) -> AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut | None:
    """ Pause Subscription

     Pause collection (void) — the subscription stays active but stops billing.

    Args:
        external_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut
     """


    return sync_detailed(
        external_id=external_id,
client=client,

    ).parsed

async def asyncio_detailed(
    external_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut]:
    """ Pause Subscription

     Pause collection (void) — the subscription stays active but stops billing.

    Args:
        external_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut]
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

) -> AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut | None:
    """ Pause Subscription

     Pause collection (void) — the subscription stays active but stops billing.

    Args:
        external_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AppsSubscriptionsApiEndpointsPauseSubscriptionResponse | ProblemOut
     """


    return (await asyncio_detailed(
        external_id=external_id,
client=client,

    )).parsed
