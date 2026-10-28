from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="PricingReceiptMarkupTerms")



@_attrs_define
class PricingReceiptMarkupTerms:
    """ What a margin over cost was, by value: the percentage and the basis it
    was taken over. Exactly these two (`receipts.REQUIRED_MARKUP_KEYS`).

        Attributes:
            basis_micros (int):
            micro_percent (int):
     """

    basis_micros: int
    micro_percent: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        basis_micros = self.basis_micros

        micro_percent = self.micro_percent


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "basis_micros": basis_micros,
            "micro_percent": micro_percent,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        basis_micros = d.pop("basis_micros")

        micro_percent = d.pop("micro_percent")

        pricing_receipt_markup_terms = cls(
            basis_micros=basis_micros,
            micro_percent=micro_percent,
        )


        pricing_receipt_markup_terms.additional_properties = d
        return pricing_receipt_markup_terms

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
