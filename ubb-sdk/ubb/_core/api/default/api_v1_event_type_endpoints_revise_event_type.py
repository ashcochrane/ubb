from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.event_type_out import EventTypeOut
from ...models.event_type_update_in import EventTypeUpdateIn
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    key: str,
    *,
    body: EventTypeUpdateIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v1/event-types/{key}".format(key=quote(str(key), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> EventTypeOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = EventTypeOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[EventTypeOut | ProblemOut]:
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
    body: EventTypeUpdateIn,

) -> Response[EventTypeOut | ProblemOut]:
    r""" Revise Event Type

     Edit a declaration. Changing a pinned element returns it to draft.

    The un-publishing is the model's, not this handler's, and deliberately so:
    it is a rule about what a change MEANS, and anything a caller has to
    remember to route through is a rule that holds until the first caller who
    does not. What this decides is what an absent field means — untouched,
    never cleared — and that an empty string detaches a satellite, because \"no
    supplier\" is a state a tenant reaches on purpose.

    Args:
        key (str):
        body (EventTypeUpdateIn): Every field optional: an absent field is untouched, not cleared.

            The two satellites detach on an EMPTY STRING rather than on a null, which
            is the one place this shape has to be explicit: "no supplier" is a state a
            tenant reaches deliberately, and a null that meant "leave alone" would
            leave them no way to say it.

            **The key is absent on purpose.** It is the name a tenant's own recorded
            events arrive under, so renaming one would silently re-point every posting
            made against it — the same objection that keeps supplier cost resolution on
            the Provider's identity rather than on its handle, arriving at the opposite
            answer because here the handle IS the identity. Withdraw and re-declare, or
            map the old name through the quarantine that already exists for a name UBB
            does not recognise.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EventTypeOut | ProblemOut]
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
    body: EventTypeUpdateIn,

) -> EventTypeOut | ProblemOut | None:
    r""" Revise Event Type

     Edit a declaration. Changing a pinned element returns it to draft.

    The un-publishing is the model's, not this handler's, and deliberately so:
    it is a rule about what a change MEANS, and anything a caller has to
    remember to route through is a rule that holds until the first caller who
    does not. What this decides is what an absent field means — untouched,
    never cleared — and that an empty string detaches a satellite, because \"no
    supplier\" is a state a tenant reaches on purpose.

    Args:
        key (str):
        body (EventTypeUpdateIn): Every field optional: an absent field is untouched, not cleared.

            The two satellites detach on an EMPTY STRING rather than on a null, which
            is the one place this shape has to be explicit: "no supplier" is a state a
            tenant reaches deliberately, and a null that meant "leave alone" would
            leave them no way to say it.

            **The key is absent on purpose.** It is the name a tenant's own recorded
            events arrive under, so renaming one would silently re-point every posting
            made against it — the same objection that keeps supplier cost resolution on
            the Provider's identity rather than on its handle, arriving at the opposite
            answer because here the handle IS the identity. Withdraw and re-declare, or
            map the old name through the quarantine that already exists for a name UBB
            does not recognise.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EventTypeOut | ProblemOut
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
    body: EventTypeUpdateIn,

) -> Response[EventTypeOut | ProblemOut]:
    r""" Revise Event Type

     Edit a declaration. Changing a pinned element returns it to draft.

    The un-publishing is the model's, not this handler's, and deliberately so:
    it is a rule about what a change MEANS, and anything a caller has to
    remember to route through is a rule that holds until the first caller who
    does not. What this decides is what an absent field means — untouched,
    never cleared — and that an empty string detaches a satellite, because \"no
    supplier\" is a state a tenant reaches on purpose.

    Args:
        key (str):
        body (EventTypeUpdateIn): Every field optional: an absent field is untouched, not cleared.

            The two satellites detach on an EMPTY STRING rather than on a null, which
            is the one place this shape has to be explicit: "no supplier" is a state a
            tenant reaches deliberately, and a null that meant "leave alone" would
            leave them no way to say it.

            **The key is absent on purpose.** It is the name a tenant's own recorded
            events arrive under, so renaming one would silently re-point every posting
            made against it — the same objection that keeps supplier cost resolution on
            the Provider's identity rather than on its handle, arriving at the opposite
            answer because here the handle IS the identity. Withdraw and re-declare, or
            map the old name through the quarantine that already exists for a name UBB
            does not recognise.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EventTypeOut | ProblemOut]
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
    body: EventTypeUpdateIn,

) -> EventTypeOut | ProblemOut | None:
    r""" Revise Event Type

     Edit a declaration. Changing a pinned element returns it to draft.

    The un-publishing is the model's, not this handler's, and deliberately so:
    it is a rule about what a change MEANS, and anything a caller has to
    remember to route through is a rule that holds until the first caller who
    does not. What this decides is what an absent field means — untouched,
    never cleared — and that an empty string detaches a satellite, because \"no
    supplier\" is a state a tenant reaches on purpose.

    Args:
        key (str):
        body (EventTypeUpdateIn): Every field optional: an absent field is untouched, not cleared.

            The two satellites detach on an EMPTY STRING rather than on a null, which
            is the one place this shape has to be explicit: "no supplier" is a state a
            tenant reaches deliberately, and a null that meant "leave alone" would
            leave them no way to say it.

            **The key is absent on purpose.** It is the name a tenant's own recorded
            events arrive under, so renaming one would silently re-point every posting
            made against it — the same objection that keeps supplier cost resolution on
            the Provider's identity rather than on its handle, arriving at the opposite
            answer because here the handle IS the identity. Withdraw and re-declare, or
            map the old name through the quarantine that already exists for a name UBB
            does not recognise.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EventTypeOut | ProblemOut
     """


    return (await asyncio_detailed(
        key=key,
client=client,
body=body,

    )).parsed
