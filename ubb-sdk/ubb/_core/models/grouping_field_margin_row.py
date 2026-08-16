from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="GroupingFieldMarginRow")



@_attrs_define
class GroupingFieldMarginRow:
    """ 
        Attributes:
            billed_cost_micros (int):
            event_count (int):
            margin_micros (int):
            provider_cost_micros (int):
            unresolved_event_count (int):
            grouping_field_value (None | str | Unset):
     """

    billed_cost_micros: int
    event_count: int
    margin_micros: int
    provider_cost_micros: int
    unresolved_event_count: int
    grouping_field_value: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        billed_cost_micros = self.billed_cost_micros

        event_count = self.event_count

        margin_micros = self.margin_micros

        provider_cost_micros = self.provider_cost_micros

        unresolved_event_count = self.unresolved_event_count

        grouping_field_value: None | str | Unset
        if isinstance(self.grouping_field_value, Unset):
            grouping_field_value = UNSET
        else:
            grouping_field_value = self.grouping_field_value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billed_cost_micros": billed_cost_micros,
            "event_count": event_count,
            "margin_micros": margin_micros,
            "provider_cost_micros": provider_cost_micros,
            "unresolved_event_count": unresolved_event_count,
        })
        if grouping_field_value is not UNSET:
            field_dict["grouping_field_value"] = grouping_field_value

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        billed_cost_micros = d.pop("billed_cost_micros")

        event_count = d.pop("event_count")

        margin_micros = d.pop("margin_micros")

        provider_cost_micros = d.pop("provider_cost_micros")

        unresolved_event_count = d.pop("unresolved_event_count")

        def _parse_grouping_field_value(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        grouping_field_value = _parse_grouping_field_value(d.pop("grouping_field_value", UNSET))


        grouping_field_margin_row = cls(
            billed_cost_micros=billed_cost_micros,
            event_count=event_count,
            margin_micros=margin_micros,
            provider_cost_micros=provider_cost_micros,
            unresolved_event_count=unresolved_event_count,
            grouping_field_value=grouping_field_value,
        )


        grouping_field_margin_row.additional_properties = d
        return grouping_field_margin_row

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
