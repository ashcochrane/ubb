from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.spend_control_family_totals_row_control_family import SpendControlFamilyTotalsRowControlFamily






T = TypeVar("T", bound="SpendControlFamilyTotalsRow")



@_attrs_define
class SpendControlFamilyTotalsRow:
    """ One family's totals over exactly the itemised events of the episodes
    shown, each event counted once per family, both denominations.

        Attributes:
            billed_cost_micros (int):
            control_family (SpendControlFamilyTotalsRowControlFamily):
            event_count (int):
            provider_cost_micros (int):
            unpriced_event_count (int):
            unresolved_event_count (int):
     """

    billed_cost_micros: int
    control_family: SpendControlFamilyTotalsRowControlFamily
    event_count: int
    provider_cost_micros: int
    unpriced_event_count: int
    unresolved_event_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        billed_cost_micros = self.billed_cost_micros

        control_family = self.control_family.value

        event_count = self.event_count

        provider_cost_micros = self.provider_cost_micros

        unpriced_event_count = self.unpriced_event_count

        unresolved_event_count = self.unresolved_event_count


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billed_cost_micros": billed_cost_micros,
            "control_family": control_family,
            "event_count": event_count,
            "provider_cost_micros": provider_cost_micros,
            "unpriced_event_count": unpriced_event_count,
            "unresolved_event_count": unresolved_event_count,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        billed_cost_micros = d.pop("billed_cost_micros")

        control_family = SpendControlFamilyTotalsRowControlFamily(d.pop("control_family"))




        event_count = d.pop("event_count")

        provider_cost_micros = d.pop("provider_cost_micros")

        unpriced_event_count = d.pop("unpriced_event_count")

        unresolved_event_count = d.pop("unresolved_event_count")

        spend_control_family_totals_row = cls(
            billed_cost_micros=billed_cost_micros,
            control_family=control_family,
            event_count=event_count,
            provider_cost_micros=provider_cost_micros,
            unpriced_event_count=unpriced_event_count,
            unresolved_event_count=unresolved_event_count,
        )


        spend_control_family_totals_row.additional_properties = d
        return spend_control_family_totals_row

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
