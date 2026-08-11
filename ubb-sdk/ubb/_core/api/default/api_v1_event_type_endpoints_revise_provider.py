from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.provider_out import ProviderOut
from ...models.provider_update_in import ProviderUpdateIn
from typing import cast



def _get_kwargs(
    key: str,
    *,
    body: ProviderUpdateIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v1/providers/{key}".format(key=quote(str(key), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | ProviderOut | None:
    if response.status_code == 200:
        response_200 = ProviderOut.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | ProviderOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    key: str,
    *,
    client: AuthenticatedClient,
    body: ProviderUpdateIn,

) -> Response[ProblemOut | ProviderOut]:
    """ Revise Provider

     Rename a supplier, or retire one — two acts, recorded apart.

    There is no delete. Supplier COGS attribution keys on this record's
    identity, so removing one would silently rewrite what historical postings
    say they cost — the failure a finance owner finds a quarter later and
    cannot repair. Renaming is safe for exactly the same reason the identity is
    not the key: nothing downstream holds the handle.

    Retirement records ``provider.retired`` rather than a second
    ``provider.declared``, because it is a commercial decision to stop offering
    a supplier and not a correction to a name. Where one request does both, the
    retirement is what the ledger is told: it is the consequential half.

    Args:
        key (str):
        body (ProviderUpdateIn): Rename or retire a supplier.

            There is no delete, here or anywhere: a Provider is retired and never
            removed, because supplier COGS attribution keys on its identity and
            deleting one would silently rewrite what historical postings say they cost.
            `retired` is a two-way switch rather than a timestamp a caller supplies —
            WHEN a supplier was retired is UBB's record of an act, not an input.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ProviderOut]
     """


    kwargs = _get_kwargs(
        key=key,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    key: str,
    *,
    client: AuthenticatedClient,
    body: ProviderUpdateIn,

) -> ProblemOut | ProviderOut | None:
    """ Revise Provider

     Rename a supplier, or retire one — two acts, recorded apart.

    There is no delete. Supplier COGS attribution keys on this record's
    identity, so removing one would silently rewrite what historical postings
    say they cost — the failure a finance owner finds a quarter later and
    cannot repair. Renaming is safe for exactly the same reason the identity is
    not the key: nothing downstream holds the handle.

    Retirement records ``provider.retired`` rather than a second
    ``provider.declared``, because it is a commercial decision to stop offering
    a supplier and not a correction to a name. Where one request does both, the
    retirement is what the ledger is told: it is the consequential half.

    Args:
        key (str):
        body (ProviderUpdateIn): Rename or retire a supplier.

            There is no delete, here or anywhere: a Provider is retired and never
            removed, because supplier COGS attribution keys on its identity and
            deleting one would silently rewrite what historical postings say they cost.
            `retired` is a two-way switch rather than a timestamp a caller supplies —
            WHEN a supplier was retired is UBB's record of an act, not an input.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ProviderOut
     """


    return sync_detailed(
        key=key,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    key: str,
    *,
    client: AuthenticatedClient,
    body: ProviderUpdateIn,

) -> Response[ProblemOut | ProviderOut]:
    """ Revise Provider

     Rename a supplier, or retire one — two acts, recorded apart.

    There is no delete. Supplier COGS attribution keys on this record's
    identity, so removing one would silently rewrite what historical postings
    say they cost — the failure a finance owner finds a quarter later and
    cannot repair. Renaming is safe for exactly the same reason the identity is
    not the key: nothing downstream holds the handle.

    Retirement records ``provider.retired`` rather than a second
    ``provider.declared``, because it is a commercial decision to stop offering
    a supplier and not a correction to a name. Where one request does both, the
    retirement is what the ledger is told: it is the consequential half.

    Args:
        key (str):
        body (ProviderUpdateIn): Rename or retire a supplier.

            There is no delete, here or anywhere: a Provider is retired and never
            removed, because supplier COGS attribution keys on its identity and
            deleting one would silently rewrite what historical postings say they cost.
            `retired` is a two-way switch rather than a timestamp a caller supplies —
            WHEN a supplier was retired is UBB's record of an act, not an input.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ProviderOut]
     """


    kwargs = _get_kwargs(
        key=key,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    key: str,
    *,
    client: AuthenticatedClient,
    body: ProviderUpdateIn,

) -> ProblemOut | ProviderOut | None:
    """ Revise Provider

     Rename a supplier, or retire one — two acts, recorded apart.

    There is no delete. Supplier COGS attribution keys on this record's
    identity, so removing one would silently rewrite what historical postings
    say they cost — the failure a finance owner finds a quarter later and
    cannot repair. Renaming is safe for exactly the same reason the identity is
    not the key: nothing downstream holds the handle.

    Retirement records ``provider.retired`` rather than a second
    ``provider.declared``, because it is a commercial decision to stop offering
    a supplier and not a correction to a name. Where one request does both, the
    retirement is what the ledger is told: it is the consequential half.

    Args:
        key (str):
        body (ProviderUpdateIn): Rename or retire a supplier.

            There is no delete, here or anywhere: a Provider is retired and never
            removed, because supplier COGS attribution keys on its identity and
            deleting one would silently rewrite what historical postings say they cost.
            `retired` is a two-way switch rather than a timestamp a caller supplies —
            WHEN a supplier was retired is UBB's record of an act, not an input.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ProviderOut
     """


    return (await asyncio_detailed(
        key=key,
client=client,
body=body,

    )).parsed
