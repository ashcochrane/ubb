from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="WebhookConfigResponse")



@_attrs_define
class WebhookConfigResponse:
    """ 
        Attributes:
            created_at (str):
            event_types (list[str]):
            id (str):
            is_active (bool):
            url (str):
            retiring_secret_expires_at (None | str | Unset):
     """

    created_at: str
    event_types: list[str]
    id: str
    is_active: bool
    url: str
    retiring_secret_expires_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        event_types = self.event_types



        id = self.id

        is_active = self.is_active

        url = self.url

        retiring_secret_expires_at: None | str | Unset
        if isinstance(self.retiring_secret_expires_at, Unset):
            retiring_secret_expires_at = UNSET
        else:
            retiring_secret_expires_at = self.retiring_secret_expires_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "event_types": event_types,
            "id": id,
            "is_active": is_active,
            "url": url,
        })
        if retiring_secret_expires_at is not UNSET:
            field_dict["retiring_secret_expires_at"] = retiring_secret_expires_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        event_types = cast(list[str], d.pop("event_types"))


        id = d.pop("id")

        is_active = d.pop("is_active")

        url = d.pop("url")

        def _parse_retiring_secret_expires_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        retiring_secret_expires_at = _parse_retiring_secret_expires_at(d.pop("retiring_secret_expires_at", UNSET))


        webhook_config_response = cls(
            created_at=created_at,
            event_types=event_types,
            id=id,
            is_active=is_active,
            url=url,
            retiring_secret_expires_at=retiring_secret_expires_at,
        )


        webhook_config_response.additional_properties = d
        return webhook_config_response

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
