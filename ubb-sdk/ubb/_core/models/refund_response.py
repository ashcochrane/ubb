from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="RefundResponse")



@_attrs_define
class RefundResponse:
    """ 
        Attributes:
            balance_micros (int):
            refund_id (str):
     """

    balance_micros: int
    refund_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        balance_micros = self.balance_micros

        refund_id = self.refund_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "balance_micros": balance_micros,
            "refund_id": refund_id,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        balance_micros = d.pop("balance_micros")

        refund_id = d.pop("refund_id")

        refund_response = cls(
            balance_micros=balance_micros,
            refund_id=refund_id,
        )


        refund_response.additional_properties = d
        return refund_response

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
