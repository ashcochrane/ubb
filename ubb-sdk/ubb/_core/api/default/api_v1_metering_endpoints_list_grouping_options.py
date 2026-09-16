from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.grouping_options_out import GroupingOptionsOut
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/analytics/grouping-options",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> GroupingOptionsOut | None:
    if response.status_code == 200:
        response_200 = GroupingOptionsOut.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[GroupingOptionsOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[GroupingOptionsOut]:
    r""" List Grouping Options

     What this tenant may group an economic question by — the discovery
    contract (#498, slice 7 §7).

    `apps/metering/queries.py::grouping_options` computes it and argues what it
    is for; this is the wire, and the two things the wire itself decides.

    Read floor, and deliberately: a finance operator building a chart is exactly
    who asks this, and it publishes no amount. The axes it lists are the
    tenant's own declarations, which the same floor already reads next door.

    UNPAGINATED, on `docs/conventions/api-contract.md`'s *\"computed reports are
    not lists\"* clause rather than in spite of its cursor rule. It is computed
    per tenant; and where that clause asks a report to be parameter-bounded,
    this one is bounded by CONSTRUCTION — the always-present axes, at most the
    registry's ten slots, and the two rollups — so there is no window a caller
    could leave open. The two registry reads beside it answer the same way.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GroupingOptionsOut]
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

) -> GroupingOptionsOut | None:
    r""" List Grouping Options

     What this tenant may group an economic question by — the discovery
    contract (#498, slice 7 §7).

    `apps/metering/queries.py::grouping_options` computes it and argues what it
    is for; this is the wire, and the two things the wire itself decides.

    Read floor, and deliberately: a finance operator building a chart is exactly
    who asks this, and it publishes no amount. The axes it lists are the
    tenant's own declarations, which the same floor already reads next door.

    UNPAGINATED, on `docs/conventions/api-contract.md`'s *\"computed reports are
    not lists\"* clause rather than in spite of its cursor rule. It is computed
    per tenant; and where that clause asks a report to be parameter-bounded,
    this one is bounded by CONSTRUCTION — the always-present axes, at most the
    registry's ten slots, and the two rollups — so there is no window a caller
    could leave open. The two registry reads beside it answer the same way.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GroupingOptionsOut
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[GroupingOptionsOut]:
    r""" List Grouping Options

     What this tenant may group an economic question by — the discovery
    contract (#498, slice 7 §7).

    `apps/metering/queries.py::grouping_options` computes it and argues what it
    is for; this is the wire, and the two things the wire itself decides.

    Read floor, and deliberately: a finance operator building a chart is exactly
    who asks this, and it publishes no amount. The axes it lists are the
    tenant's own declarations, which the same floor already reads next door.

    UNPAGINATED, on `docs/conventions/api-contract.md`'s *\"computed reports are
    not lists\"* clause rather than in spite of its cursor rule. It is computed
    per tenant; and where that clause asks a report to be parameter-bounded,
    this one is bounded by CONSTRUCTION — the always-present axes, at most the
    registry's ten slots, and the two rollups — so there is no window a caller
    could leave open. The two registry reads beside it answer the same way.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GroupingOptionsOut]
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

) -> GroupingOptionsOut | None:
    r""" List Grouping Options

     What this tenant may group an economic question by — the discovery
    contract (#498, slice 7 §7).

    `apps/metering/queries.py::grouping_options` computes it and argues what it
    is for; this is the wire, and the two things the wire itself decides.

    Read floor, and deliberately: a finance operator building a chart is exactly
    who asks this, and it publishes no amount. The axes it lists are the
    tenant's own declarations, which the same floor already reads next door.

    UNPAGINATED, on `docs/conventions/api-contract.md`'s *\"computed reports are
    not lists\"* clause rather than in spite of its cursor rule. It is computed
    per tenant; and where that clause asks a report to be parameter-bounded,
    this one is bounded by CONSTRUCTION — the always-present axes, at most the
    registry's ten slots, and the two rollups — so there is no window a caller
    could leave open. The two registry reads beside it answer the same way.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GroupingOptionsOut
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
