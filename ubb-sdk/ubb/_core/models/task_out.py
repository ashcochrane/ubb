from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.task_out_dimensions import TaskOutDimensions





T = TypeVar("T", bound="TaskOut")



@_attrs_define
class TaskOut:
    """ 
        Attributes:
            created_at (str):
            event_count (int):
            status (str):
            task_id (str):
            total_billed_cost_micros (int):
            total_provider_cost_micros (int):
            unpriced_event_count (int):
            unresolved_event_count (int):
            completed_at (None | str | Unset):
            dimensions (TaskOutDimensions | Unset):
            parent_task_id (None | str | Unset):
            provider_cost_limit_micros (int | None | Unset):
            task_type (str | Unset):  Default: ''.
     """

    created_at: str
    event_count: int
    status: str
    task_id: str
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    unpriced_event_count: int
    unresolved_event_count: int
    completed_at: None | str | Unset = UNSET
    dimensions: TaskOutDimensions | Unset = UNSET
    parent_task_id: None | str | Unset = UNSET
    provider_cost_limit_micros: int | None | Unset = UNSET
    task_type: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.task_out_dimensions import TaskOutDimensions
        created_at = self.created_at

        event_count = self.event_count

        status = self.status

        task_id = self.task_id

        total_billed_cost_micros = self.total_billed_cost_micros

        total_provider_cost_micros = self.total_provider_cost_micros

        unpriced_event_count = self.unpriced_event_count

        unresolved_event_count = self.unresolved_event_count

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        else:
            completed_at = self.completed_at

        dimensions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.dimensions, Unset):
            dimensions = self.dimensions.to_dict()

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
            "event_count": event_count,
            "status": status,
            "task_id": task_id,
            "total_billed_cost_micros": total_billed_cost_micros,
            "total_provider_cost_micros": total_provider_cost_micros,
            "unpriced_event_count": unpriced_event_count,
            "unresolved_event_count": unresolved_event_count,
        })
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if dimensions is not UNSET:
            field_dict["dimensions"] = dimensions
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if provider_cost_limit_micros is not UNSET:
            field_dict["provider_cost_limit_micros"] = provider_cost_limit_micros
        if task_type is not UNSET:
            field_dict["task_type"] = task_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_out_dimensions import TaskOutDimensions
        d = dict(src_dict)
        created_at = d.pop("created_at")

        event_count = d.pop("event_count")

        status = d.pop("status")

        task_id = d.pop("task_id")

        total_billed_cost_micros = d.pop("total_billed_cost_micros")

        total_provider_cost_micros = d.pop("total_provider_cost_micros")

        unpriced_event_count = d.pop("unpriced_event_count")

        unresolved_event_count = d.pop("unresolved_event_count")

        def _parse_completed_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))


        _dimensions = d.pop("dimensions", UNSET)
        dimensions: TaskOutDimensions | Unset
        if isinstance(_dimensions,  Unset):
            dimensions = UNSET
        else:
            dimensions = TaskOutDimensions.from_dict(_dimensions)




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

        task_out = cls(
            created_at=created_at,
            event_count=event_count,
            status=status,
            task_id=task_id,
            total_billed_cost_micros=total_billed_cost_micros,
            total_provider_cost_micros=total_provider_cost_micros,
            unpriced_event_count=unpriced_event_count,
            unresolved_event_count=unresolved_event_count,
            completed_at=completed_at,
            dimensions=dimensions,
            parent_task_id=parent_task_id,
            provider_cost_limit_micros=provider_cost_limit_micros,
            task_type=task_type,
        )


        task_out.additional_properties = d
        return task_out

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
