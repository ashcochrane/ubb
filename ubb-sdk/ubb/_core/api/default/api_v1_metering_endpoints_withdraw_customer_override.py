from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.book_publish_out import BookPublishOut
from ...models.problem_out import ProblemOut
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime



def _get_kwargs(
    customer_id: UUID,
    override_id: UUID,
    *,
    effective_at: datetime.datetime | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_effective_at: None | str | Unset
    if isinstance(effective_at, Unset):
        json_effective_at = UNSET
    elif isinstance(effective_at, datetime.datetime):
        json_effective_at = effective_at.isoformat()
    else:
        json_effective_at = effective_at
    params["effective_at"] = json_effective_at


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/metering/pricing/customers/{customer_id}/overrides/{override_id}".format(customer_id=quote(str(customer_id), safe=""),override_id=quote(str(override_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> BookPublishOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = BookPublishOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[BookPublishOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    customer_id: UUID,
    override_id: UUID,
    *,
    client: AuthenticatedClient,
    effective_at: datetime.datetime | None | Unset = UNSET,

) -> Response[BookPublishOut | ProblemOut]:
    """ Withdraw Customer Override

     Withdraw one of a customer's own rules: they go back to inheriting.

    **This writes no rule either.** It declares a draft retiring the override
    on the customer's own book, and publishing that draft is what ends the
    deal. Retiring an override reopens nothing and revives nothing — the rule
    the customer inherits was there all along, out-ranked, and starts
    answering again the moment it is not.

    `effective_at` dates the withdrawal forward under the same bounds a publish
    takes, and omitting it means now.

    Args:
        customer_id (UUID):
        override_id (UUID):
        effective_at (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookPublishOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
override_id=override_id,
effective_at=effective_at,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    override_id: UUID,
    *,
    client: AuthenticatedClient,
    effective_at: datetime.datetime | None | Unset = UNSET,

) -> BookPublishOut | ProblemOut | None:
    """ Withdraw Customer Override

     Withdraw one of a customer's own rules: they go back to inheriting.

    **This writes no rule either.** It declares a draft retiring the override
    on the customer's own book, and publishing that draft is what ends the
    deal. Retiring an override reopens nothing and revives nothing — the rule
    the customer inherits was there all along, out-ranked, and starts
    answering again the moment it is not.

    `effective_at` dates the withdrawal forward under the same bounds a publish
    takes, and omitting it means now.

    Args:
        customer_id (UUID):
        override_id (UUID):
        effective_at (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookPublishOut | ProblemOut
     """


    return sync_detailed(
        customer_id=customer_id,
override_id=override_id,
client=client,
effective_at=effective_at,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    override_id: UUID,
    *,
    client: AuthenticatedClient,
    effective_at: datetime.datetime | None | Unset = UNSET,

) -> Response[BookPublishOut | ProblemOut]:
    """ Withdraw Customer Override

     Withdraw one of a customer's own rules: they go back to inheriting.

    **This writes no rule either.** It declares a draft retiring the override
    on the customer's own book, and publishing that draft is what ends the
    deal. Retiring an override reopens nothing and revives nothing — the rule
    the customer inherits was there all along, out-ranked, and starts
    answering again the moment it is not.

    `effective_at` dates the withdrawal forward under the same bounds a publish
    takes, and omitting it means now.

    Args:
        customer_id (UUID):
        override_id (UUID):
        effective_at (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookPublishOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
override_id=override_id,
effective_at=effective_at,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    override_id: UUID,
    *,
    client: AuthenticatedClient,
    effective_at: datetime.datetime | None | Unset = UNSET,

) -> BookPublishOut | ProblemOut | None:
    """ Withdraw Customer Override

     Withdraw one of a customer's own rules: they go back to inheriting.

    **This writes no rule either.** It declares a draft retiring the override
    on the customer's own book, and publishing that draft is what ends the
    deal. Retiring an override reopens nothing and revives nothing — the rule
    the customer inherits was there all along, out-ranked, and starts
    answering again the moment it is not.

    `effective_at` dates the withdrawal forward under the same bounds a publish
    takes, and omitting it means now.

    Args:
        customer_id (UUID):
        override_id (UUID):
        effective_at (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookPublishOut | ProblemOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
override_id=override_id,
client=client,
effective_at=effective_at,

    )).parsed
