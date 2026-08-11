from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.event_type_in_costing_method import EventTypeInCostingMethod
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="EventTypeIn")



@_attrs_define
class EventTypeIn:
    """ 
        Attributes:
            costing_method (EventTypeInCostingMethod):
            key (str):
            category_key (None | str | Unset):
            provider_key (None | str | Unset):
            source_shape_id (str | Unset):  Default: ''.
            source_shape_label (str | Unset):  Default: ''.
     """

    costing_method: EventTypeInCostingMethod
    key: str
    category_key: None | str | Unset = UNSET
    provider_key: None | str | Unset = UNSET
    source_shape_id: str | Unset = ''
    source_shape_label: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        costing_method = self.costing_method.value

        key = self.key

        category_key: None | str | Unset
        if isinstance(self.category_key, Unset):
            category_key = UNSET
        else:
            category_key = self.category_key

        provider_key: None | str | Unset
        if isinstance(self.provider_key, Unset):
            provider_key = UNSET
        else:
            provider_key = self.provider_key

        source_shape_id = self.source_shape_id

        source_shape_label = self.source_shape_label


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "costing_method": costing_method,
            "key": key,
        })
        if category_key is not UNSET:
            field_dict["category_key"] = category_key
        if provider_key is not UNSET:
            field_dict["provider_key"] = provider_key
        if source_shape_id is not UNSET:
            field_dict["source_shape_id"] = source_shape_id
        if source_shape_label is not UNSET:
            field_dict["source_shape_label"] = source_shape_label

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        costing_method = EventTypeInCostingMethod(d.pop("costing_method"))




        key = d.pop("key")

        def _parse_category_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        category_key = _parse_category_key(d.pop("category_key", UNSET))


        def _parse_provider_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_key = _parse_provider_key(d.pop("provider_key", UNSET))


        source_shape_id = d.pop("source_shape_id", UNSET)

        source_shape_label = d.pop("source_shape_label", UNSET)

        event_type_in = cls(
            costing_method=costing_method,
            key=key,
            category_key=category_key,
            provider_key=provider_key,
            source_shape_id=source_shape_id,
            source_shape_label=source_shape_label,
        )


        event_type_in.additional_properties = d
        return event_type_in

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
