from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.cost_book_in import CostBookIn
from ...models.cost_book_out import CostBookOut
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    *,
    body: CostBookIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/cost-books",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> CostBookOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = CostBookOut.from_dict(response.json())



        return response_200

    if response.status_code == 409:
        response_409 = ProblemOut.from_dict(response.json())



        return response_409

    if response.status_code == 422:
        response_422 = ProblemOut.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[CostBookOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: CostBookIn,

) -> Response[CostBookOut | ProblemOut]:
    """ Declare Cost Book

     Declare a cost book: a record of what one supplier charges this tenant.

    It arrives EMPTY, for the reason a Pricing Book does: UBB ships no
    catalogue of supplier prices and cannot — they are the supplier's.

    Declarations dedupe on natural identity: a second book under the same key,
    or a second default for one supplier and currency, answers 409.

    Args:
        body (CostBookIn): Declare a cost book: a record of what one supplier charges this tenant.

            It names the supplier and the currency that supplier bills in, and both
            are required in the sense that matters: `currency` may not be empty, and
            `provider_key` must be stated — the empty string is a stated value and
            means the book applies whatever the supplier, which is a real choice
            rather than an omission.

            `is_default` marks the book a cost is resolved from for that supplier and
            currency. A tenant has at most one per pair; declaring a second answers
            409.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CostBookOut | ProblemOut]
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
    body: CostBookIn,

) -> CostBookOut | ProblemOut | None:
    """ Declare Cost Book

     Declare a cost book: a record of what one supplier charges this tenant.

    It arrives EMPTY, for the reason a Pricing Book does: UBB ships no
    catalogue of supplier prices and cannot — they are the supplier's.

    Declarations dedupe on natural identity: a second book under the same key,
    or a second default for one supplier and currency, answers 409.

    Args:
        body (CostBookIn): Declare a cost book: a record of what one supplier charges this tenant.

            It names the supplier and the currency that supplier bills in, and both
            are required in the sense that matters: `currency` may not be empty, and
            `provider_key` must be stated — the empty string is a stated value and
            means the book applies whatever the supplier, which is a real choice
            rather than an omission.

            `is_default` marks the book a cost is resolved from for that supplier and
            currency. A tenant has at most one per pair; declaring a second answers
            409.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CostBookOut | ProblemOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: CostBookIn,

) -> Response[CostBookOut | ProblemOut]:
    """ Declare Cost Book

     Declare a cost book: a record of what one supplier charges this tenant.

    It arrives EMPTY, for the reason a Pricing Book does: UBB ships no
    catalogue of supplier prices and cannot — they are the supplier's.

    Declarations dedupe on natural identity: a second book under the same key,
    or a second default for one supplier and currency, answers 409.

    Args:
        body (CostBookIn): Declare a cost book: a record of what one supplier charges this tenant.

            It names the supplier and the currency that supplier bills in, and both
            are required in the sense that matters: `currency` may not be empty, and
            `provider_key` must be stated — the empty string is a stated value and
            means the book applies whatever the supplier, which is a real choice
            rather than an omission.

            `is_default` marks the book a cost is resolved from for that supplier and
            currency. A tenant has at most one per pair; declaring a second answers
            409.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CostBookOut | ProblemOut]
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
    body: CostBookIn,

) -> CostBookOut | ProblemOut | None:
    """ Declare Cost Book

     Declare a cost book: a record of what one supplier charges this tenant.

    It arrives EMPTY, for the reason a Pricing Book does: UBB ships no
    catalogue of supplier prices and cannot — they are the supplier's.

    Declarations dedupe on natural identity: a second book under the same key,
    or a second default for one supplier and currency, answers 409.

    Args:
        body (CostBookIn): Declare a cost book: a record of what one supplier charges this tenant.

            It names the supplier and the currency that supplier bills in, and both
            are required in the sense that matters: `currency` may not be empty, and
            `provider_key` must be stated — the empty string is a stated value and
            means the book applies whatever the supplier, which is a real choice
            rather than an omission.

            `is_default` marks the book a cost is resolved from for that supplier and
            currency. A tenant has at most one per pair; declaring a second answers
            409.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CostBookOut | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
