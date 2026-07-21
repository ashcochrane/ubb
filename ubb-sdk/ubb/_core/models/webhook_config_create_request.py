from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="WebhookConfigCreateRequest")



@_attrs_define
class WebhookConfigCreateRequest:
    """ 
        Attributes:
            event_types (list[str]):
            secret (str):
            url (str):
            is_active (bool | Unset):  Default: True.
     """

    event_types: list[str]
    secret: str
    url: str
    is_active: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        event_types = self.event_types



        secret = self.secret

        url = self.url

        is_active = self.is_active


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event_types": event_types,
            "secret": secret,
            "url": url,
        })
        if is_active is not UNSET:
            field_dict["is_active"] = is_active

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        event_types = cast(list[str], d.pop("event_types"))


        secret = d.pop("secret")

        url = d.pop("url")

        is_active = d.pop("is_active", UNSET)

        webhook_config_create_request = cls(
            event_types=event_types,
            secret=secret,
            url=url,
            is_active=is_active,
        )


        webhook_config_create_request.additional_properties = d
        return webhook_config_create_request

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
