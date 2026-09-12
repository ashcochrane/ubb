from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.webhook_config_response_event_types_item_type_0 import WebhookConfigResponseEventTypesItemType0
from ..types import UNSET, Unset
from typing import cast
from typing import Literal, cast






T = TypeVar("T", bound="WebhookConfigResponse")



@_attrs_define
class WebhookConfigResponse:
    """ 
        Attributes:
            created_at (str):
            event_types (list[Literal['*'] | WebhookConfigResponseEventTypesItemType0]):
            id (str):
            is_active (bool):
            url (str):
            retiring_secret_expires_at (None | str | Unset):
     """

    created_at: str
    event_types: list[Literal['*'] | WebhookConfigResponseEventTypesItemType0]
    id: str
    is_active: bool
    url: str
    retiring_secret_expires_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        event_types = []
        for event_types_item_data in self.event_types:
            event_types_item: Literal['*'] | str
            if isinstance(event_types_item_data, WebhookConfigResponseEventTypesItemType0):
                event_types_item = event_types_item_data.value
            else:
                event_types_item = event_types_item_data
            event_types.append(event_types_item)



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

        event_types = []
        _event_types = d.pop("event_types")
        for event_types_item_data in (_event_types):
            def _parse_event_types_item(data: object) -> Literal['*'] | WebhookConfigResponseEventTypesItemType0:
                try:
                    if not isinstance(data, str):
                        raise TypeError()
                    event_types_item_type_0 = WebhookConfigResponseEventTypesItemType0(data)



                    return event_types_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                event_types_item_type_1 = cast(Literal['*'] , data)
                if event_types_item_type_1 != '*':
                    raise ValueError(f"event_types_item_type_1 must match const '*', got '{event_types_item_type_1}'")
                return event_types_item_type_1

            event_types_item = _parse_event_types_item(event_types_item_data)

            event_types.append(event_types_item)


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
