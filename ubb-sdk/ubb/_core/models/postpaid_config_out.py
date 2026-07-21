from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="PostpaidConfigOut")



@_attrs_define
class PostpaidConfigOut:
    """ 
        Attributes:
            usage_line_item_group_by (str):
            consolidate_with_subscription (bool | Unset):  Default: False.
     """

    usage_line_item_group_by: str
    consolidate_with_subscription: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        usage_line_item_group_by = self.usage_line_item_group_by

        consolidate_with_subscription = self.consolidate_with_subscription


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "usage_line_item_group_by": usage_line_item_group_by,
        })
        if consolidate_with_subscription is not UNSET:
            field_dict["consolidate_with_subscription"] = consolidate_with_subscription

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        usage_line_item_group_by = d.pop("usage_line_item_group_by")

        consolidate_with_subscription = d.pop("consolidate_with_subscription", UNSET)

        postpaid_config_out = cls(
            usage_line_item_group_by=usage_line_item_group_by,
            consolidate_with_subscription=consolidate_with_subscription,
        )


        postpaid_config_out.additional_properties = d
        return postpaid_config_out

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
