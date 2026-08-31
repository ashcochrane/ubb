from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.start_task_response_status import StartTaskResponseStatus
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="StartTaskResponse")



@_attrs_define
class StartTaskResponse:
    """ What a start registered, or what its key already claimed.

    ⚠ THE REGISTRATION, NOT THE READ. A start answers *which unit of work is
    this, and did I just create it* — the identity, the altitude, and the facts
    the unit pinned. What it deliberately does NOT carry is the cost
    rollups: they are a read's answer, they are all zero on the call that
    creates the row, and `GET /api/v1/tasks/{task_id}` is one call away for a
    caller replaying an attempt that has since run up cost.

    ⚠ AND THE DECLARED GROUPING VALUES ARE NOT ECHOED, for two reasons that
    point the same way. The caller just sent them, and a start that pinned
    something else would say so by refusing rather than by handing back a
    corrected bag. The second is a constraint rather than a preference and is
    recorded because it decided a published surface: that bag's wire key is
    retired vocabulary under a spread ceiling another slice owns, and every
    schema publishing it mints one more generated SDK module that counts
    against the ceiling — so a third copy of the property would fail the sweep
    for a debt this commit does not own. #358 is the precedent, in the same
    direction.

        Attributes:
            created_at (str):
            replayed (bool):
            status (StartTaskResponseStatus):
            task_id (str):
            agreed_price_micros (int | None | Unset):
            external_task_id (str | Unset):  Default: ''.
            parent_task_id (None | str | Unset):
            provider_cost_limit_micros (int | None | Unset):
            task_type (str | Unset):  Default: ''.
     """

    created_at: str
    replayed: bool
    status: StartTaskResponseStatus
    task_id: str
    agreed_price_micros: int | None | Unset = UNSET
    external_task_id: str | Unset = ''
    parent_task_id: None | str | Unset = UNSET
    provider_cost_limit_micros: int | None | Unset = UNSET
    task_type: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        replayed = self.replayed

        status = self.status.value

        task_id = self.task_id

        agreed_price_micros: int | None | Unset
        if isinstance(self.agreed_price_micros, Unset):
            agreed_price_micros = UNSET
        else:
            agreed_price_micros = self.agreed_price_micros

        external_task_id = self.external_task_id

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        else:
            parent_task_id = self.parent_task_id

        provider_cost_limit_micros: int | None | Unset
        if isinstance(self.provider_cost_limit_micros, Unset):
            provider_cost_limit_micros = UNSET
        else:
            provider_cost_limit_micros = self.provider_cost_limit_micros

        task_type = self.task_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "replayed": replayed,
            "status": status,
            "task_id": task_id,
        })
        if agreed_price_micros is not UNSET:
            field_dict["agreed_price_micros"] = agreed_price_micros
        if external_task_id is not UNSET:
            field_dict["external_task_id"] = external_task_id
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if provider_cost_limit_micros is not UNSET:
            field_dict["provider_cost_limit_micros"] = provider_cost_limit_micros
        if task_type is not UNSET:
            field_dict["task_type"] = task_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        replayed = d.pop("replayed")

        status = StartTaskResponseStatus(d.pop("status"))




        task_id = d.pop("task_id")

        def _parse_agreed_price_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        agreed_price_micros = _parse_agreed_price_micros(d.pop("agreed_price_micros", UNSET))


        external_task_id = d.pop("external_task_id", UNSET)

        def _parse_parent_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_provider_cost_limit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_limit_micros = _parse_provider_cost_limit_micros(d.pop("provider_cost_limit_micros", UNSET))


        task_type = d.pop("task_type", UNSET)

        start_task_response = cls(
            created_at=created_at,
            replayed=replayed,
            status=status,
            task_id=task_id,
            agreed_price_micros=agreed_price_micros,
            external_task_id=external_task_id,
            parent_task_id=parent_task_id,
            provider_cost_limit_micros=provider_cost_limit_micros,
            task_type=task_type,
        )


        start_task_response.additional_properties = d
        return start_task_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
