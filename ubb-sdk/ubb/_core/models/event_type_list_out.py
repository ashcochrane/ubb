from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.event_type_out import EventTypeOut





T = TypeVar("T", bound="EventTypeListOut")



@_attrs_define
class EventTypeListOut:
    """ 
        Attributes:
            event_types (list[EventTypeOut]):
     """

    event_types: list[EventTypeOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.event_type_out import EventTypeOut
        event_types = []
        for event_types_item_data in self.event_types:
            event_types_item = event_types_item_data.to_dict()
            event_types.append(event_types_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event_types": event_types,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.event_type_out import EventTypeOut
        d = dict(src_dict)
        event_types = []
        _event_types = d.pop("event_types")
        for event_types_item_data in (_event_types):
            event_types_item = EventTypeOut.from_dict(event_types_item_data)



            event_types.append(event_types_item)


        event_type_list_out = cls(
            event_types=event_types,
        )


        event_type_list_out.additional_properties = d
        return event_type_list_out

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
