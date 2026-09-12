from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.itemised_event_row import ItemisedEventRow





T = TypeVar("T", bound="ItemisedEventsOut")



@_attrs_define
class ItemisedEventsOut:
    """ The events an episode itemises and their totals in both denominations
    — each total adding what is resolved and counting what is not, so a row
    can never read complete while its own events read partial.

        Attributes:
            billed_cost_micros (int):
            event_count (int):
            events (list[ItemisedEventRow]):
            provider_cost_micros (int):
            unpriced_event_count (int):
            unresolved_event_count (int):
     """

    billed_cost_micros: int
    event_count: int
    events: list[ItemisedEventRow]
    provider_cost_micros: int
    unpriced_event_count: int
    unresolved_event_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.itemised_event_row import ItemisedEventRow
        billed_cost_micros = self.billed_cost_micros

        event_count = self.event_count

        events = []
        for events_item_data in self.events:
            events_item = events_item_data.to_dict()
            events.append(events_item)



        provider_cost_micros = self.provider_cost_micros

        unpriced_event_count = self.unpriced_event_count

        unresolved_event_count = self.unresolved_event_count


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billed_cost_micros": billed_cost_micros,
            "event_count": event_count,
            "events": events,
            "provider_cost_micros": provider_cost_micros,
            "unpriced_event_count": unpriced_event_count,
            "unresolved_event_count": unresolved_event_count,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.itemised_event_row import ItemisedEventRow
        d = dict(src_dict)
        billed_cost_micros = d.pop("billed_cost_micros")

        event_count = d.pop("event_count")

        events = []
        _events = d.pop("events")
        for events_item_data in (_events):
            events_item = ItemisedEventRow.from_dict(events_item_data)



            events.append(events_item)


        provider_cost_micros = d.pop("provider_cost_micros")

        unpriced_event_count = d.pop("unpriced_event_count")

        unresolved_event_count = d.pop("unresolved_event_count")

        itemised_events_out = cls(
            billed_cost_micros=billed_cost_micros,
            event_count=event_count,
            events=events,
            provider_cost_micros=provider_cost_micros,
            unpriced_event_count=unpriced_event_count,
            unresolved_event_count=unresolved_event_count,
        )


        itemised_events_out.additional_properties = d
        return itemised_events_out

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
