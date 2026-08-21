from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.book_publish_out import BookPublishOut
from ...models.customer_override_in import CustomerOverrideIn
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    customer_id: UUID,
    *,
    body: CustomerOverrideIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/customers/{customer_id}/overrides".format(customer_id=quote(str(customer_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    *,
    client: AuthenticatedClient,
    body: CustomerOverrideIn,

) -> Response[BookPublishOut | ProblemOut]:
    """ Declare Customer Override

     Declare one customer's own pricing rule, as a draft.

    The override states a WHOLE rule — the quantity it prices, the selectors it
    pins, how it derives its price and what it charges — and replaces whatever
    this customer inherits for that rule. Nothing is inherited into it: a field
    left out takes the rule defaults, never the superseded rule's value, so a
    customer moved from a margin over cost onto a flat price is stated in one
    body. `GET /pricing/customers/{customer_id}/inherited-rule` answers what
    they get today, which is what a client offers as the starting point.

    **This writes no rule.** It declares a draft on the customer's own book,
    exactly as a change to any other book is declared, and publishing it
    through `POST /pricing/books/{book_id}/publishes/{publish_id}/publish`
    is what puts the deal in force. The response carries that book's id and the
    diff.

    `effective_at` dates the override forward and omitting it means now, under
    the bounds every publish takes: timezone-aware (`effective_at_naive`), not
    in the past (`effective_at_in_past`), within 366 days
    (`effective_at_too_far_ahead`), and at or after the latest boundary already
    scheduled on this customer's book
    (`effective_at_before_scheduled_boundary`).

    Args:
        customer_id (UUID):
        body (CustomerOverrideIn): The rule this customer gets, and when it takes effect.

            **A COMPLETE RULE, WHICH IS THE WHOLE RULING.** Every field a rule has is
            stated here: the quantity it prices, the selectors it pins, how it derives
            its price and what it charges. There is no field naming a rule to inherit
            from and no field that takes a value while leaving a method behind —
            **partial override is not expressible on this surface**, because a rule
            whose method comes from one record and whose value comes from another
            cannot be explained by naming one rule, which is the property the receipt
            design rests on (#151 §6.2).

            **THIS BODY NAMES NO ACT.** It carries no `kind`, unlike a change to a
            book: declaring an override adds a rule and withdrawing one retires it, and
            which of the two is happening is the route you called.

            `effective_at` dates the override forward and omitting it means now, under
            exactly the bounds a publish takes, because this IS a publish: it is
            declared as a draft on the customer's own book, published through the
            book's own route, and reversed by a further publish. There is no
            immediate-effect path to an override and no second mutation surface for one.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookPublishOut | ProblemOut]
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
    body: CustomerOverrideIn,

) -> BookPublishOut | ProblemOut | None:
    """ Declare Customer Override

     Declare one customer's own pricing rule, as a draft.

    The override states a WHOLE rule — the quantity it prices, the selectors it
    pins, how it derives its price and what it charges — and replaces whatever
    this customer inherits for that rule. Nothing is inherited into it: a field
    left out takes the rule defaults, never the superseded rule's value, so a
    customer moved from a margin over cost onto a flat price is stated in one
    body. `GET /pricing/customers/{customer_id}/inherited-rule` answers what
    they get today, which is what a client offers as the starting point.

    **This writes no rule.** It declares a draft on the customer's own book,
    exactly as a change to any other book is declared, and publishing it
    through `POST /pricing/books/{book_id}/publishes/{publish_id}/publish`
    is what puts the deal in force. The response carries that book's id and the
    diff.

    `effective_at` dates the override forward and omitting it means now, under
    the bounds every publish takes: timezone-aware (`effective_at_naive`), not
    in the past (`effective_at_in_past`), within 366 days
    (`effective_at_too_far_ahead`), and at or after the latest boundary already
    scheduled on this customer's book
    (`effective_at_before_scheduled_boundary`).

    Args:
        customer_id (UUID):
        body (CustomerOverrideIn): The rule this customer gets, and when it takes effect.

            **A COMPLETE RULE, WHICH IS THE WHOLE RULING.** Every field a rule has is
            stated here: the quantity it prices, the selectors it pins, how it derives
            its price and what it charges. There is no field naming a rule to inherit
            from and no field that takes a value while leaving a method behind —
            **partial override is not expressible on this surface**, because a rule
            whose method comes from one record and whose value comes from another
            cannot be explained by naming one rule, which is the property the receipt
            design rests on (#151 §6.2).

            **THIS BODY NAMES NO ACT.** It carries no `kind`, unlike a change to a
            book: declaring an override adds a rule and withdrawing one retires it, and
            which of the two is happening is the route you called.

            `effective_at` dates the override forward and omitting it means now, under
            exactly the bounds a publish takes, because this IS a publish: it is
            declared as a draft on the customer's own book, published through the
            book's own route, and reversed by a further publish. There is no
            immediate-effect path to an override and no second mutation surface for one.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookPublishOut | ProblemOut
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
    body: CustomerOverrideIn,

) -> Response[BookPublishOut | ProblemOut]:
    """ Declare Customer Override

     Declare one customer's own pricing rule, as a draft.

    The override states a WHOLE rule — the quantity it prices, the selectors it
    pins, how it derives its price and what it charges — and replaces whatever
    this customer inherits for that rule. Nothing is inherited into it: a field
    left out takes the rule defaults, never the superseded rule's value, so a
    customer moved from a margin over cost onto a flat price is stated in one
    body. `GET /pricing/customers/{customer_id}/inherited-rule` answers what
    they get today, which is what a client offers as the starting point.

    **This writes no rule.** It declares a draft on the customer's own book,
    exactly as a change to any other book is declared, and publishing it
    through `POST /pricing/books/{book_id}/publishes/{publish_id}/publish`
    is what puts the deal in force. The response carries that book's id and the
    diff.

    `effective_at` dates the override forward and omitting it means now, under
    the bounds every publish takes: timezone-aware (`effective_at_naive`), not
    in the past (`effective_at_in_past`), within 366 days
    (`effective_at_too_far_ahead`), and at or after the latest boundary already
    scheduled on this customer's book
    (`effective_at_before_scheduled_boundary`).

    Args:
        customer_id (UUID):
        body (CustomerOverrideIn): The rule this customer gets, and when it takes effect.

            **A COMPLETE RULE, WHICH IS THE WHOLE RULING.** Every field a rule has is
            stated here: the quantity it prices, the selectors it pins, how it derives
            its price and what it charges. There is no field naming a rule to inherit
            from and no field that takes a value while leaving a method behind —
            **partial override is not expressible on this surface**, because a rule
            whose method comes from one record and whose value comes from another
            cannot be explained by naming one rule, which is the property the receipt
            design rests on (#151 §6.2).

            **THIS BODY NAMES NO ACT.** It carries no `kind`, unlike a change to a
            book: declaring an override adds a rule and withdrawing one retires it, and
            which of the two is happening is the route you called.

            `effective_at` dates the override forward and omitting it means now, under
            exactly the bounds a publish takes, because this IS a publish: it is
            declared as a draft on the customer's own book, published through the
            book's own route, and reversed by a further publish. There is no
            immediate-effect path to an override and no second mutation surface for one.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookPublishOut | ProblemOut]
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
    body: CustomerOverrideIn,

) -> BookPublishOut | ProblemOut | None:
    """ Declare Customer Override

     Declare one customer's own pricing rule, as a draft.

    The override states a WHOLE rule — the quantity it prices, the selectors it
    pins, how it derives its price and what it charges — and replaces whatever
    this customer inherits for that rule. Nothing is inherited into it: a field
    left out takes the rule defaults, never the superseded rule's value, so a
    customer moved from a margin over cost onto a flat price is stated in one
    body. `GET /pricing/customers/{customer_id}/inherited-rule` answers what
    they get today, which is what a client offers as the starting point.

    **This writes no rule.** It declares a draft on the customer's own book,
    exactly as a change to any other book is declared, and publishing it
    through `POST /pricing/books/{book_id}/publishes/{publish_id}/publish`
    is what puts the deal in force. The response carries that book's id and the
    diff.

    `effective_at` dates the override forward and omitting it means now, under
    the bounds every publish takes: timezone-aware (`effective_at_naive`), not
    in the past (`effective_at_in_past`), within 366 days
    (`effective_at_too_far_ahead`), and at or after the latest boundary already
    scheduled on this customer's book
    (`effective_at_before_scheduled_boundary`).

    Args:
        customer_id (UUID):
        body (CustomerOverrideIn): The rule this customer gets, and when it takes effect.

            **A COMPLETE RULE, WHICH IS THE WHOLE RULING.** Every field a rule has is
            stated here: the quantity it prices, the selectors it pins, how it derives
            its price and what it charges. There is no field naming a rule to inherit
            from and no field that takes a value while leaving a method behind —
            **partial override is not expressible on this surface**, because a rule
            whose method comes from one record and whose value comes from another
            cannot be explained by naming one rule, which is the property the receipt
            design rests on (#151 §6.2).

            **THIS BODY NAMES NO ACT.** It carries no `kind`, unlike a change to a
            book: declaring an override adds a rule and withdrawing one retires it, and
            which of the two is happening is the route you called.

            `effective_at` dates the override forward and omitting it means now, under
            exactly the bounds a publish takes, because this IS a publish: it is
            declared as a draft on the customer's own book, published through the
            book's own route, and reversed by a further publish. There is no
            immediate-effect path to an override and no second mutation surface for one.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookPublishOut | ProblemOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
body=body,

    )).parsed
