from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.book_publish_in import BookPublishIn
from ...models.book_publish_out import BookPublishOut
from ...models.problem_out import ProblemOut
from typing import cast
from uuid import UUID



def _get_kwargs(
    book_id: UUID,
    *,
    body: BookPublishIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/metering/pricing/rate-cards/{book_id}/publishes".format(book_id=quote(str(book_id), safe=""),),
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
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    body: BookPublishIn,

) -> Response[BookPublishOut | ProblemOut]:
    """ Declare Book Publish

     Declare a change to a book: the intended changes, and nothing written.

    A draft holds the changes and writes no rule, which is what makes it freely
    editable and freely discardable. The response carries the diff — what the
    book will look like afterwards — so a tenant decides against the outcome
    rather than against their own request.

    Every change is resolved before the draft is created, so a name the tenant
    has not declared, or a rule that is not there, is a 422 while they are still
    deciding rather than a surprise when the price was supposed to change.

    **The change can be dated forward, and nothing runs at the instant.**
    `effective_at` names when it takes effect and omitting it means now.
    Publishing writes the rows there and then, carrying the boundary as a value
    resolution reads, so no job has to run when the moment arrives.

    An instant must be timezone-aware (`effective_at_naive`), must not be in the
    past (`effective_at_in_past`), and must be within 366 days
    (`effective_at_too_far_ahead`). A refused declaration writes nothing and is
    recorded nowhere.

    Args:
        book_id (UUID):
        body (BookPublishIn): The intended changes, and when they take effect.

            **`effective_at` IS WHAT DATES A CHANGE FORWARD, AND OMITTING IT MEANS
            NOW.** A tenant who has agreed a rise from the first of next month states
            that instant here and stops having to remember: publishing writes the rows
            immediately, carrying the boundary as a value the resolver reads, so
            **nothing runs at the instant itself**. There is no job to be late, which
            matters because a late job would price every event in the gap at the old
            rate and that wrong price would sit permanently on an authoritative record.

            The instant must be timezone-aware (`effective_at_naive`). A change is dated
            forward or not at all, so an instant more than five minutes behind the
            present is refused with `effective_at_in_past` — the allowance is clock
            skew, so that a caller stamping its own "now" is not told its clock is
            wrong. And it must be within the platform's forward horizon of **366 days**;
            beyond it the request is refused with `effective_at_too_far_ahead`.

            Each of the three carries a code of its own so that *"that date is a typo"*
            is distinguishable from *"that date has passed"* and from every other reason
            a body is refused. The horizon is a platform bound and no tenant setting
            moves it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookPublishOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    body: BookPublishIn,

) -> BookPublishOut | ProblemOut | None:
    """ Declare Book Publish

     Declare a change to a book: the intended changes, and nothing written.

    A draft holds the changes and writes no rule, which is what makes it freely
    editable and freely discardable. The response carries the diff — what the
    book will look like afterwards — so a tenant decides against the outcome
    rather than against their own request.

    Every change is resolved before the draft is created, so a name the tenant
    has not declared, or a rule that is not there, is a 422 while they are still
    deciding rather than a surprise when the price was supposed to change.

    **The change can be dated forward, and nothing runs at the instant.**
    `effective_at` names when it takes effect and omitting it means now.
    Publishing writes the rows there and then, carrying the boundary as a value
    resolution reads, so no job has to run when the moment arrives.

    An instant must be timezone-aware (`effective_at_naive`), must not be in the
    past (`effective_at_in_past`), and must be within 366 days
    (`effective_at_too_far_ahead`). A refused declaration writes nothing and is
    recorded nowhere.

    Args:
        book_id (UUID):
        body (BookPublishIn): The intended changes, and when they take effect.

            **`effective_at` IS WHAT DATES A CHANGE FORWARD, AND OMITTING IT MEANS
            NOW.** A tenant who has agreed a rise from the first of next month states
            that instant here and stops having to remember: publishing writes the rows
            immediately, carrying the boundary as a value the resolver reads, so
            **nothing runs at the instant itself**. There is no job to be late, which
            matters because a late job would price every event in the gap at the old
            rate and that wrong price would sit permanently on an authoritative record.

            The instant must be timezone-aware (`effective_at_naive`). A change is dated
            forward or not at all, so an instant more than five minutes behind the
            present is refused with `effective_at_in_past` — the allowance is clock
            skew, so that a caller stamping its own "now" is not told its clock is
            wrong. And it must be within the platform's forward horizon of **366 days**;
            beyond it the request is refused with `effective_at_too_far_ahead`.

            Each of the three carries a code of its own so that *"that date is a typo"*
            is distinguishable from *"that date has passed"* and from every other reason
            a body is refused. The horizon is a platform bound and no tenant setting
            moves it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookPublishOut | ProblemOut
     """


    return sync_detailed(
        book_id=book_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    body: BookPublishIn,

) -> Response[BookPublishOut | ProblemOut]:
    """ Declare Book Publish

     Declare a change to a book: the intended changes, and nothing written.

    A draft holds the changes and writes no rule, which is what makes it freely
    editable and freely discardable. The response carries the diff — what the
    book will look like afterwards — so a tenant decides against the outcome
    rather than against their own request.

    Every change is resolved before the draft is created, so a name the tenant
    has not declared, or a rule that is not there, is a 422 while they are still
    deciding rather than a surprise when the price was supposed to change.

    **The change can be dated forward, and nothing runs at the instant.**
    `effective_at` names when it takes effect and omitting it means now.
    Publishing writes the rows there and then, carrying the boundary as a value
    resolution reads, so no job has to run when the moment arrives.

    An instant must be timezone-aware (`effective_at_naive`), must not be in the
    past (`effective_at_in_past`), and must be within 366 days
    (`effective_at_too_far_ahead`). A refused declaration writes nothing and is
    recorded nowhere.

    Args:
        book_id (UUID):
        body (BookPublishIn): The intended changes, and when they take effect.

            **`effective_at` IS WHAT DATES A CHANGE FORWARD, AND OMITTING IT MEANS
            NOW.** A tenant who has agreed a rise from the first of next month states
            that instant here and stops having to remember: publishing writes the rows
            immediately, carrying the boundary as a value the resolver reads, so
            **nothing runs at the instant itself**. There is no job to be late, which
            matters because a late job would price every event in the gap at the old
            rate and that wrong price would sit permanently on an authoritative record.

            The instant must be timezone-aware (`effective_at_naive`). A change is dated
            forward or not at all, so an instant more than five minutes behind the
            present is refused with `effective_at_in_past` — the allowance is clock
            skew, so that a caller stamping its own "now" is not told its clock is
            wrong. And it must be within the platform's forward horizon of **366 days**;
            beyond it the request is refused with `effective_at_too_far_ahead`.

            Each of the three carries a code of its own so that *"that date is a typo"*
            is distinguishable from *"that date has passed"* and from every other reason
            a body is refused. The horizon is a platform bound and no tenant setting
            moves it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BookPublishOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        book_id=book_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    book_id: UUID,
    *,
    client: AuthenticatedClient,
    body: BookPublishIn,

) -> BookPublishOut | ProblemOut | None:
    """ Declare Book Publish

     Declare a change to a book: the intended changes, and nothing written.

    A draft holds the changes and writes no rule, which is what makes it freely
    editable and freely discardable. The response carries the diff — what the
    book will look like afterwards — so a tenant decides against the outcome
    rather than against their own request.

    Every change is resolved before the draft is created, so a name the tenant
    has not declared, or a rule that is not there, is a 422 while they are still
    deciding rather than a surprise when the price was supposed to change.

    **The change can be dated forward, and nothing runs at the instant.**
    `effective_at` names when it takes effect and omitting it means now.
    Publishing writes the rows there and then, carrying the boundary as a value
    resolution reads, so no job has to run when the moment arrives.

    An instant must be timezone-aware (`effective_at_naive`), must not be in the
    past (`effective_at_in_past`), and must be within 366 days
    (`effective_at_too_far_ahead`). A refused declaration writes nothing and is
    recorded nowhere.

    Args:
        book_id (UUID):
        body (BookPublishIn): The intended changes, and when they take effect.

            **`effective_at` IS WHAT DATES A CHANGE FORWARD, AND OMITTING IT MEANS
            NOW.** A tenant who has agreed a rise from the first of next month states
            that instant here and stops having to remember: publishing writes the rows
            immediately, carrying the boundary as a value the resolver reads, so
            **nothing runs at the instant itself**. There is no job to be late, which
            matters because a late job would price every event in the gap at the old
            rate and that wrong price would sit permanently on an authoritative record.

            The instant must be timezone-aware (`effective_at_naive`). A change is dated
            forward or not at all, so an instant more than five minutes behind the
            present is refused with `effective_at_in_past` — the allowance is clock
            skew, so that a caller stamping its own "now" is not told its clock is
            wrong. And it must be within the platform's forward horizon of **366 days**;
            beyond it the request is refused with `effective_at_too_far_ahead`.

            Each of the three carries a code of its own so that *"that date is a typo"*
            is distinguishable from *"that date has passed"* and from every other reason
            a body is refused. The horizon is a platform bound and no tenant setting
            moves it.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BookPublishOut | ProblemOut
     """


    return (await asyncio_detailed(
        book_id=book_id,
client=client,
body=body,

    )).parsed
