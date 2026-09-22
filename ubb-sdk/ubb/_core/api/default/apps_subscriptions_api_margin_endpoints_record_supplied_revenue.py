from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.tenant_supplied_revenue_in import TenantSuppliedRevenueIn
from ...models.tenant_supplied_revenue_out import TenantSuppliedRevenueOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,
    *,
    body: TenantSuppliedRevenueIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/margin/customers/{customer_id}/supplied-revenue".format(customer_id=quote(str(customer_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | TenantSuppliedRevenueOut | None:
    if response.status_code == 200:
        response_200 = TenantSuppliedRevenueOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | TenantSuppliedRevenueOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: TenantSuppliedRevenueIn,

) -> Response[ProblemOut | TenantSuppliedRevenueOut]:
    """ Record Supplied Revenue

     Record what one customer paid you for one period, billed somewhere UBB
    cannot see.

    **The figure is the whole revenue for that customer and that period — not
    an addition to what UBB priced.** Where UBB also priced the customer's usage
    inside the period, `/metering/analytics/economics` states this figure as
    the revenue and leaves that usage's price out of it, and usage nobody
    priced there no longer makes the revenue incomplete. A Stripe subscription
    is added as before and is not affected.

    `period_end` is exclusive. Omit it for revenue that is an instant rather
    than a span: such a figure covers no period, so it is counted beside the
    usage in the window it lands in rather than instead of it. Recording again
    for the same customer, `period_start` and `source_reference` re-states the
    figure; a different `source_reference` records a second figure beside it,
    and figures whose periods overlap both count — two invoices covering one
    month are two facts.

    Args:
        customer_id (UUID):
        body (TenantSuppliedRevenueIn): What a tenant states it earned from one customer over one
            period.

            ⚠ **NOT A CHARGE.** UBB neither created nor invoiced this money; the tenant
            bills its customers somewhere UBB cannot see and is supplying the figure so
            that margin can be computed at the scope it was supplied at.

            **THE WHOLE REVENUE FOR THAT CUSTOMER AND PERIOD, NOT AN ADDITION TO WHAT
            UBB PRICED** (#537). Where UBB also priced the customer's usage inside the
            period, the figure replaces that usage's revenue rather than adding to it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | TenantSuppliedRevenueOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: TenantSuppliedRevenueIn,

) -> ProblemOut | TenantSuppliedRevenueOut | None:
    """ Record Supplied Revenue

     Record what one customer paid you for one period, billed somewhere UBB
    cannot see.

    **The figure is the whole revenue for that customer and that period — not
    an addition to what UBB priced.** Where UBB also priced the customer's usage
    inside the period, `/metering/analytics/economics` states this figure as
    the revenue and leaves that usage's price out of it, and usage nobody
    priced there no longer makes the revenue incomplete. A Stripe subscription
    is added as before and is not affected.

    `period_end` is exclusive. Omit it for revenue that is an instant rather
    than a span: such a figure covers no period, so it is counted beside the
    usage in the window it lands in rather than instead of it. Recording again
    for the same customer, `period_start` and `source_reference` re-states the
    figure; a different `source_reference` records a second figure beside it,
    and figures whose periods overlap both count — two invoices covering one
    month are two facts.

    Args:
        customer_id (UUID):
        body (TenantSuppliedRevenueIn): What a tenant states it earned from one customer over one
            period.

            ⚠ **NOT A CHARGE.** UBB neither created nor invoiced this money; the tenant
            bills its customers somewhere UBB cannot see and is supplying the figure so
            that margin can be computed at the scope it was supplied at.

            **THE WHOLE REVENUE FOR THAT CUSTOMER AND PERIOD, NOT AN ADDITION TO WHAT
            UBB PRICED** (#537). Where UBB also priced the customer's usage inside the
            period, the figure replaces that usage's revenue rather than adding to it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | TenantSuppliedRevenueOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: TenantSuppliedRevenueIn,

) -> Response[ProblemOut | TenantSuppliedRevenueOut]:
    """ Record Supplied Revenue

     Record what one customer paid you for one period, billed somewhere UBB
    cannot see.

    **The figure is the whole revenue for that customer and that period — not
    an addition to what UBB priced.** Where UBB also priced the customer's usage
    inside the period, `/metering/analytics/economics` states this figure as
    the revenue and leaves that usage's price out of it, and usage nobody
    priced there no longer makes the revenue incomplete. A Stripe subscription
    is added as before and is not affected.

    `period_end` is exclusive. Omit it for revenue that is an instant rather
    than a span: such a figure covers no period, so it is counted beside the
    usage in the window it lands in rather than instead of it. Recording again
    for the same customer, `period_start` and `source_reference` re-states the
    figure; a different `source_reference` records a second figure beside it,
    and figures whose periods overlap both count — two invoices covering one
    month are two facts.

    Args:
        customer_id (UUID):
        body (TenantSuppliedRevenueIn): What a tenant states it earned from one customer over one
            period.

            ⚠ **NOT A CHARGE.** UBB neither created nor invoiced this money; the tenant
            bills its customers somewhere UBB cannot see and is supplying the figure so
            that margin can be computed at the scope it was supplied at.

            **THE WHOLE REVENUE FOR THAT CUSTOMER AND PERIOD, NOT AN ADDITION TO WHAT
            UBB PRICED** (#537). Where UBB also priced the customer's usage inside the
            period, the figure replaces that usage's revenue rather than adding to it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | TenantSuppliedRevenueOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    body: TenantSuppliedRevenueIn,

) -> ProblemOut | TenantSuppliedRevenueOut | None:
    """ Record Supplied Revenue

     Record what one customer paid you for one period, billed somewhere UBB
    cannot see.

    **The figure is the whole revenue for that customer and that period — not
    an addition to what UBB priced.** Where UBB also priced the customer's usage
    inside the period, `/metering/analytics/economics` states this figure as
    the revenue and leaves that usage's price out of it, and usage nobody
    priced there no longer makes the revenue incomplete. A Stripe subscription
    is added as before and is not affected.

    `period_end` is exclusive. Omit it for revenue that is an instant rather
    than a span: such a figure covers no period, so it is counted beside the
    usage in the window it lands in rather than instead of it. Recording again
    for the same customer, `period_start` and `source_reference` re-states the
    figure; a different `source_reference` records a second figure beside it,
    and figures whose periods overlap both count — two invoices covering one
    month are two facts.

    Args:
        customer_id (UUID):
        body (TenantSuppliedRevenueIn): What a tenant states it earned from one customer over one
            period.

            ⚠ **NOT A CHARGE.** UBB neither created nor invoiced this money; the tenant
            bills its customers somewhere UBB cannot see and is supplying the figure so
            that margin can be computed at the scope it was supplied at.

            **THE WHOLE REVENUE FOR THAT CUSTOMER AND PERIOD, NOT AN ADDITION TO WHAT
            UBB PRICED** (#537). Where UBB also priced the customer's usage inside the
            period, the figure replaces that usage's revenue rather than adding to it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | TenantSuppliedRevenueOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
body=body,

    )).parsed
