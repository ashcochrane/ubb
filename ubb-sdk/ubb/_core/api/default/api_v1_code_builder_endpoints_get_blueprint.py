from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.problem_out import ProblemOut
from ...models.resolved_integration_blueprint import ResolvedIntegrationBlueprint
from typing import cast



def _get_kwargs(
    configuration_fingerprint: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/code-builder/blueprints/{configuration_fingerprint}".format(configuration_fingerprint=quote(str(configuration_fingerprint), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ProblemOut | ResolvedIntegrationBlueprint | None:
    if response.status_code == 200:
        response_200 = ResolvedIntegrationBlueprint.from_dict(response.json())



        return response_200

    if response.status_code == 404:
        response_404 = ProblemOut.from_dict(response.json())



        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ProblemOut | ResolvedIntegrationBlueprint]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    configuration_fingerprint: str,
    *,
    client: AuthenticatedClient,

) -> Response[ProblemOut | ResolvedIntegrationBlueprint]:
    """ Get Blueprint

     The Integration Blueprint stored under a fingerprint.

    Exactly the Blueprint that was resolved, whatever has changed since. A
    fingerprint that was never resolved, or whose snapshot has been removed,
    answers `404 not_found`: resolve the selection again.

    Args:
        configuration_fingerprint (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ResolvedIntegrationBlueprint]
     """


    kwargs = _get_kwargs(
        configuration_fingerprint=configuration_fingerprint,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    configuration_fingerprint: str,
    *,
    client: AuthenticatedClient,

) -> ProblemOut | ResolvedIntegrationBlueprint | None:
    """ Get Blueprint

     The Integration Blueprint stored under a fingerprint.

    Exactly the Blueprint that was resolved, whatever has changed since. A
    fingerprint that was never resolved, or whose snapshot has been removed,
    answers `404 not_found`: resolve the selection again.

    Args:
        configuration_fingerprint (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ResolvedIntegrationBlueprint
     """


    return sync_detailed(
        configuration_fingerprint=configuration_fingerprint,
client=client,

    ).parsed

async def asyncio_detailed(
    configuration_fingerprint: str,
    *,
    client: AuthenticatedClient,

) -> Response[ProblemOut | ResolvedIntegrationBlueprint]:
    """ Get Blueprint

     The Integration Blueprint stored under a fingerprint.

    Exactly the Blueprint that was resolved, whatever has changed since. A
    fingerprint that was never resolved, or whose snapshot has been removed,
    answers `404 not_found`: resolve the selection again.

    Args:
        configuration_fingerprint (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ProblemOut | ResolvedIntegrationBlueprint]
     """


    kwargs = _get_kwargs(
        configuration_fingerprint=configuration_fingerprint,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    configuration_fingerprint: str,
    *,
    client: AuthenticatedClient,

) -> ProblemOut | ResolvedIntegrationBlueprint | None:
    """ Get Blueprint

     The Integration Blueprint stored under a fingerprint.

    Exactly the Blueprint that was resolved, whatever has changed since. A
    fingerprint that was never resolved, or whose snapshot has been removed,
    answers `404 not_found`: resolve the selection again.

    Args:
        configuration_fingerprint (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ProblemOut | ResolvedIntegrationBlueprint
     """


    return (await asyncio_detailed(
        configuration_fingerprint=configuration_fingerprint,
client=client,

    )).parsed
