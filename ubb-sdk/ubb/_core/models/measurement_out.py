from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.measurement_out_source_kind import MeasurementOutSourceKind
from ..models.measurement_out_value_type import MeasurementOutValueType
from typing import cast






T = TypeVar("T", bound="MeasurementOut")



@_attrs_define
class MeasurementOut:
    """ 
        Attributes:
            advisories (list[str]):
            code (str):
            constant_value (None | str): A constant quantity's declared value: an exact decimal written as a string, for
                both value types. `value_type` gives its meaning: an `integer` constant is a whole number, and a `decimal` one
                may carry a fraction. It is text so that no binary float carries it, and it is not evidence that the value is a
                string. Present exactly when `source_kind` is `constant`. Null for every other kind. Always in its canonical
                form: no unnecessary leading zero, no trailing fractional zero or point, and `0` for every spelling of zero.
            display_name (str):
            required_for_costing (bool):
            source_kind (MeasurementOutSourceKind):
            source_path (list[str]):
            unit (str):
            value_type (MeasurementOutValueType):
     """

    advisories: list[str]
    code: str
    constant_value: None | str
    display_name: str
    required_for_costing: bool
    source_kind: MeasurementOutSourceKind
    source_path: list[str]
    unit: str
    value_type: MeasurementOutValueType
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        advisories = self.advisories



        code = self.code

        constant_value: None | str
        constant_value = self.constant_value

        display_name = self.display_name

        required_for_costing = self.required_for_costing

        source_kind = self.source_kind.value

        source_path = self.source_path



        unit = self.unit

        value_type = self.value_type.value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "advisories": advisories,
            "code": code,
            "constant_value": constant_value,
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

        def _parse_constant_value(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        constant_value = _parse_constant_value(d.pop("constant_value"))


        display_name = d.pop("display_name")

        required_for_costing = d.pop("required_for_costing")

        source_kind = MeasurementOutSourceKind(d.pop("source_kind"))




        source_path = cast(list[str], d.pop("source_path"))


        unit = d.pop("unit")

        value_type = MeasurementOutValueType(d.pop("value_type"))




        measurement_out = cls(
            advisories=advisories,
            code=code,
            constant_value=constant_value,
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
