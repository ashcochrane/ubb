from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pricing_receipt_provenance_markup_rung import PricingReceiptProvenanceMarkupRung






T = TypeVar("T", bound="PricingReceiptProvenanceMarkup")



@_attrs_define
class PricingReceiptProvenanceMarkup:
    """ The rung the margin came from and the record that declared it.

        Attributes:
            record_id (str):
            rung (PricingReceiptProvenanceMarkupRung):
     """

    record_id: str
    rung: PricingReceiptProvenanceMarkupRung
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        record_id = self.record_id

        rung = self.rung.value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "record_id": record_id,
            "rung": rung,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        record_id = d.pop("record_id")

        rung = PricingReceiptProvenanceMarkupRung(d.pop("rung"))




        pricing_receipt_provenance_markup = cls(
            record_id=record_id,
            rung=rung,
        )


        pricing_receipt_provenance_markup.additional_properties = d
        return pricing_receipt_provenance_markup

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
