from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ResolutionRunSelectorOut")



@_attrs_define
class ResolutionRunSelectorOut:
    """ The three axes, as they were stated — echoed so the record of the act and
    the answer to the request cannot describe the same run differently.

        Attributes:
            selected_customer_id (None | str | Unset):
            selected_event_type (None | str | Unset):
            selected_from (None | str | Unset):
            selected_to (None | str | Unset):
     """

    selected_customer_id: None | str | Unset = UNSET
    selected_event_type: None | str | Unset = UNSET
    selected_from: None | str | Unset = UNSET
    selected_to: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        selected_customer_id: None | str | Unset
        if isinstance(self.selected_customer_id, Unset):
            selected_customer_id = UNSET
        else:
            selected_customer_id = self.selected_customer_id

        selected_event_type: None | str | Unset
        if isinstance(self.selected_event_type, Unset):
            selected_event_type = UNSET
        else:
            selected_event_type = self.selected_event_type

        selected_from: None | str | Unset
        if isinstance(self.selected_from, Unset):
            selected_from = UNSET
        else:
            selected_from = self.selected_from

        selected_to: None | str | Unset
        if isinstance(self.selected_to, Unset):
            selected_to = UNSET
        else:
            selected_to = self.selected_to


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if selected_customer_id is not UNSET:
            field_dict["selected_customer_id"] = selected_customer_id
        if selected_event_type is not UNSET:
            field_dict["selected_event_type"] = selected_event_type
        if selected_from is not UNSET:
            field_dict["selected_from"] = selected_from
        if selected_to is not UNSET:
            field_dict["selected_to"] = selected_to

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_selected_customer_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        selected_customer_id = _parse_selected_customer_id(d.pop("selected_customer_id", UNSET))


        def _parse_selected_event_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        selected_event_type = _parse_selected_event_type(d.pop("selected_event_type", UNSET))


        def _parse_selected_from(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        selected_from = _parse_selected_from(d.pop("selected_from", UNSET))


        def _parse_selected_to(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        selected_to = _parse_selected_to(d.pop("selected_to", UNSET))


        resolution_run_selector_out = cls(
            selected_customer_id=selected_customer_id,
            selected_event_type=selected_event_type,
            selected_from=selected_from,
            selected_to=selected_to,
        )


        resolution_run_selector_out.additional_properties = d
        return resolution_run_selector_out

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
