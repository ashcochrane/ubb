from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.task_type_out import TaskTypeOut





T = TypeVar("T", bound="TaskTypeRegistryOut")



@_attrs_define
class TaskTypeRegistryOut:
    """ 
        Attributes:
            task_types (list[TaskTypeOut]):
     """

    task_types: list[TaskTypeOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.task_type_out import TaskTypeOut
        task_types = []
        for task_types_item_data in self.task_types:
            task_types_item = task_types_item_data.to_dict()
            task_types.append(task_types_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "task_types": task_types,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_type_out import TaskTypeOut
        d = dict(src_dict)
        task_types = []
        _task_types = d.pop("task_types")
        for task_types_item_data in (_task_types):
            task_types_item = TaskTypeOut.from_dict(task_types_item_data)



            task_types.append(task_types_item)


        task_type_registry_out = cls(
            task_types=task_types,
        )


        task_type_registry_out.additional_properties = d
        return task_type_registry_out

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
