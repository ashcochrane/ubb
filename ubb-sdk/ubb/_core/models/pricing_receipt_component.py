from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pricing_receipt_component_rate_structure import PricingReceiptComponentRateStructure






T = TypeVar("T", bound="PricingReceiptComponent")



@_attrs_define
class PricingReceiptComponent:
    """ One priced quantity, with the terms that priced it, BY VALUE — the
    measured detail behind it expires and this record does not
    (`receipts.REQUIRED_COMPONENT_KEYS`, a minimum).

        Attributes:
            fixed_micros (int):
            measurement_key (str):
            micros (int):
            rate_per_unit_micros (int):
            rate_structure (PricingReceiptComponentRateStructure):
            unit_quantity (int):
            units (str):
     """

    fixed_micros: int
    measurement_key: str
    micros: int
    rate_per_unit_micros: int
    rate_structure: PricingReceiptComponentRateStructure
    unit_quantity: int
    units: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        fixed_micros = self.fixed_micros

        measurement_key = self.measurement_key

        micros = self.micros

        rate_per_unit_micros = self.rate_per_unit_micros

        rate_structure = self.rate_structure.value

        unit_quantity = self.unit_quantity

        units = self.units


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "fixed_micros": fixed_micros,
            "measurement_key": measurement_key,
            "micros": micros,
            "rate_per_unit_micros": rate_per_unit_micros,
            "rate_structure": rate_structure,
            "unit_quantity": unit_quantity,
            "units": units,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fixed_micros = d.pop("fixed_micros")

        measurement_key = d.pop("measurement_key")

        micros = d.pop("micros")

        rate_per_unit_micros = d.pop("rate_per_unit_micros")

        rate_structure = PricingReceiptComponentRateStructure(d.pop("rate_structure"))




        unit_quantity = d.pop("unit_quantity")

        units = d.pop("units")

        pricing_receipt_component = cls(
            fixed_micros=fixed_micros,
            measurement_key=measurement_key,
            micros=micros,
            rate_per_unit_micros=rate_per_unit_micros,
            rate_structure=rate_structure,
            unit_quantity=unit_quantity,
            units=units,
        )


        pricing_receipt_component.additional_properties = d
        return pricing_receipt_component

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
