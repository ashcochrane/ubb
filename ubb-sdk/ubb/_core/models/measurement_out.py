from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.measurement_out_source_kind import MeasurementOutSourceKind
from typing import cast






T = TypeVar("T", bound="MeasurementOut")



@_attrs_define
class MeasurementOut:
    """ 
        Attributes:
            advisories (list[str]):
            code (str):
            display_name (str):
            required_for_costing (bool):
            source_kind (MeasurementOutSourceKind):
            source_path (list[str]):
            unit (str):
            value_type (str):
     """

    advisories: list[str]
    code: str
    display_name: str
    required_for_costing: bool
    source_kind: MeasurementOutSourceKind
    source_path: list[str]
    unit: str
    value_type: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        advisories = self.advisories



        code = self.code

        display_name = self.display_name

        required_for_costing = self.required_for_costing

        source_kind = self.source_kind.value

        source_path = self.source_path



        unit = self.unit

        value_type = self.value_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "advisories": advisories,
            "code": code,
            "display_name": display_name,
            "required_for_costing": required_for_costing,
            "source_kind": source_kind,
            "source_path": source_path,
            "unit": unit,
            "value_type": value_type,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        advisories = cast(list[str], d.pop("advisories"))


        code = d.pop("code")

        display_name = d.pop("display_name")

        required_for_costing = d.pop("required_for_costing")

        source_kind = MeasurementOutSourceKind(d.pop("source_kind"))




        source_path = cast(list[str], d.pop("source_path"))


        unit = d.pop("unit")

        value_type = d.pop("value_type")

        measurement_out = cls(
            advisories=advisories,
            code=code,
            display_name=display_name,
            required_for_costing=required_for_costing,
            source_kind=source_kind,
            source_path=source_path,
            unit=unit,
            value_type=value_type,
        )


        measurement_out.additional_properties = d
        return measurement_out

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
