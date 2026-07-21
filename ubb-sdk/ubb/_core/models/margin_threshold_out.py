from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="MarginThresholdOut")



@_attrs_define
class MarginThresholdOut:
    """ 
        Attributes:
            consecutive_periods (int):
            min_margin_pct (float):
            provider_cost_spike_pct (float):
     """

    consecutive_periods: int
    min_margin_pct: float
    provider_cost_spike_pct: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        consecutive_periods = self.consecutive_periods

        min_margin_pct = self.min_margin_pct

        provider_cost_spike_pct = self.provider_cost_spike_pct


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "consecutive_periods": consecutive_periods,
            "min_margin_pct": min_margin_pct,
            "provider_cost_spike_pct": provider_cost_spike_pct,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        consecutive_periods = d.pop("consecutive_periods")

        min_margin_pct = d.pop("min_margin_pct")

        provider_cost_spike_pct = d.pop("provider_cost_spike_pct")

        margin_threshold_out = cls(
            consecutive_periods=consecutive_periods,
            min_margin_pct=min_margin_pct,
            provider_cost_spike_pct=provider_cost_spike_pct,
        )


        margin_threshold_out.additional_properties = d
        return margin_threshold_out

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
