from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="SubscriptionCancelIn")



@_attrs_define
class SubscriptionCancelIn:
    """ 
        Attributes:
            at_period_end (bool | Unset):  Default: True.
     """

    at_period_end: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        at_period_end = self.at_period_end


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if at_period_end is not UNSET:
            field_dict["at_period_end"] = at_period_end

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        at_period_end = d.pop("at_period_end", UNSET)

        subscription_cancel_in = cls(
            at_period_end=at_period_end,
        )


        subscription_cancel_in.additional_properties = d
        return subscription_cancel_in

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
