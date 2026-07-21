from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="WithdrawRequest")



@_attrs_define
class WithdrawRequest:
    """ 
        Attributes:
            amount_micros (int):
            idempotency_key (str):
            description (str | Unset):  Default: ''.
     """

    amount_micros: int
    idempotency_key: str
    description: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        idempotency_key = self.idempotency_key

        description = self.description


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "idempotency_key": idempotency_key,
        })
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_micros = d.pop("amount_micros")

        idempotency_key = d.pop("idempotency_key")

        description = d.pop("description", UNSET)

        withdraw_request = cls(
            amount_micros=amount_micros,
            idempotency_key=idempotency_key,
            description=description,
        )


        withdraw_request.additional_properties = d
        return withdraw_request

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
