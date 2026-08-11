from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.measurement_in import MeasurementIn
from ...models.measurement_out import MeasurementOut
from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    key: str,
    code: str,
    *,
    body: MeasurementIn,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/event-types/{key}/measurements/{code}".format(key=quote(str(key), safe=""),code=quote(str(code), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> MeasurementOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = MeasurementOut.from_dict(response.json())



        return response_200

    if response.status_code == 201:
        response_201 = MeasurementOut.from_dict(response.json())



        return response_201

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[MeasurementOut | ProblemOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    key: str,
    code: str,
    *,
    client: AuthenticatedClient,
    body: MeasurementIn,

) -> Response[MeasurementOut | ProblemOut]:
    """ Declare Measurement

     Declare or re-declare one quantity beneath an Event Type.

    The same name on two Event Types is two independent declarations, so this
    is keyed on the pair and never on the code alone: a tenant's Gemini and
    OpenAI integrations never have to agree about spelling to both be correct.

    Declaring one under a PUBLISHED Event Type revises the publication — the
    model does that, on the same footing as an edit, because a published
    declaration that grows a required quantity is a different declaration from
    the one a tenant generated their integration against.

    Args:
        key (str):
        code (str):
        body (MeasurementIn): One measurable quantity an Event Type produces.

            The code is the path segment rather than a body field: it is this
            declaration's identity beneath its Event Type, and a body that could
            disagree with the URL would make "which declaration is this" a question
            with two answers.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MeasurementOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        key=key,
code=code,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    key: str,
    code: str,
    *,
    client: AuthenticatedClient,
    body: MeasurementIn,

) -> MeasurementOut | ProblemOut | None:
    """ Declare Measurement

     Declare or re-declare one quantity beneath an Event Type.

    The same name on two Event Types is two independent declarations, so this
    is keyed on the pair and never on the code alone: a tenant's Gemini and
    OpenAI integrations never have to agree about spelling to both be correct.

    Declaring one under a PUBLISHED Event Type revises the publication — the
    model does that, on the same footing as an edit, because a published
    declaration that grows a required quantity is a different declaration from
    the one a tenant generated their integration against.

    Args:
        key (str):
        code (str):
        body (MeasurementIn): One measurable quantity an Event Type produces.

            The code is the path segment rather than a body field: it is this
            declaration's identity beneath its Event Type, and a body that could
            disagree with the URL would make "which declaration is this" a question
            with two answers.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MeasurementOut | ProblemOut
     """


    return sync_detailed(
        key=key,
code=code,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    key: str,
    code: str,
    *,
    client: AuthenticatedClient,
    body: MeasurementIn,

) -> Response[MeasurementOut | ProblemOut]:
    """ Declare Measurement

     Declare or re-declare one quantity beneath an Event Type.

    The same name on two Event Types is two independent declarations, so this
    is keyed on the pair and never on the code alone: a tenant's Gemini and
    OpenAI integrations never have to agree about spelling to both be correct.

    Declaring one under a PUBLISHED Event Type revises the publication — the
    model does that, on the same footing as an edit, because a published
    declaration that grows a required quantity is a different declaration from
    the one a tenant generated their integration against.

    Args:
        key (str):
        code (str):
        body (MeasurementIn): One measurable quantity an Event Type produces.

            The code is the path segment rather than a body field: it is this
            declaration's identity beneath its Event Type, and a body that could
            disagree with the URL would make "which declaration is this" a question
            with two answers.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MeasurementOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        key=key,
code=code,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    key: str,
    code: str,
    *,
    client: AuthenticatedClient,
    body: MeasurementIn,

) -> MeasurementOut | ProblemOut | None:
    """ Declare Measurement

     Declare or re-declare one quantity beneath an Event Type.

    The same name on two Event Types is two independent declarations, so this
    is keyed on the pair and never on the code alone: a tenant's Gemini and
    OpenAI integrations never have to agree about spelling to both be correct.

    Declaring one under a PUBLISHED Event Type revises the publication — the
    model does that, on the same footing as an edit, because a published
    declaration that grows a required quantity is a different declaration from
    the one a tenant generated their integration against.

    Args:
        key (str):
        code (str):
        body (MeasurementIn): One measurable quantity an Event Type produces.

            The code is the path segment rather than a body field: it is this
            declaration's identity beneath its Event Type, and a body that could
            disagree with the URL would make "which declaration is this" a question
            with two answers.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MeasurementOut | ProblemOut
     """


    return (await asyncio_detailed(
        key=key,
code=code,
client=client,
body=body,

    )).parsed
