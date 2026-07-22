from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="UnprofitableCustomerRow")



@_attrs_define
class UnprofitableCustomerRow:
    """ 
        Attributes:
            customer_id (str):
            external_id (str):
            gross_margin_micros (int):
            margin_percentage (float):
     """

    customer_id: str
    external_id: str
    gross_margin_micros: int
    margin_percentage: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        customer_id = self.customer_id

        external_id = self.external_id

        gross_margin_micros = self.gross_margin_micros

        margin_percentage = self.margin_percentage


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_id": customer_id,
            "external_id": external_id,
            "gross_margin_micros": gross_margin_micros,
            "margin_percentage": margin_percentage,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        customer_id = d.pop("customer_id")

        external_id = d.pop("external_id")

        gross_margin_micros = d.pop("gross_margin_micros")

        margin_percentage = d.pop("margin_percentage")

        unprofitable_customer_row = cls(
            customer_id=customer_id,
            external_id=external_id,
            gross_margin_micros=gross_margin_micros,
            margin_percentage=margin_percentage,
        )


        unprofitable_customer_row.additional_properties = d
        return unprofitable_customer_row

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
