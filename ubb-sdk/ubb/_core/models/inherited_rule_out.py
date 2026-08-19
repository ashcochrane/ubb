from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.inherited_pricing_rule import InheritedPricingRule





T = TypeVar("T", bound="InheritedRuleOut")



@_attrs_define
class InheritedRuleOut:
    """ What this customer is charged for a quantity where they have no override.

    **AN ENVELOPE, BECAUSE "NOTHING IS INHERITED" IS AN ANSWER.** A quantity no
    book in play prices falls to the tenant's markup rung, and a client creating
    an override there is starting from nothing rather than from a rule — a
    perfectly ordinary state, and one a `404` would report as *"no such
    customer"*. So the rule is nullable and the status stays `200`.

        Attributes:
            rule (InheritedPricingRule | None | Unset):
     """

    rule: InheritedPricingRule | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.inherited_pricing_rule import InheritedPricingRule
        rule: dict[str, Any] | None | Unset
        if isinstance(self.rule, Unset):
            rule = UNSET
        elif isinstance(self.rule, InheritedPricingRule):
            rule = self.rule.to_dict()
        else:
            rule = self.rule


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if rule is not UNSET:
            field_dict["rule"] = rule

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.inherited_pricing_rule import InheritedPricingRule
        d = dict(src_dict)
        def _parse_rule(data: object) -> InheritedPricingRule | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                rule_type_0 = InheritedPricingRule.from_dict(data)



                return rule_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(InheritedPricingRule | None | Unset, data)

        rule = _parse_rule(d.pop("rule", UNSET))


        inherited_rule_out = cls(
            rule=rule,
        )


        inherited_rule_out.additional_properties = d
        return inherited_rule_out

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
