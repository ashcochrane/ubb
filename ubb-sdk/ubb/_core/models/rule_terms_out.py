from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.rule_terms_out_pricing_method_type_0 import RuleTermsOutPricingMethodType0
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RuleTermsOut")



@_attrs_define
class RuleTermsOut:
    """ What a rule charges and how it derives it — everything a change may move.

    ⚠ The arithmetic shape is deliberately absent, for the reason `BookChangeIn`
    gives: a publish cannot move it. A reader comparing a `before` with an
    `after` therefore sees all three terms and is not told which one the rule
    actually charges on — `GET .../rates` answers that, and this row is a
    statement about what a change does rather than a restatement of the rule.

    **THE METHOD IS HERE BECAUSE A CHANGE CAN MOVE IT (#361).** A customer
    override replaces a whole rule including its method, so the diff a tenant
    reads before committing to it has to show the method changing — otherwise
    the one part of a negotiated deal that changes its shape is the one part
    that is invisible until after it lands.

        Attributes:
            fixed_micros (int):
            rate_per_unit_micros (int):
            unit_quantity (int):
            pricing_method (None | RuleTermsOutPricingMethodType0 | Unset):
     """

    fixed_micros: int
    rate_per_unit_micros: int
    unit_quantity: int
    pricing_method: None | RuleTermsOutPricingMethodType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        fixed_micros = self.fixed_micros

        rate_per_unit_micros = self.rate_per_unit_micros

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
