from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="PricingReceiptTotals")



@_attrs_define
class PricingReceiptTotals:
    """ The amount each section resolved; null where it is not settled.

        Attributes:
            billed_cost_micros (int | None): The customer price the pricing section resolved for this receipt's subject, in
                micros: present exactly when `pricing.status` is `known`, and null otherwise.
            provider_cost_micros (int | None): The supplier cost (COGS) the costing section resolved for this receipt's
                subject, in micros: present exactly when `costing.status` is `known`, and null otherwise.
     """

    billed_cost_micros: int | None
    provider_cost_micros: int | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        billed_cost_micros: int | None
        billed_cost_micros = self.billed_cost_micros

        provider_cost_micros: int | None
        provider_cost_micros = self.provider_cost_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billed_cost_micros": billed_cost_micros,
            "provider_cost_micros": provider_cost_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_billed_cost_micros(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        billed_cost_micros = _parse_billed_cost_micros(d.pop("billed_cost_micros"))


        def _parse_provider_cost_micros(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros"))


        pricing_receipt_totals = cls(
            billed_cost_micros=billed_cost_micros,
            provider_cost_micros=provider_cost_micros,
        )


        pricing_receipt_totals.additional_properties = d
        return pricing_receipt_totals

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
