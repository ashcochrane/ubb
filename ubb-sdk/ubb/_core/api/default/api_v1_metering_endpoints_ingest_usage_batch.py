from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.ingest_batch_request import IngestBatchRequest
from ...models.ingest_batch_response import IngestBatchResponse
from typing import cast



def _get_kwargs(
    *,
    body: IngestBatchRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/usage/ingest",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> IngestBatchResponse | None:
    if response.status_code == 200:
        response_200 = IngestBatchResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[IngestBatchResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: IngestBatchRequest,

) -> Response[IngestBatchResponse]:
    """ Ingest Usage Batch

     Async accept path: estimate -> atomic hold -> durable raw append -> 202-style
    verdicts. Exact pricing settles in workers (estimate-hold-settle; see
    docs/plans/2026-07-03-async-ingestion-hard-stop-design.md). Settlement is
    claimed by the settle_raw_events task (wired in the settlement change) —
    this endpoint's only durability contract is that every held/duplicate-
    suspect item lands in RawIngestEvent before the response is returned.

    Args:
        body (IngestBatchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IngestBatchResponse]
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
    body: IngestBatchRequest,

) -> IngestBatchResponse | None:
    """ Ingest Usage Batch

     Async accept path: estimate -> atomic hold -> durable raw append -> 202-style
    verdicts. Exact pricing settles in workers (estimate-hold-settle; see
    docs/plans/2026-07-03-async-ingestion-hard-stop-design.md). Settlement is
    claimed by the settle_raw_events task (wired in the settlement change) —
    this endpoint's only durability contract is that every held/duplicate-
    suspect item lands in RawIngestEvent before the response is returned.

    Args:
        body (IngestBatchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IngestBatchResponse
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: IngestBatchRequest,

) -> Response[IngestBatchResponse]:
    """ Ingest Usage Batch

     Async accept path: estimate -> atomic hold -> durable raw append -> 202-style
    verdicts. Exact pricing settles in workers (estimate-hold-settle; see
    docs/plans/2026-07-03-async-ingestion-hard-stop-design.md). Settlement is
    claimed by the settle_raw_events task (wired in the settlement change) —
    this endpoint's only durability contract is that every held/duplicate-
    suspect item lands in RawIngestEvent before the response is returned.

    Args:
        body (IngestBatchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IngestBatchResponse]
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
    body: IngestBatchRequest,

) -> IngestBatchResponse | None:
    """ Ingest Usage Batch

     Async accept path: estimate -> atomic hold -> durable raw append -> 202-style
    verdicts. Exact pricing settles in workers (estimate-hold-settle; see
    docs/plans/2026-07-03-async-ingestion-hard-stop-design.md). Settlement is
    claimed by the settle_raw_events task (wired in the settlement change) —
    this endpoint's only durability contract is that every held/duplicate-
    suspect item lands in RawIngestEvent before the response is returned.

    Args:
        body (IngestBatchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IngestBatchResponse
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
