from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="TopUpRequest")



@_attrs_define
class TopUpRequest:
    """ 
        Attributes:
            amount_micros (int):
            cancel_url (str):
            idempotency_key (str):
            success_url (str):
     """

    amount_micros: int
    cancel_url: str
    idempotency_key: str
    success_url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        cancel_url = self.cancel_url

        idempotency_key = self.idempotency_key

        success_url = self.success_url


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "cancel_url": cancel_url,
            "idempotency_key": idempotency_key,
            "success_url": success_url,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_micros = d.pop("amount_micros")

        cancel_url = d.pop("cancel_url")

        idempotency_key = d.pop("idempotency_key")

        success_url = d.pop("success_url")

        top_up_request = cls(
            amount_micros=amount_micros,
            cancel_url=cancel_url,
            idempotency_key=idempotency_key,
            success_url=success_url,
        )


        top_up_request.additional_properties = d
        return top_up_request

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
