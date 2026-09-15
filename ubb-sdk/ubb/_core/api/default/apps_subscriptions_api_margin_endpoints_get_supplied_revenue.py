from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.apps_subscriptions_api_margin_endpoints_get_supplied_revenue_basis_type_0 import AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0
from ...models.problem_out import ProblemOut
from ...models.supplied_revenue_window_out import SuppliedRevenueWindowOut
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime



def _get_kwargs(
    customer_id: UUID,
    *,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    basis: AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_start_date: None | str | Unset
    if isinstance(start_date, Unset):
        json_start_date = UNSET
    elif isinstance(start_date, datetime.date):
        json_start_date = start_date.isoformat()
    else:
        json_start_date = start_date
    params["start_date"] = json_start_date

    json_end_date: None | str | Unset
    if isinstance(end_date, Unset):
        json_end_date = UNSET
    elif isinstance(end_date, datetime.date):
        json_end_date = end_date.isoformat()
    else:
        json_end_date = end_date
    params["end_date"] = json_end_date

    json_basis: None | str | Unset
    if isinstance(basis, Unset):
        json_basis = UNSET
    elif isinstance(basis, AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0):
        json_basis = basis.value
    else:
        json_basis = basis
    params["basis"] = json_basis


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/margin/customers/{customer_id}/supplied-revenue".format(customer_id=quote(str(customer_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | SuppliedRevenueWindowOut | None:
    if response.status_code == 200:
        response_200 = SuppliedRevenueWindowOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | SuppliedRevenueWindowOut]:
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
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    basis: AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset = UNSET,

) -> Response[ProblemOut | SuppliedRevenueWindowOut]:
    r""" Get Supplied Revenue

     The window's supplied revenue, under a basis the response names.

    ⚠ **THE BASIS PARAMETER CARRIES ITS CONCEPT'S MARKER, which is the
    OPPOSITE of the ruling on the unit-of-work listing's `status` filter**
    (`tests/contracts/test_openapi_known_values.py`), and the difference is
    worth stating because the two look alike. There the marker was declined
    because it would have NARROWED what a caller may send — turning a mistyped
    filter into a 422 where it was an empty page. Here the route already
    refuses a basis the registry does not declare, below, and would have to:
    there is no honest answer to \"state this figure on a basis I have
    invented\". So the marker documents a refusal the server already makes
    rather than introducing one, which is exactly when ADR-0007 §3 wants it.

    **`known` MEANS A SUPPLIED FIGURE IS ATTRIBUTABLE TO THIS WINDOW, NOT THAT
    THE WINDOW IS FULLY COVERED.** That is a real limit and it is stated rather
    than papered over: UBB cannot tell a month the tenant has not got round to
    supplying from a month in which the customer generated nothing, so \"fully
    covered\" is not a fact available to it. What the caller gets instead is the
    contributing records themselves, each with its own period — so the coverage
    is readable from the answer rather than asserted by a status that cannot
    know it.

    Args:
        customer_id (UUID):
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        basis (AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | SuppliedRevenueWindowOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
start_date=start_date,
end_date=end_date,
basis=basis,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    basis: AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset = UNSET,

) -> ProblemOut | SuppliedRevenueWindowOut | None:
    r""" Get Supplied Revenue

     The window's supplied revenue, under a basis the response names.

    ⚠ **THE BASIS PARAMETER CARRIES ITS CONCEPT'S MARKER, which is the
    OPPOSITE of the ruling on the unit-of-work listing's `status` filter**
    (`tests/contracts/test_openapi_known_values.py`), and the difference is
    worth stating because the two look alike. There the marker was declined
    because it would have NARROWED what a caller may send — turning a mistyped
    filter into a 422 where it was an empty page. Here the route already
    refuses a basis the registry does not declare, below, and would have to:
    there is no honest answer to \"state this figure on a basis I have
    invented\". So the marker documents a refusal the server already makes
    rather than introducing one, which is exactly when ADR-0007 §3 wants it.

    **`known` MEANS A SUPPLIED FIGURE IS ATTRIBUTABLE TO THIS WINDOW, NOT THAT
    THE WINDOW IS FULLY COVERED.** That is a real limit and it is stated rather
    than papered over: UBB cannot tell a month the tenant has not got round to
    supplying from a month in which the customer generated nothing, so \"fully
    covered\" is not a fact available to it. What the caller gets instead is the
    contributing records themselves, each with its own period — so the coverage
    is readable from the answer rather than asserted by a status that cannot
    know it.

    Args:
        customer_id (UUID):
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        basis (AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | SuppliedRevenueWindowOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
start_date=start_date,
end_date=end_date,
basis=basis,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    basis: AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset = UNSET,

) -> Response[ProblemOut | SuppliedRevenueWindowOut]:
    r""" Get Supplied Revenue

     The window's supplied revenue, under a basis the response names.

    ⚠ **THE BASIS PARAMETER CARRIES ITS CONCEPT'S MARKER, which is the
    OPPOSITE of the ruling on the unit-of-work listing's `status` filter**
    (`tests/contracts/test_openapi_known_values.py`), and the difference is
    worth stating because the two look alike. There the marker was declined
    because it would have NARROWED what a caller may send — turning a mistyped
    filter into a 422 where it was an empty page. Here the route already
    refuses a basis the registry does not declare, below, and would have to:
    there is no honest answer to \"state this figure on a basis I have
    invented\". So the marker documents a refusal the server already makes
    rather than introducing one, which is exactly when ADR-0007 §3 wants it.

    **`known` MEANS A SUPPLIED FIGURE IS ATTRIBUTABLE TO THIS WINDOW, NOT THAT
    THE WINDOW IS FULLY COVERED.** That is a real limit and it is stated rather
    than papered over: UBB cannot tell a month the tenant has not got round to
    supplying from a month in which the customer generated nothing, so \"fully
    covered\" is not a fact available to it. What the caller gets instead is the
    contributing records themselves, each with its own period — so the coverage
    is readable from the answer rather than asserted by a status that cannot
    know it.

    Args:
        customer_id (UUID):
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        basis (AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | SuppliedRevenueWindowOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
start_date=start_date,
end_date=end_date,
basis=basis,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    start_date: datetime.date | None | Unset = UNSET,
    end_date: datetime.date | None | Unset = UNSET,
    basis: AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset = UNSET,

) -> ProblemOut | SuppliedRevenueWindowOut | None:
    r""" Get Supplied Revenue

     The window's supplied revenue, under a basis the response names.

    ⚠ **THE BASIS PARAMETER CARRIES ITS CONCEPT'S MARKER, which is the
    OPPOSITE of the ruling on the unit-of-work listing's `status` filter**
    (`tests/contracts/test_openapi_known_values.py`), and the difference is
    worth stating because the two look alike. There the marker was declined
    because it would have NARROWED what a caller may send — turning a mistyped
    filter into a 422 where it was an empty page. Here the route already
    refuses a basis the registry does not declare, below, and would have to:
    there is no honest answer to \"state this figure on a basis I have
    invented\". So the marker documents a refusal the server already makes
    rather than introducing one, which is exactly when ADR-0007 §3 wants it.

    **`known` MEANS A SUPPLIED FIGURE IS ATTRIBUTABLE TO THIS WINDOW, NOT THAT
    THE WINDOW IS FULLY COVERED.** That is a real limit and it is stated rather
    than papered over: UBB cannot tell a month the tenant has not got round to
    supplying from a month in which the customer generated nothing, so \"fully
    covered\" is not a fact available to it. What the caller gets instead is the
    contributing records themselves, each with its own period — so the coverage
    is readable from the answer rather than asserted by a status that cannot
    know it.

    Args:
        customer_id (UUID):
        start_date (datetime.date | None | Unset):
        end_date (datetime.date | None | Unset):
        basis (AppsSubscriptionsApiMarginEndpointsGetSuppliedRevenueBasisType0 | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | SuppliedRevenueWindowOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
start_date=start_date,
end_date=end_date,
basis=basis,

    )).parsed
