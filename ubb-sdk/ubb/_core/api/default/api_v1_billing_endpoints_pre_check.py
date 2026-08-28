from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.pre_check_request import PreCheckRequest
from ...models.pre_check_response import PreCheckResponse
from typing import cast



def _get_kwargs(
    *,
    body: PreCheckRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/billing/pre-check",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> PreCheckResponse | None:
    if response.status_code == 200:
        response_200 = PreCheckResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[PreCheckResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: PreCheckRequest,

) -> Response[PreCheckResponse]:
    """ Pre Check

     Ask whether this customer's spending state would let work proceed.

    ADVISORY ONLY — this call registers nothing. Registering a unit of work is
    `POST /api/v1/tasks`, at the root and behind no product gate, and it is the
    only call that creates one.

    A denial is a `200` carrying `allowed: false` and a `reason`, not an error:
    the question was answered.

    Args:
        body (PreCheckRequest): ADVISORY ONLY — THIS CALL REGISTERS NOTHING (#410).

            It used to, behind a flag, and every field that served the flag has gone
            with it: registering a unit of work is now its own call, `POST
            /api/v1/tasks`, at the root and behind no product gate. A money-shaped
            admission check and the registration of a unit of work were one call
            answering two questions, and a metering-only tenant could not reach the
            second because the first sat behind billing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PreCheckResponse]
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
    body: PreCheckRequest,

) -> PreCheckResponse | None:
    """ Pre Check

     Ask whether this customer's spending state would let work proceed.

    ADVISORY ONLY — this call registers nothing. Registering a unit of work is
    `POST /api/v1/tasks`, at the root and behind no product gate, and it is the
    only call that creates one.

    A denial is a `200` carrying `allowed: false` and a `reason`, not an error:
    the question was answered.

    Args:
        body (PreCheckRequest): ADVISORY ONLY — THIS CALL REGISTERS NOTHING (#410).

            It used to, behind a flag, and every field that served the flag has gone
            with it: registering a unit of work is now its own call, `POST
            /api/v1/tasks`, at the root and behind no product gate. A money-shaped
            admission check and the registration of a unit of work were one call
            answering two questions, and a metering-only tenant could not reach the
            second because the first sat behind billing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PreCheckResponse
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: PreCheckRequest,

) -> Response[PreCheckResponse]:
    """ Pre Check

     Ask whether this customer's spending state would let work proceed.

    ADVISORY ONLY — this call registers nothing. Registering a unit of work is
    `POST /api/v1/tasks`, at the root and behind no product gate, and it is the
    only call that creates one.

    A denial is a `200` carrying `allowed: false` and a `reason`, not an error:
    the question was answered.

    Args:
        body (PreCheckRequest): ADVISORY ONLY — THIS CALL REGISTERS NOTHING (#410).

            It used to, behind a flag, and every field that served the flag has gone
            with it: registering a unit of work is now its own call, `POST
            /api/v1/tasks`, at the root and behind no product gate. A money-shaped
            admission check and the registration of a unit of work were one call
            answering two questions, and a metering-only tenant could not reach the
            second because the first sat behind billing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PreCheckResponse]
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
    body: PreCheckRequest,

) -> PreCheckResponse | None:
    """ Pre Check

     Ask whether this customer's spending state would let work proceed.

    ADVISORY ONLY — this call registers nothing. Registering a unit of work is
    `POST /api/v1/tasks`, at the root and behind no product gate, and it is the
    only call that creates one.

    A denial is a `200` carrying `allowed: false` and a `reason`, not an error:
    the question was answered.

    Args:
        body (PreCheckRequest): ADVISORY ONLY — THIS CALL REGISTERS NOTHING (#410).

            It used to, behind a flag, and every field that served the flag has gone
            with it: registering a unit of work is now its own call, `POST
            /api/v1/tasks`, at the root and behind no product gate. A money-shaped
            admission check and the registration of a unit of work were one call
            answering two questions, and a metering-only tenant could not reach the
            second because the first sat behind billing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PreCheckResponse
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
