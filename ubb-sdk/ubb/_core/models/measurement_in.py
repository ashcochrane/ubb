from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.measurement_in_source_kind import MeasurementInSourceKind
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="MeasurementIn")



@_attrs_define
class MeasurementIn:
    """ One measurable quantity an Event Type produces.

    The code is the path segment rather than a body field: it is this
    declaration's identity beneath its Event Type, and a body that could
    disagree with the URL would make "which declaration is this" a question
    with two answers.

        Attributes:
            source_kind (MeasurementInSourceKind):
            unit (str):
            value_type (str):
            display_name (str | Unset):  Default: ''.
            required_for_costing (bool | Unset):  Default: False.
            source_path (list[str] | Unset):
     """

    source_kind: MeasurementInSourceKind
    unit: str
    value_type: str
    display_name: str | Unset = ''
    required_for_costing: bool | Unset = False
    source_path: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        source_kind = self.source_kind.value

        unit = self.unit

        value_type = self.value_type

        display_name = self.display_name

        required_for_costing = self.required_for_costing

        source_path: list[str] | Unset = UNSET
        if not isinstance(self.source_path, Unset):
            source_path = self.source_path




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "source_kind": source_kind,
            "unit": unit,
            "value_type": value_type,
        })
        if display_name is not UNSET:
            field_dict["display_name"] = display_name
        if required_for_costing is not UNSET:
            field_dict["required_for_costing"] = required_for_costing
        if source_path is not UNSET:
            field_dict["source_path"] = source_path

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source_kind = MeasurementInSourceKind(d.pop("source_kind"))




        unit = d.pop("unit")

        value_type = d.pop("value_type")

        display_name = d.pop("display_name", UNSET)

        required_for_costing = d.pop("required_for_costing", UNSET)

        source_path = cast(list[str], d.pop("source_path", UNSET))


        measurement_in = cls(
            source_kind=source_kind,
            unit=unit,
            value_type=value_type,
            display_name=display_name,
            required_for_costing=required_for_costing,
            source_path=source_path,
        )


        measurement_in.additional_properties = d
        return measurement_in

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
