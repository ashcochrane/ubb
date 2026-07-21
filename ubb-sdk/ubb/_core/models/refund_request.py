from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from uuid import UUID






T = TypeVar("T", bound="RefundRequest")



@_attrs_define
class RefundRequest:
    """ 
        Attributes:
            idempotency_key (str):
            usage_event_id (UUID):
            reason (str | Unset):  Default: ''.
     """

    idempotency_key: str
    usage_event_id: UUID
    reason: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        idempotency_key = self.idempotency_key

        usage_event_id = str(self.usage_event_id)

        reason = self.reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "idempotency_key": idempotency_key,
            "usage_event_id": usage_event_id,
        })
        if reason is not UNSET:
            field_dict["reason"] = reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        idempotency_key = d.pop("idempotency_key")

        usage_event_id = UUID(d.pop("usage_event_id"))




        reason = d.pop("reason", UNSET)

        refund_request = cls(
            idempotency_key=idempotency_key,
            usage_event_id=usage_event_id,
            reason=reason,
        )


        refund_request.additional_properties = d
        return refund_request

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
