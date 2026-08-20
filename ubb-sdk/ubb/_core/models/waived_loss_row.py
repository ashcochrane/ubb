from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="WaivedLossRow")



@_attrs_define
class WaivedLossRow:
    """ What waiving cost this tenant in one currency.

        Attributes:
            currency (str):
            provider_cost_micros (int):
            unresolved_event_count (int):
            waived_event_count (int):
     """

    currency: str
    provider_cost_micros: int
    unresolved_event_count: int
    waived_event_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        currency = self.currency

        provider_cost_micros = self.provider_cost_micros

        unresolved_event_count = self.unresolved_event_count

        waived_event_count = self.waived_event_count


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "currency": currency,
            "provider_cost_micros": provider_cost_micros,
            "unresolved_event_count": unresolved_event_count,
            "waived_event_count": waived_event_count,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        currency = d.pop("currency")

        provider_cost_micros = d.pop("provider_cost_micros")

        unresolved_event_count = d.pop("unresolved_event_count")

        waived_event_count = d.pop("waived_event_count")

        waived_loss_row = cls(
            currency=currency,
            provider_cost_micros=provider_cost_micros,
            unresolved_event_count=unresolved_event_count,
            waived_event_count=waived_event_count,
        )


        waived_loss_row.additional_properties = d
        return waived_loss_row

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
