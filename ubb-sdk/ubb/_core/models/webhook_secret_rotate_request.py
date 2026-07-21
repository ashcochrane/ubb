from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="WebhookSecretRotateRequest")



@_attrs_define
class WebhookSecretRotateRequest:
    """ 
        Attributes:
            new_secret (str):
            overlap_hours (int | Unset):  Default: 24.
     """

    new_secret: str
    overlap_hours: int | Unset = 24
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        new_secret = self.new_secret

        overlap_hours = self.overlap_hours


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "new_secret": new_secret,
        })
        if overlap_hours is not UNSET:
            field_dict["overlap_hours"] = overlap_hours

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        new_secret = d.pop("new_secret")

        overlap_hours = d.pop("overlap_hours", UNSET)

        webhook_secret_rotate_request = cls(
            new_secret=new_secret,
            overlap_hours=overlap_hours,
        )


        webhook_secret_rotate_request.additional_properties = d
        return webhook_secret_rotate_request

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
