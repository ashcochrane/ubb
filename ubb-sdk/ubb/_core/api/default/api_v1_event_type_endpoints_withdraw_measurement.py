from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from typing import cast



def _get_kwargs(
    key: str,
    code: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/event-types/{key}/measurements/{code}".format(key=quote(str(key), safe=""),code=quote(str(code), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | ProblemOut | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if response.status_code == 409:
        response_409 = ProblemOut.from_dict(response.json())



        return response_409

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | ProblemOut]:
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

) -> Response[Any | ProblemOut]:
    """ Withdraw Measurement

     Withdraw one declared quantity, unless a rate still prices it.

    A real delete rather than the data plane's soft delete: that rule protects
    rows carrying money history, and a part of a declaration carries none.

    Refused while a rate names it: a priced rule against a quantity you no
    longer declare is a rule that can price nothing, so either the rule goes
    first or the declaration stays.

    Args:
        key (str):
        code (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ProblemOut]
     """


    kwargs = _get_kwargs(
        key=key,
code=code,

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

) -> Any | ProblemOut | None:
    """ Withdraw Measurement

     Withdraw one declared quantity, unless a rate still prices it.

    A real delete rather than the data plane's soft delete: that rule protects
    rows carrying money history, and a part of a declaration carries none.

    Refused while a rate names it: a priced rule against a quantity you no
    longer declare is a rule that can price nothing, so either the rule goes
    first or the declaration stays.

    Args:
        key (str):
        code (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ProblemOut
     """


    return sync_detailed(
        key=key,
code=code,
client=client,

    ).parsed

async def asyncio_detailed(
    key: str,
    code: str,
    *,
    client: AuthenticatedClient,

) -> Response[Any | ProblemOut]:
    """ Withdraw Measurement

     Withdraw one declared quantity, unless a rate still prices it.

    A real delete rather than the data plane's soft delete: that rule protects
    rows carrying money history, and a part of a declaration carries none.

    Refused while a rate names it: a priced rule against a quantity you no
    longer declare is a rule that can price nothing, so either the rule goes
    first or the declaration stays.

    Args:
        key (str):
        code (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ProblemOut]
     """


    kwargs = _get_kwargs(
        key=key,
code=code,

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

) -> Any | ProblemOut | None:
    """ Withdraw Measurement

     Withdraw one declared quantity, unless a rate still prices it.

    A real delete rather than the data plane's soft delete: that rule protects
    rows carrying money history, and a part of a declaration carries none.

    Refused while a rate names it: a priced rule against a quantity you no
    longer declare is a rule that can price nothing, so either the rule goes
    first or the declaration stays.

    Args:
        key (str):
        code (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ProblemOut
     """


    return (await asyncio_detailed(
        key=key,
code=code,
client=client,

    )).parsed
