from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="IntegrationBlueprintVerificationRecordInMeasurements")



@_attrs_define
class IntegrationBlueprintVerificationRecordInMeasurements:
    """ Each quantity is an exact decimal written as a STRING — `"12"`, `"2.5"`, `"-3"`, `"0"` — never a JSON number, which
    most clients have already carried as a binary float. Base-10 digits with an optional leading `-` and an optional
    fractional part, a digit on each side of the point: no exponent, no `+`, and no spaces, separators or locale
    formatting. No precision or scale is imposed. A quantity may be negative, and zero is a recorded value. Where the
    event's Event Type declares the key, its `value_type` decides whether a fraction is allowed (`integer` refuses one);
    a key no publication declares is accepted and held as written. Every value is stored and answered in its canonical
    form: no unnecessary leading zero, no trailing fractional zero or point, and `0` for every spelling of zero.

     """

    additional_properties: dict[str, str] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        
        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        integration_blueprint_verification_record_in_measurements = cls(
        )


        integration_blueprint_verification_record_in_measurements.additional_properties = d
        return integration_blueprint_verification_record_in_measurements

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> str:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: str) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
