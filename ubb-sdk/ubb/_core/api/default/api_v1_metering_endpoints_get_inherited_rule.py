from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.inherited_rule_out import InheritedRuleOut
from ...models.problem_out import ProblemOut
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime



def _get_kwargs(
    customer_id: UUID,
    *,
    measurement_key: str,
    provider: str | Unset = '',
    event_type: str | Unset = '',
    task_type: str | Unset = '',
    subtask_type: str | Unset = '',
    grouping_field: list[str] | Unset = UNSET,
    as_of: datetime.datetime | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["measurement_key"] = measurement_key

    params["provider"] = provider

    params["event_type"] = event_type

    params["task_type"] = task_type

    params["subtask_type"] = subtask_type

    json_grouping_field: list[str] | Unset = UNSET
    if not isinstance(grouping_field, Unset):
        json_grouping_field = grouping_field


    params["grouping_field"] = json_grouping_field

    json_as_of: None | str | Unset
    if isinstance(as_of, Unset):
        json_as_of = UNSET
    elif isinstance(as_of, datetime.datetime):
        json_as_of = as_of.isoformat()
    else:
        json_as_of = as_of
    params["as_of"] = json_as_of


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/metering/pricing/customers/{customer_id}/inherited-rule".format(customer_id=quote(str(customer_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> InheritedRuleOut | ProblemOut | None:
    if response.status_code == 200:
        response_200 = InheritedRuleOut.from_dict(response.json())



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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[InheritedRuleOut | ProblemOut]:
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
    measurement_key: str,
    provider: str | Unset = '',
    event_type: str | Unset = '',
    task_type: str | Unset = '',
    subtask_type: str | Unset = '',
    grouping_field: list[str] | Unset = UNSET,
    as_of: datetime.datetime | None | Unset = UNSET,

) -> Response[InheritedRuleOut | ProblemOut]:
    """ Get Inherited Rule

     What this customer is charged for a rule where they have no override.

    The starting point for writing one: the rule as it stands for this customer
    with their own book taken out of the ladder, so a client can show the
    method and the current value the override is about to replace, and copy
    them into `POST /pricing/customers/{customer_id}/overrides`.

    It is the same ladder one rung shorter — same specificity-before-source,
    same absence of fallthrough between books — so what is shown cannot drift
    from what is being overridden.

    `rule` is null where nothing is inherited, which is an ordinary state
    rather than an error: a quantity no book in play prices falls to the
    tenant's markup rung, and an override written there starts from nothing.

    Each `grouping_field` is `key=value`, naming a grouping field this tenant
    has declared; repeat the parameter to pin more than one. `as_of` asks the
    question at an instant other than now.

    Args:
        customer_id (UUID):
        measurement_key (str):
        provider (str | Unset):  Default: ''.
        event_type (str | Unset):  Default: ''.
        task_type (str | Unset):  Default: ''.
        subtask_type (str | Unset):  Default: ''.
        grouping_field (list[str] | Unset):
        as_of (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[InheritedRuleOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
measurement_key=measurement_key,
provider=provider,
event_type=event_type,
task_type=task_type,
subtask_type=subtask_type,
grouping_field=grouping_field,
as_of=as_of,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    measurement_key: str,
    provider: str | Unset = '',
    event_type: str | Unset = '',
    task_type: str | Unset = '',
    subtask_type: str | Unset = '',
    grouping_field: list[str] | Unset = UNSET,
    as_of: datetime.datetime | None | Unset = UNSET,

) -> InheritedRuleOut | ProblemOut | None:
    """ Get Inherited Rule

     What this customer is charged for a rule where they have no override.

    The starting point for writing one: the rule as it stands for this customer
    with their own book taken out of the ladder, so a client can show the
    method and the current value the override is about to replace, and copy
    them into `POST /pricing/customers/{customer_id}/overrides`.

    It is the same ladder one rung shorter — same specificity-before-source,
    same absence of fallthrough between books — so what is shown cannot drift
    from what is being overridden.

    `rule` is null where nothing is inherited, which is an ordinary state
    rather than an error: a quantity no book in play prices falls to the
    tenant's markup rung, and an override written there starts from nothing.

    Each `grouping_field` is `key=value`, naming a grouping field this tenant
    has declared; repeat the parameter to pin more than one. `as_of` asks the
    question at an instant other than now.

    Args:
        customer_id (UUID):
        measurement_key (str):
        provider (str | Unset):  Default: ''.
        event_type (str | Unset):  Default: ''.
        task_type (str | Unset):  Default: ''.
        subtask_type (str | Unset):  Default: ''.
        grouping_field (list[str] | Unset):
        as_of (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        InheritedRuleOut | ProblemOut
     """


    return sync_detailed(
        customer_id=customer_id,
client=client,
measurement_key=measurement_key,
provider=provider,
event_type=event_type,
task_type=task_type,
subtask_type=subtask_type,
grouping_field=grouping_field,
as_of=as_of,

    ).parsed

async def asyncio_detailed(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    measurement_key: str,
    provider: str | Unset = '',
    event_type: str | Unset = '',
    task_type: str | Unset = '',
    subtask_type: str | Unset = '',
    grouping_field: list[str] | Unset = UNSET,
    as_of: datetime.datetime | None | Unset = UNSET,

) -> Response[InheritedRuleOut | ProblemOut]:
    """ Get Inherited Rule

     What this customer is charged for a rule where they have no override.

    The starting point for writing one: the rule as it stands for this customer
    with their own book taken out of the ladder, so a client can show the
    method and the current value the override is about to replace, and copy
    them into `POST /pricing/customers/{customer_id}/overrides`.

    It is the same ladder one rung shorter — same specificity-before-source,
    same absence of fallthrough between books — so what is shown cannot drift
    from what is being overridden.

    `rule` is null where nothing is inherited, which is an ordinary state
    rather than an error: a quantity no book in play prices falls to the
    tenant's markup rung, and an override written there starts from nothing.

    Each `grouping_field` is `key=value`, naming a grouping field this tenant
    has declared; repeat the parameter to pin more than one. `as_of` asks the
    question at an instant other than now.

    Args:
        customer_id (UUID):
        measurement_key (str):
        provider (str | Unset):  Default: ''.
        event_type (str | Unset):  Default: ''.
        task_type (str | Unset):  Default: ''.
        subtask_type (str | Unset):  Default: ''.
        grouping_field (list[str] | Unset):
        as_of (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[InheritedRuleOut | ProblemOut]
     """


    kwargs = _get_kwargs(
        customer_id=customer_id,
measurement_key=measurement_key,
provider=provider,
event_type=event_type,
task_type=task_type,
subtask_type=subtask_type,
grouping_field=grouping_field,
as_of=as_of,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    customer_id: UUID,
    *,
    client: AuthenticatedClient,
    measurement_key: str,
    provider: str | Unset = '',
    event_type: str | Unset = '',
    task_type: str | Unset = '',
    subtask_type: str | Unset = '',
    grouping_field: list[str] | Unset = UNSET,
    as_of: datetime.datetime | None | Unset = UNSET,

) -> InheritedRuleOut | ProblemOut | None:
    """ Get Inherited Rule

     What this customer is charged for a rule where they have no override.

    The starting point for writing one: the rule as it stands for this customer
    with their own book taken out of the ladder, so a client can show the
    method and the current value the override is about to replace, and copy
    them into `POST /pricing/customers/{customer_id}/overrides`.

    It is the same ladder one rung shorter — same specificity-before-source,
    same absence of fallthrough between books — so what is shown cannot drift
    from what is being overridden.

    `rule` is null where nothing is inherited, which is an ordinary state
    rather than an error: a quantity no book in play prices falls to the
    tenant's markup rung, and an override written there starts from nothing.

    Each `grouping_field` is `key=value`, naming a grouping field this tenant
    has declared; repeat the parameter to pin more than one. `as_of` asks the
    question at an instant other than now.

    Args:
        customer_id (UUID):
        measurement_key (str):
        provider (str | Unset):  Default: ''.
        event_type (str | Unset):  Default: ''.
        task_type (str | Unset):  Default: ''.
        subtask_type (str | Unset):  Default: ''.
        grouping_field (list[str] | Unset):
        as_of (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        InheritedRuleOut | ProblemOut
     """


    return (await asyncio_detailed(
        customer_id=customer_id,
client=client,
measurement_key=measurement_key,
provider=provider,
event_type=event_type,
task_type=task_type,
subtask_type=subtask_type,
grouping_field=grouping_field,
as_of=as_of,

    )).parsed
