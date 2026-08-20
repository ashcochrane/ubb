from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.rule_terms_out_pricing_method_type_0 import RuleTermsOutPricingMethodType0
from ..models.rule_terms_out_rate_structure import RuleTermsOutRateStructure
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RuleTermsOut")



@_attrs_define
class RuleTermsOut:
    """ What a rule charges and how it derives it — everything a change may move.

    **THE METHOD IS HERE BECAUSE A CHANGE CAN MOVE IT (#361).** A customer
    override replaces a whole rule including its method, so the diff a tenant
    reads before committing to it has to show the method changing — otherwise
    the one part of a negotiated deal that changes its shape is the one part
    that is invisible until after it lands.

    **AND SO IS THE ARITHMETIC SHAPE, FOR THE SAME REASON, ONE TICKET LATER
    (#366).** It was absent while a publish could not move it; a diff showing
    three money terms and not which one the rule actually charges on told a
    reader almost nothing — a rule going from a per-unit charge to a fixed
    component reads as *"nothing moved"* if only the terms are shown, because
    both terms are already there and only the shape decides which is spent.

        Attributes:
            fixed_micros (int):
            rate_per_unit_micros (int):
            rate_structure (RuleTermsOutRateStructure):
            unit_quantity (int):
            pricing_method (None | RuleTermsOutPricingMethodType0 | Unset):
     """

    fixed_micros: int
    rate_per_unit_micros: int
    rate_structure: RuleTermsOutRateStructure
    unit_quantity: int
    pricing_method: None | RuleTermsOutPricingMethodType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        fixed_micros = self.fixed_micros

        rate_per_unit_micros = self.rate_per_unit_micros

        rate_structure = self.rate_structure.value

        unit_quantity = self.unit_quantity

        pricing_method: None | str | Unset
        if isinstance(self.pricing_method, Unset):
            pricing_method = UNSET
        elif isinstance(self.pricing_method, RuleTermsOutPricingMethodType0):
            pricing_method = self.pricing_method.value
        else:
            pricing_method = self.pricing_method


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "fixed_micros": fixed_micros,
            "rate_per_unit_micros": rate_per_unit_micros,
            "rate_structure": rate_structure,
            "unit_quantity": unit_quantity,
        })
        if pricing_method is not UNSET:
            field_dict["pricing_method"] = pricing_method

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fixed_micros = d.pop("fixed_micros")

        rate_per_unit_micros = d.pop("rate_per_unit_micros")

        rate_structure = RuleTermsOutRateStructure(d.pop("rate_structure"))




        unit_quantity = d.pop("unit_quantity")

        def _parse_pricing_method(data: object) -> None | RuleTermsOutPricingMethodType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_method_type_0 = RuleTermsOutPricingMethodType0(data)



                return pricing_method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuleTermsOutPricingMethodType0 | Unset, data)

        pricing_method = _parse_pricing_method(d.pop("pricing_method", UNSET))


        rule_terms_out = cls(
            fixed_micros=fixed_micros,
            rate_per_unit_micros=rate_per_unit_micros,
            rate_structure=rate_structure,
            unit_quantity=unit_quantity,
            pricing_method=pricing_method,
        )


        rule_terms_out.additional_properties = d
        return rule_terms_out

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
