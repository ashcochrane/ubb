from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="PostpaidConfigIn")



@_attrs_define
class PostpaidConfigIn:
    """ 
        Attributes:
            consolidate_with_subscription (bool | None | Unset):
            usage_line_item_group_by (None | str | Unset):
     """

    consolidate_with_subscription: bool | None | Unset = UNSET
    usage_line_item_group_by: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        consolidate_with_subscription: bool | None | Unset
        if isinstance(self.consolidate_with_subscription, Unset):
            consolidate_with_subscription = UNSET
        else:
            consolidate_with_subscription = self.consolidate_with_subscription

        usage_line_item_group_by: None | str | Unset
        if isinstance(self.usage_line_item_group_by, Unset):
            usage_line_item_group_by = UNSET
        else:
            usage_line_item_group_by = self.usage_line_item_group_by


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if consolidate_with_subscription is not UNSET:
            field_dict["consolidate_with_subscription"] = consolidate_with_subscription
        if usage_line_item_group_by is not UNSET:
            field_dict["usage_line_item_group_by"] = usage_line_item_group_by

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_consolidate_with_subscription(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        consolidate_with_subscription = _parse_consolidate_with_subscription(d.pop("consolidate_with_subscription", UNSET))


        def _parse_usage_line_item_group_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        usage_line_item_group_by = _parse_usage_line_item_group_by(d.pop("usage_line_item_group_by", UNSET))


        postpaid_config_in = cls(
            consolidate_with_subscription=consolidate_with_subscription,
            usage_line_item_group_by=usage_line_item_group_by,
        )


        postpaid_config_in.additional_properties = d
        return postpaid_config_in

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
