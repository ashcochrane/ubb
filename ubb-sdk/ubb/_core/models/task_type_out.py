from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.task_type_out_kind import TaskTypeOutKind
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TaskTypeOut")



@_attrs_define
class TaskTypeOut:
    """ 
        Attributes:
            key (str):
            kind (TaskTypeOutKind):
            required_dimensions (list[str]):
            retired (bool):
            default_provider_cost_limit_micros (int | None | Unset):
     """

    key: str
    kind: TaskTypeOutKind
    required_dimensions: list[str]
    retired: bool
    default_provider_cost_limit_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        kind = self.kind.value

        required_dimensions = self.required_dimensions



        retired = self.retired

        default_provider_cost_limit_micros: int | None | Unset
        if isinstance(self.default_provider_cost_limit_micros, Unset):
            default_provider_cost_limit_micros = UNSET
        else:
            default_provider_cost_limit_micros = self.default_provider_cost_limit_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
            "kind": kind,
            "required_dimensions": required_dimensions,
            "retired": retired,
        })
        if default_provider_cost_limit_micros is not UNSET:
            field_dict["default_provider_cost_limit_micros"] = default_provider_cost_limit_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        kind = TaskTypeOutKind(d.pop("kind"))




        required_dimensions = cast(list[str], d.pop("required_dimensions"))


        retired = d.pop("retired")

        def _parse_default_provider_cost_limit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        default_provider_cost_limit_micros = _parse_default_provider_cost_limit_micros(d.pop("default_provider_cost_limit_micros", UNSET))


        task_type_out = cls(
            key=key,
            kind=kind,
            required_dimensions=required_dimensions,
            retired=retired,
            default_provider_cost_limit_micros=default_provider_cost_limit_micros,
        )


        task_type_out.additional_properties = d
        return task_type_out

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
