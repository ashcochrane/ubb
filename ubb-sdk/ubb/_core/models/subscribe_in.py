from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="SubscribeIn")



@_attrs_define
class SubscribeIn:
    """ 
        Attributes:
            plan_key (str):
            seats (int | Unset):  Default: 0.
     """

    plan_key: str
    seats: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        plan_key = self.plan_key

        seats = self.seats


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "plan_key": plan_key,
        })
        if seats is not UNSET:
            field_dict["seats"] = seats

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        plan_key = d.pop("plan_key")

        seats = d.pop("seats", UNSET)

        subscribe_in = cls(
            plan_key=plan_key,
            seats=seats,
        )


        subscribe_in.additional_properties = d
        return subscribe_in

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
