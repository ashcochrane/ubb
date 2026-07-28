from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.me_balance_response import MeBalanceResponse
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/me/balance",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> MeBalanceResponse | None:
    if response.status_code == 200:
        response_200 = MeBalanceResponse.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[MeBalanceResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[MeBalanceResponse]:
    r""" Get Balance

     A pooled seat's balance IS the billing owner's (Task 9 finding B):
    Task 8c's ``lock_for_billing`` ratchet refuses to let a wallet exist on
    a seat id at all, and ``start_top_up`` pins every top-up's credit to
    ``customer.resolve_billing_owner()`` — so a seat's OWN wallet row can
    never exist, even right after that seat pays. Reading ``customer``
    directly here used to 404 into a fabricated ``balance_micros: 0`` that
    never changed no matter how much the seat topped up. Resolve to the
    owner instead, exactly like the tenant surface's GET
    /billing/customers/{id}/balance, and disclose ownership
    (``is_pooled_seat`` / ``billing_owner_external_id``, the same two
    fields that surface already returns) so the widget can label the number
    \"your business's balance\" rather than implying it is the seat's own.

    This does NOT extend to /me/grants or /me/transactions below: those are
    ITEMIZED lists (individual lots/lines with amounts and timing), and
    resolving them to the owner would show one seat every sibling seat's
    financial activity — the exact leak their docstrings are written to
    avoid. A balance is one aggregate number, not sibling-attributed detail,
    so disclosing it does not cross the same privacy line.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MeBalanceResponse]
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

) -> MeBalanceResponse | None:
    r""" Get Balance

     A pooled seat's balance IS the billing owner's (Task 9 finding B):
    Task 8c's ``lock_for_billing`` ratchet refuses to let a wallet exist on
    a seat id at all, and ``start_top_up`` pins every top-up's credit to
    ``customer.resolve_billing_owner()`` — so a seat's OWN wallet row can
    never exist, even right after that seat pays. Reading ``customer``
    directly here used to 404 into a fabricated ``balance_micros: 0`` that
    never changed no matter how much the seat topped up. Resolve to the
    owner instead, exactly like the tenant surface's GET
    /billing/customers/{id}/balance, and disclose ownership
    (``is_pooled_seat`` / ``billing_owner_external_id``, the same two
    fields that surface already returns) so the widget can label the number
    \"your business's balance\" rather than implying it is the seat's own.

    This does NOT extend to /me/grants or /me/transactions below: those are
    ITEMIZED lists (individual lots/lines with amounts and timing), and
    resolving them to the owner would show one seat every sibling seat's
    financial activity — the exact leak their docstrings are written to
    avoid. A balance is one aggregate number, not sibling-attributed detail,
    so disclosing it does not cross the same privacy line.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MeBalanceResponse
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[MeBalanceResponse]:
    r""" Get Balance

     A pooled seat's balance IS the billing owner's (Task 9 finding B):
    Task 8c's ``lock_for_billing`` ratchet refuses to let a wallet exist on
    a seat id at all, and ``start_top_up`` pins every top-up's credit to
    ``customer.resolve_billing_owner()`` — so a seat's OWN wallet row can
    never exist, even right after that seat pays. Reading ``customer``
    directly here used to 404 into a fabricated ``balance_micros: 0`` that
    never changed no matter how much the seat topped up. Resolve to the
    owner instead, exactly like the tenant surface's GET
    /billing/customers/{id}/balance, and disclose ownership
    (``is_pooled_seat`` / ``billing_owner_external_id``, the same two
    fields that surface already returns) so the widget can label the number
    \"your business's balance\" rather than implying it is the seat's own.

    This does NOT extend to /me/grants or /me/transactions below: those are
    ITEMIZED lists (individual lots/lines with amounts and timing), and
    resolving them to the owner would show one seat every sibling seat's
    financial activity — the exact leak their docstrings are written to
    avoid. A balance is one aggregate number, not sibling-attributed detail,
    so disclosing it does not cross the same privacy line.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MeBalanceResponse]
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

) -> MeBalanceResponse | None:
    r""" Get Balance

     A pooled seat's balance IS the billing owner's (Task 9 finding B):
    Task 8c's ``lock_for_billing`` ratchet refuses to let a wallet exist on
    a seat id at all, and ``start_top_up`` pins every top-up's credit to
    ``customer.resolve_billing_owner()`` — so a seat's OWN wallet row can
    never exist, even right after that seat pays. Reading ``customer``
    directly here used to 404 into a fabricated ``balance_micros: 0`` that
    never changed no matter how much the seat topped up. Resolve to the
    owner instead, exactly like the tenant surface's GET
    /billing/customers/{id}/balance, and disclose ownership
    (``is_pooled_seat`` / ``billing_owner_external_id``, the same two
    fields that surface already returns) so the widget can label the number
    \"your business's balance\" rather than implying it is the seat's own.

    This does NOT extend to /me/grants or /me/transactions below: those are
    ITEMIZED lists (individual lots/lines with amounts and timing), and
    resolving them to the owner would show one seat every sibling seat's
    financial activity — the exact leak their docstrings are written to
    avoid. A balance is one aggregate number, not sibling-attributed detail,
    so disclosing it does not cross the same privacy line.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MeBalanceResponse
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
