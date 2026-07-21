from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.usage_summary_response import UsageSummaryResponse
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/me/usage-summary",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> UsageSummaryResponse | None:
    if response.status_code == 200:
        response_200 = UsageSummaryResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[UsageSummaryResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[UsageSummaryResponse]:
    """ Get Usage Summary

     Month-to-date usage rollup for the calling end customer.

    Window: current UTC calendar month-to-date (house convention — first of
    month through today inclusive; period_end is the exclusive day bound).

    Deliberately NO billing-owner gate (unlike /me/usage-invoices): usage
    attribution is per-seat by design, so a pooled seat sees only its OWN
    consumption here and leaks nothing about its siblings — there is no
    consolidated money amount to protect. A BUSINESS token aggregates across
    its seats (the same seat basis its consolidated invoice bills on).
    Metering-scoped, not billing-scoped: a meter-only tenant's customers can
    still see what they consumed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UsageSummaryResponse]
     """


    kwargs = _get_kwargs(
        
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,

) -> UsageSummaryResponse | None:
    """ Get Usage Summary

     Month-to-date usage rollup for the calling end customer.

    Window: current UTC calendar month-to-date (house convention — first of
    month through today inclusive; period_end is the exclusive day bound).

    Deliberately NO billing-owner gate (unlike /me/usage-invoices): usage
    attribution is per-seat by design, so a pooled seat sees only its OWN
    consumption here and leaks nothing about its siblings — there is no
    consolidated money amount to protect. A BUSINESS token aggregates across
    its seats (the same seat basis its consolidated invoice bills on).
    Metering-scoped, not billing-scoped: a meter-only tenant's customers can
    still see what they consumed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UsageSummaryResponse
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[UsageSummaryResponse]:
    """ Get Usage Summary

     Month-to-date usage rollup for the calling end customer.

    Window: current UTC calendar month-to-date (house convention — first of
    month through today inclusive; period_end is the exclusive day bound).

    Deliberately NO billing-owner gate (unlike /me/usage-invoices): usage
    attribution is per-seat by design, so a pooled seat sees only its OWN
    consumption here and leaks nothing about its siblings — there is no
    consolidated money amount to protect. A BUSINESS token aggregates across
    its seats (the same seat basis its consolidated invoice bills on).
    Metering-scoped, not billing-scoped: a meter-only tenant's customers can
    still see what they consumed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UsageSummaryResponse]
     """


    kwargs = _get_kwargs(
        
    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,

) -> UsageSummaryResponse | None:
    """ Get Usage Summary

     Month-to-date usage rollup for the calling end customer.

    Window: current UTC calendar month-to-date (house convention — first of
    month through today inclusive; period_end is the exclusive day bound).

    Deliberately NO billing-owner gate (unlike /me/usage-invoices): usage
    attribution is per-seat by design, so a pooled seat sees only its OWN
    consumption here and leaks nothing about its siblings — there is no
    consolidated money amount to protect. A BUSINESS token aggregates across
    its seats (the same seat basis its consolidated invoice bills on).
    Metering-scoped, not billing-scoped: a meter-only tenant's customers can
    still see what they consumed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UsageSummaryResponse
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
