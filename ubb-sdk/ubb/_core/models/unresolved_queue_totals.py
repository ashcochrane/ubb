from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="UnresolvedQueueTotals")



@_attrs_define
class UnresolvedQueueTotals:
    """ What the queue has already cost, in one currency, and what it left out.

        Attributes:
            currency (str):
            provider_cost_micros (int):
            queued_event_count (int):
            unresolved_event_count (int):
     """

    currency: str
    provider_cost_micros: int
    queued_event_count: int
    unresolved_event_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        currency = self.currency

        provider_cost_micros = self.provider_cost_micros

        queued_event_count = self.queued_event_count

        unresolved_event_count = self.unresolved_event_count


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "currency": currency,
            "provider_cost_micros": provider_cost_micros,
            "queued_event_count": queued_event_count,
            "unresolved_event_count": unresolved_event_count,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        currency = d.pop("currency")

        provider_cost_micros = d.pop("provider_cost_micros")

        queued_event_count = d.pop("queued_event_count")

        unresolved_event_count = d.pop("unresolved_event_count")

        unresolved_queue_totals = cls(
            currency=currency,
            provider_cost_micros=provider_cost_micros,
            queued_event_count=queued_event_count,
            unresolved_event_count=unresolved_event_count,
        )


        unresolved_queue_totals.additional_properties = d
        return unresolved_queue_totals

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
