from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="CloseTaskResponse")



@_attrs_define
class CloseTaskResponse:
    """ 
        Attributes:
            event_count (int):
            status (str):
            task_id (str):
            total_billed_cost_micros (int):
            total_provider_cost_micros (int):
            parent_task_id (None | str | Unset):
     """

    event_count: int
    status: str
    task_id: str
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    parent_task_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        event_count = self.event_count

        status = self.status

        task_id = self.task_id

        total_billed_cost_micros = self.total_billed_cost_micros

        total_provider_cost_micros = self.total_provider_cost_micros

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        else:
            parent_task_id = self.parent_task_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event_count": event_count,
            "status": status,
            "task_id": task_id,
            "total_billed_cost_micros": total_billed_cost_micros,
            "total_provider_cost_micros": total_provider_cost_micros,
        })
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        event_count = d.pop("event_count")

        status = d.pop("status")

        task_id = d.pop("task_id")

        total_billed_cost_micros = d.pop("total_billed_cost_micros")

        total_provider_cost_micros = d.pop("total_provider_cost_micros")

        def _parse_parent_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        close_task_response = cls(
            event_count=event_count,
            status=status,
            task_id=task_id,
            total_billed_cost_micros=total_billed_cost_micros,
            total_provider_cost_micros=total_provider_cost_micros,
            parent_task_id=parent_task_id,
        )


        close_task_response.additional_properties = d
        return close_task_response

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
