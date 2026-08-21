from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.pricing_book_in import PricingBookIn
from ...models.pricing_book_out import PricingBookOut
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    *,
    body: PricingBookIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/pricing-books",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> PricingBookOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = PricingBookOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[PricingBookOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: PricingBookIn,

) -> Response[PricingBookOut | ProblemOut]:
    """ Declare Pricing Book

     Declare a Pricing Book: a catalogue of what this tenant charges.

    It arrives EMPTY. UBB ships no catalogue — no starter rules, no default
    rule set, no seeded markup — so a book prices nothing until rules are
    published into it and every event falls past it to the markup rung.

    A book names neither a supplier nor a currency; see the request schema for
    why. Declarations dedupe on natural identity: a second book under the same
    key, or a second default, answers 409.

    Args:
        body (PricingBookIn): Declare a Pricing Book: a catalogue of what this tenant charges.

            It names neither a supplier nor a currency, and both absences are
            deliberate. A tenant's price for a unit of work does not change because
            they switched supplier, and a tenant has exactly one currency
            (per-tenant single currency; multi-currency and FX are not supported), so
            a book that repeated either would be repeating a decision made elsewhere.
            A rule that should price one supplier's work differently pins `provider`
            as a selector, which is where that belongs.

            `is_default` marks the book a customer is priced from when nothing
            narrower applies. A tenant has at most one; declaring a second answers
            409.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PricingBookOut | ProblemOut]
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
    body: PricingBookIn,

) -> PricingBookOut | ProblemOut | None:
    """ Declare Pricing Book

     Declare a Pricing Book: a catalogue of what this tenant charges.

    It arrives EMPTY. UBB ships no catalogue — no starter rules, no default
    rule set, no seeded markup — so a book prices nothing until rules are
    published into it and every event falls past it to the markup rung.

    A book names neither a supplier nor a currency; see the request schema for
    why. Declarations dedupe on natural identity: a second book under the same
    key, or a second default, answers 409.

    Args:
        body (PricingBookIn): Declare a Pricing Book: a catalogue of what this tenant charges.

            It names neither a supplier nor a currency, and both absences are
            deliberate. A tenant's price for a unit of work does not change because
            they switched supplier, and a tenant has exactly one currency
            (per-tenant single currency; multi-currency and FX are not supported), so
            a book that repeated either would be repeating a decision made elsewhere.
            A rule that should price one supplier's work differently pins `provider`
            as a selector, which is where that belongs.

            `is_default` marks the book a customer is priced from when nothing
            narrower applies. A tenant has at most one; declaring a second answers
            409.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PricingBookOut | ProblemOut
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: PricingBookIn,

) -> Response[PricingBookOut | ProblemOut]:
    """ Declare Pricing Book

     Declare a Pricing Book: a catalogue of what this tenant charges.

    It arrives EMPTY. UBB ships no catalogue — no starter rules, no default
    rule set, no seeded markup — so a book prices nothing until rules are
    published into it and every event falls past it to the markup rung.

    A book names neither a supplier nor a currency; see the request schema for
    why. Declarations dedupe on natural identity: a second book under the same
    key, or a second default, answers 409.

    Args:
        body (PricingBookIn): Declare a Pricing Book: a catalogue of what this tenant charges.

            It names neither a supplier nor a currency, and both absences are
            deliberate. A tenant's price for a unit of work does not change because
            they switched supplier, and a tenant has exactly one currency
            (per-tenant single currency; multi-currency and FX are not supported), so
            a book that repeated either would be repeating a decision made elsewhere.
            A rule that should price one supplier's work differently pins `provider`
            as a selector, which is where that belongs.

            `is_default` marks the book a customer is priced from when nothing
            narrower applies. A tenant has at most one; declaring a second answers
            409.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PricingBookOut | ProblemOut]
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
    body: PricingBookIn,

) -> PricingBookOut | ProblemOut | None:
    """ Declare Pricing Book

     Declare a Pricing Book: a catalogue of what this tenant charges.

    It arrives EMPTY. UBB ships no catalogue — no starter rules, no default
    rule set, no seeded markup — so a book prices nothing until rules are
    published into it and every event falls past it to the markup rung.

    A book names neither a supplier nor a currency; see the request schema for
    why. Declarations dedupe on natural identity: a second book under the same
    key, or a second default, answers 409.

    Args:
        body (PricingBookIn): Declare a Pricing Book: a catalogue of what this tenant charges.

            It names neither a supplier nor a currency, and both absences are
            deliberate. A tenant's price for a unit of work does not change because
            they switched supplier, and a tenant has exactly one currency
            (per-tenant single currency; multi-currency and FX are not supported), so
            a book that repeated either would be repeating a decision made elsewhere.
            A rule that should price one supplier's work differently pins `provider`
            as a selector, which is where that belongs.

            `is_default` marks the book a customer is priced from when nothing
            narrower applies. A tenant has at most one; declaring a second answers
            409.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PricingBookOut | ProblemOut
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
