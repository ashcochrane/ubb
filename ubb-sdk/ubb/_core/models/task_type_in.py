from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TaskTypeIn")



@_attrs_define
class TaskTypeIn:
    """ 
        Attributes:
            key (str):
            default_provider_cost_limit_micros (int | None | Unset):
            kind (str | Unset):  Default: 'task'.
            required_dimensions (list[str] | Unset):
     """

    key: str
    default_provider_cost_limit_micros: int | None | Unset = UNSET
    kind: str | Unset = 'task'
    required_dimensions: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        default_provider_cost_limit_micros: int | None | Unset
        if isinstance(self.default_provider_cost_limit_micros, Unset):
            default_provider_cost_limit_micros = UNSET
        else:
            default_provider_cost_limit_micros = self.default_provider_cost_limit_micros

        kind = self.kind

        required_dimensions: list[str] | Unset = UNSET
        if not isinstance(self.required_dimensions, Unset):
            required_dimensions = self.required_dimensions




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
        })
        if default_provider_cost_limit_micros is not UNSET:
            field_dict["default_provider_cost_limit_micros"] = default_provider_cost_limit_micros
        if kind is not UNSET:
            field_dict["kind"] = kind
        if required_dimensions is not UNSET:
            field_dict["required_dimensions"] = required_dimensions

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        def _parse_default_provider_cost_limit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        default_provider_cost_limit_micros = _parse_default_provider_cost_limit_micros(d.pop("default_provider_cost_limit_micros", UNSET))


        kind = d.pop("kind", UNSET)

        required_dimensions = cast(list[str], d.pop("required_dimensions", UNSET))


        task_type_in = cls(
            key=key,
            default_provider_cost_limit_micros=default_provider_cost_limit_micros,
            kind=kind,
            required_dimensions=required_dimensions,
        )


        task_type_in.additional_properties = d
        return task_type_in

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
