from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="UnsupportedMeasureOut")



@_attrs_define
class UnsupportedMeasureOut:
    """ One measure an axis REFUSES, and why.

    Declaring capability by exception rather than by enumeration: every measure
    not named here is accepted at this axis and answers with its own state. The
    set these are exceptions to is published by the one economic query, which is
    the module that computes the measures — this read only ever names one in
    order to refuse it.

        Attributes:
            measure (str):
            reason (str):
     """

    measure: str
    reason: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        measure = self.measure

        reason = self.reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "measure": measure,
            "reason": reason,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        measure = d.pop("measure")

        reason = d.pop("reason")

        unsupported_measure_out = cls(
            measure=measure,
            reason=reason,
        )


        unsupported_measure_out.additional_properties = d
        return unsupported_measure_out

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
