from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="DimensionMarginRow")



@_attrs_define
class DimensionMarginRow:
    """ 
        Attributes:
            billed_cost_micros (int):
            event_count (int):
            margin_micros (int):
            provider_cost_micros (int):
            dimension (None | str | Unset):
     """

    billed_cost_micros: int
    event_count: int
    margin_micros: int
    provider_cost_micros: int
    dimension: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        billed_cost_micros = self.billed_cost_micros

        event_count = self.event_count

        margin_micros = self.margin_micros

        provider_cost_micros = self.provider_cost_micros

        dimension: None | str | Unset
        if isinstance(self.dimension, Unset):
            dimension = UNSET
        else:
            dimension = self.dimension


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billed_cost_micros": billed_cost_micros,
            "event_count": event_count,
            "margin_micros": margin_micros,
            "provider_cost_micros": provider_cost_micros,
        })
        if dimension is not UNSET:
            field_dict["dimension"] = dimension

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        billed_cost_micros = d.pop("billed_cost_micros")

        event_count = d.pop("event_count")

        margin_micros = d.pop("margin_micros")

        provider_cost_micros = d.pop("provider_cost_micros")

        def _parse_dimension(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dimension = _parse_dimension(d.pop("dimension", UNSET))


        dimension_margin_row = cls(
            billed_cost_micros=billed_cost_micros,
            event_count=event_count,
            margin_micros=margin_micros,
            provider_cost_micros=provider_cost_micros,
            dimension=dimension,
        )


        dimension_margin_row.additional_properties = d
        return dimension_margin_row

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
