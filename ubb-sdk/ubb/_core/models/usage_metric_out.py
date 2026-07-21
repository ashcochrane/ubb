from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="UsageMetricOut")



@_attrs_define
class UsageMetricOut:
    """ 
        Attributes:
            billed_cost_micros (int):
            event_count (int):
            event_type (str):
            units (int):
     """

    billed_cost_micros: int
    event_count: int
    event_type: str
    units: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        billed_cost_micros = self.billed_cost_micros

        event_count = self.event_count

        event_type = self.event_type

        units = self.units


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billed_cost_micros": billed_cost_micros,
            "event_count": event_count,
            "event_type": event_type,
            "units": units,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        billed_cost_micros = d.pop("billed_cost_micros")

        event_count = d.pop("event_count")

        event_type = d.pop("event_type")

        units = d.pop("units")

        usage_metric_out = cls(
            billed_cost_micros=billed_cost_micros,
            event_count=event_count,
            event_type=event_type,
            units=units,
        )


        usage_metric_out.additional_properties = d
        return usage_metric_out

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
