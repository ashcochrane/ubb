from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.usage_batch_request import UsageBatchRequest
from ...models.usage_batch_response import UsageBatchResponse
from typing import cast



def _get_kwargs(
    *,
    body: UsageBatchRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/usage/batch",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> UsageBatchResponse | None:
    if response.status_code == 200:
        response_200 = UsageBatchResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[UsageBatchResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: UsageBatchRequest,

) -> Response[UsageBatchResponse]:
    """ Record Usage Batch

     Batch ingestion: 1..100 INDEPENDENT items (>100 or 0 → 422).

    Each item runs the same per-item record_usage in its own atomic commit —
    deliberately NOT one mega-transaction, which would hold Task/counter locks
    for the whole batch, delay outbox dispatch, and diverge from the semantics
    of N sequential singles. Always HTTP 200 with positionally-aligned
    results[] + accepted/rejected counts; per-item idempotency makes a
    whole-batch replay return the original event ids with zero new rows, and
    a duplicate idempotency_key WITHIN one batch resolves to the first item's
    event id (the first item commits before the second runs).

    Args:
        body (UsageBatchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UsageBatchResponse]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    body: UsageBatchRequest,

) -> UsageBatchResponse | None:
    """ Record Usage Batch

     Batch ingestion: 1..100 INDEPENDENT items (>100 or 0 → 422).

    Each item runs the same per-item record_usage in its own atomic commit —
    deliberately NOT one mega-transaction, which would hold Task/counter locks
    for the whole batch, delay outbox dispatch, and diverge from the semantics
    of N sequential singles. Always HTTP 200 with positionally-aligned
    results[] + accepted/rejected counts; per-item idempotency makes a
    whole-batch replay return the original event ids with zero new rows, and
    a duplicate idempotency_key WITHIN one batch resolves to the first item's
    event id (the first item commits before the second runs).

    Args:
        body (UsageBatchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UsageBatchResponse
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: UsageBatchRequest,

) -> Response[UsageBatchResponse]:
    """ Record Usage Batch

     Batch ingestion: 1..100 INDEPENDENT items (>100 or 0 → 422).

    Each item runs the same per-item record_usage in its own atomic commit —
    deliberately NOT one mega-transaction, which would hold Task/counter locks
    for the whole batch, delay outbox dispatch, and diverge from the semantics
    of N sequential singles. Always HTTP 200 with positionally-aligned
    results[] + accepted/rejected counts; per-item idempotency makes a
    whole-batch replay return the original event ids with zero new rows, and
    a duplicate idempotency_key WITHIN one batch resolves to the first item's
    event id (the first item commits before the second runs).

    Args:
        body (UsageBatchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UsageBatchResponse]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    body: UsageBatchRequest,

) -> UsageBatchResponse | None:
    """ Record Usage Batch

     Batch ingestion: 1..100 INDEPENDENT items (>100 or 0 → 422).

    Each item runs the same per-item record_usage in its own atomic commit —
    deliberately NOT one mega-transaction, which would hold Task/counter locks
    for the whole batch, delay outbox dispatch, and diverge from the semantics
    of N sequential singles. Always HTTP 200 with positionally-aligned
    results[] + accepted/rejected counts; per-item idempotency makes a
    whole-batch replay return the original event ids with zero new rows, and
    a duplicate idempotency_key WITHIN one batch resolves to the first item's
    event id (the first item commits before the second runs).

    Args:
        body (UsageBatchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UsageBatchResponse
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
