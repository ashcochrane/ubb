from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.grouping_field_out_scope import GroupingFieldOutScope






T = TypeVar("T", bound="GroupingFieldOut")



@_attrs_define
class GroupingFieldOut:
    """ 
        Attributes:
            key (str):
            max_cardinality (int):
            retired (bool):
            scope (GroupingFieldOutScope):
            slot (str):
     """

    key: str
    max_cardinality: int
    retired: bool
    scope: GroupingFieldOutScope
    slot: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        max_cardinality = self.max_cardinality

        retired = self.retired

        scope = self.scope.value

        slot = self.slot


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
            "max_cardinality": max_cardinality,
            "retired": retired,
            "scope": scope,
            "slot": slot,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        max_cardinality = d.pop("max_cardinality")

        retired = d.pop("retired")

        scope = GroupingFieldOutScope(d.pop("scope"))




        slot = d.pop("slot")

        grouping_field_out = cls(
            key=key,
            max_cardinality=max_cardinality,
            retired=retired,
            scope=scope,
            slot=slot,
        )


        grouping_field_out.additional_properties = d
        return grouping_field_out

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
