from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="MarginThresholdIn")



@_attrs_define
class MarginThresholdIn:
    """ 
        Attributes:
            consecutive_periods (int | Unset):  Default: 1.
            min_margin_pct (float | Unset):  Default: 0.0.
            provider_cost_spike_pct (float | Unset):  Default: 25.0.
     """

    consecutive_periods: int | Unset = 1
    min_margin_pct: float | Unset = 0.0
    provider_cost_spike_pct: float | Unset = 25.0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        consecutive_periods = self.consecutive_periods

        min_margin_pct = self.min_margin_pct

        provider_cost_spike_pct = self.provider_cost_spike_pct


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if consecutive_periods is not UNSET:
            field_dict["consecutive_periods"] = consecutive_periods
        if min_margin_pct is not UNSET:
            field_dict["min_margin_pct"] = min_margin_pct
        if provider_cost_spike_pct is not UNSET:
            field_dict["provider_cost_spike_pct"] = provider_cost_spike_pct

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        consecutive_periods = d.pop("consecutive_periods", UNSET)

        min_margin_pct = d.pop("min_margin_pct", UNSET)

        provider_cost_spike_pct = d.pop("provider_cost_spike_pct", UNSET)

        margin_threshold_in = cls(
            consecutive_periods=consecutive_periods,
            min_margin_pct=min_margin_pct,
            provider_cost_spike_pct=provider_cost_spike_pct,
        )


        margin_threshold_in.additional_properties = d
        return margin_threshold_in

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
