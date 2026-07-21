from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.webhook_delivery_list_response import WebhookDeliveryListResponse
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    config_id: str,
    *,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params["limit"] = limit


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/webhooks/configs/{config_id}/deliveries".format(config_id=quote(str(config_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | WebhookDeliveryListResponse | None:
    if response.status_code == 200:
        response_200 = WebhookDeliveryListResponse.from_dict(response.json())



        return response_200

    if response.status_code == 400:
        response_400 = ProblemOut.from_dict(response.json())



        return response_400

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | WebhookDeliveryListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    config_id: str,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[ProblemOut | WebhookDeliveryListResponse]:
    """ List Webhook Deliveries

     The self-serve debugging surface: per-endpoint delivery attempts —
    successes, retries, and dead-letters — newest first, in the house cursor
    envelope, over the per-endpoint checkpointed records (#76).

    Args:
        config_id (str):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | WebhookDeliveryListResponse]
     """


    kwargs = _get_kwargs(
        config_id=config_id,
cursor=cursor,
limit=limit,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    config_id: str,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> ProblemOut | WebhookDeliveryListResponse | None:
    """ List Webhook Deliveries

     The self-serve debugging surface: per-endpoint delivery attempts —
    successes, retries, and dead-letters — newest first, in the house cursor
    envelope, over the per-endpoint checkpointed records (#76).

    Args:
        config_id (str):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | WebhookDeliveryListResponse
     """


    return sync_detailed(
        config_id=config_id,
client=client,
cursor=cursor,
limit=limit,

    ).parsed

async def asyncio_detailed(
    config_id: str,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> Response[ProblemOut | WebhookDeliveryListResponse]:
    """ List Webhook Deliveries

     The self-serve debugging surface: per-endpoint delivery attempts —
    successes, retries, and dead-letters — newest first, in the house cursor
    envelope, over the per-endpoint checkpointed records (#76).

    Args:
        config_id (str):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | WebhookDeliveryListResponse]
     """


    kwargs = _get_kwargs(
        config_id=config_id,
cursor=cursor,
limit=limit,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    config_id: str,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,

) -> ProblemOut | WebhookDeliveryListResponse | None:
    """ List Webhook Deliveries

     The self-serve debugging surface: per-endpoint delivery attempts —
    successes, retries, and dead-letters — newest first, in the house cursor
    envelope, over the per-endpoint checkpointed records (#76).

    Args:
        config_id (str):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | WebhookDeliveryListResponse
     """


    return (await asyncio_detailed(
        config_id=config_id,
client=client,
cursor=cursor,
limit=limit,

    )).parsed
