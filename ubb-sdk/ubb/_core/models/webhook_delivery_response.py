from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="WebhookDeliveryResponse")



@_attrs_define
class WebhookDeliveryResponse:
    """ 
        Attributes:
            created_at (str):
            error_message (str):
            event_id (str):
            event_type (str):
            id (str):
            success (bool):
            status_code (int | None | Unset):
     """

    created_at: str
    error_message: str
    event_id: str
    event_type: str
    id: str
    success: bool
    status_code: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        error_message = self.error_message

        event_id = self.event_id

        event_type = self.event_type

        id = self.id

        success = self.success

        status_code: int | None | Unset
        if isinstance(self.status_code, Unset):
            status_code = UNSET
        else:
            status_code = self.status_code


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "error_message": error_message,
            "event_id": event_id,
            "event_type": event_type,
            "id": id,
            "success": success,
        })
        if status_code is not UNSET:
            field_dict["status_code"] = status_code

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        error_message = d.pop("error_message")

        event_id = d.pop("event_id")

        event_type = d.pop("event_type")

        id = d.pop("id")

        success = d.pop("success")

        def _parse_status_code(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        status_code = _parse_status_code(d.pop("status_code", UNSET))


        webhook_delivery_response = cls(
            created_at=created_at,
            error_message=error_message,
            event_id=event_id,
            event_type=event_type,
            id=id,
            success=success,
            status_code=status_code,
        )


        webhook_delivery_response.additional_properties = d
        return webhook_delivery_response

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
