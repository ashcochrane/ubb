from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="DimensionDefIn")



@_attrs_define
class DimensionDefIn:
    """ 
        Attributes:
            key (str):
            slot (str):
            max_cardinality (int | Unset):  Default: 100.
            scope (str | Unset):  Default: 'event'.
     """

    key: str
    slot: str
    max_cardinality: int | Unset = 100
    scope: str | Unset = 'event'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        slot = self.slot

        max_cardinality = self.max_cardinality

        scope = self.scope


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
            "slot": slot,
        })
        if max_cardinality is not UNSET:
            field_dict["max_cardinality"] = max_cardinality
        if scope is not UNSET:
            field_dict["scope"] = scope

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        slot = d.pop("slot")

        max_cardinality = d.pop("max_cardinality", UNSET)

        scope = d.pop("scope", UNSET)

        dimension_def_in = cls(
            key=key,
            slot=slot,
            max_cardinality=max_cardinality,
            scope=scope,
        )


        dimension_def_in.additional_properties = d
        return dimension_def_in

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
