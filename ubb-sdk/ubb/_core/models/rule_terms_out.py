from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="RuleTermsOut")



@_attrs_define
class RuleTermsOut:
    """ What a rule charges — the three columns a change may move.

    ⚠ The arithmetic shape is deliberately absent, for the reason `BookChangeIn`
    gives: a publish cannot move it. A reader comparing a `before` with an
    `after` therefore sees all three terms and is not told which one the rule
    actually charges on — `GET .../rates` answers that, and this row is a
    statement about what a change does rather than a restatement of the rule.

        Attributes:
            fixed_micros (int):
            rate_per_unit_micros (int):
            unit_quantity (int):
     """

    fixed_micros: int
    rate_per_unit_micros: int
    unit_quantity: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        fixed_micros = self.fixed_micros

        rate_per_unit_micros = self.rate_per_unit_micros

        unit_quantity = self.unit_quantity


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "fixed_micros": fixed_micros,
            "rate_per_unit_micros": rate_per_unit_micros,
            "unit_quantity": unit_quantity,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fixed_micros = d.pop("fixed_micros")

        rate_per_unit_micros = d.pop("rate_per_unit_micros")

        unit_quantity = d.pop("unit_quantity")

        rule_terms_out = cls(
            fixed_micros=fixed_micros,
            rate_per_unit_micros=rate_per_unit_micros,
            unit_quantity=unit_quantity,
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
