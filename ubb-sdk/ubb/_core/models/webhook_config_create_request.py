from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.webhook_config_create_request_event_types_item_type_0 import WebhookConfigCreateRequestEventTypesItemType0
from ..types import UNSET, Unset
from typing import cast
from typing import Literal, cast






T = TypeVar("T", bound="WebhookConfigCreateRequest")



@_attrs_define
class WebhookConfigCreateRequest:
    """ 
        Attributes:
            event_types (list[Literal['*'] | WebhookConfigCreateRequestEventTypesItemType0]):
            secret (str):
            url (str):
            is_active (bool | Unset):  Default: True.
     """

    event_types: list[Literal['*'] | WebhookConfigCreateRequestEventTypesItemType0]
    secret: str
    url: str
    is_active: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        event_types = []
        for event_types_item_data in self.event_types:
            event_types_item: Literal['*'] | str
            if isinstance(event_types_item_data, WebhookConfigCreateRequestEventTypesItemType0):
                event_types_item = event_types_item_data.value
            else:
                event_types_item = event_types_item_data
            event_types.append(event_types_item)



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
        event_types = []
        _event_types = d.pop("event_types")
        for event_types_item_data in (_event_types):
            def _parse_event_types_item(data: object) -> Literal['*'] | WebhookConfigCreateRequestEventTypesItemType0:
                try:
                    if not isinstance(data, str):
                        raise TypeError()
                    event_types_item_type_0 = WebhookConfigCreateRequestEventTypesItemType0(data)



                    return event_types_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                event_types_item_type_1 = cast(Literal['*'] , data)
                if event_types_item_type_1 != '*':
                    raise ValueError(f"event_types_item_type_1 must match const '*', got '{event_types_item_type_1}'")
                return event_types_item_type_1

            event_types_item = _parse_event_types_item(event_types_item_data)

            event_types.append(event_types_item)


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
