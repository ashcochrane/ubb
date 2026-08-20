from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.inherited_pricing_rule_pricing_method_type_0 import InheritedPricingRulePricingMethodType0
from ..models.inherited_pricing_rule_rate_structure import InheritedPricingRuleRateStructure
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.inherited_pricing_rule_grouping_fields import InheritedPricingRuleGroupingFields





T = TypeVar("T", bound="InheritedPricingRule")



@_attrs_define
class InheritedPricingRule:
    """ One rule, as a client would start an override from it.

    Everything an override body has to state, in the shape it has to state it —
    so *create from the inherited rule* is a copy rather than a translation. The
    rule's own id and the book it came from ride along so a reader can say where
    the starting point came from.

        Attributes:
            book_id (str):
            currency (str):
            event_type (str):
            fixed_micros (int):
            measurement_key (str):
            provider (str):
            rate_per_unit_micros (int):
            rate_structure (InheritedPricingRuleRateStructure):
            rule_id (str):
            subtask_type (str):
            task_type (str):
            unit_quantity (int):
            grouping_fields (InheritedPricingRuleGroupingFields | Unset):
            pricing_method (InheritedPricingRulePricingMethodType0 | None | Unset):
     """

    book_id: str
    currency: str
    event_type: str
    fixed_micros: int
    measurement_key: str
    provider: str
    rate_per_unit_micros: int
    rate_structure: InheritedPricingRuleRateStructure
    rule_id: str
    subtask_type: str
    task_type: str
    unit_quantity: int
    grouping_fields: InheritedPricingRuleGroupingFields | Unset = UNSET
    pricing_method: InheritedPricingRulePricingMethodType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.inherited_pricing_rule_grouping_fields import InheritedPricingRuleGroupingFields
        book_id = self.book_id

        currency = self.currency

        event_type = self.event_type

        fixed_micros = self.fixed_micros

        measurement_key = self.measurement_key

        provider = self.provider

        rate_per_unit_micros = self.rate_per_unit_micros

        rate_structure = self.rate_structure.value

        rule_id = self.rule_id

        subtask_type = self.subtask_type

        task_type = self.task_type

        unit_quantity = self.unit_quantity

        grouping_fields: dict[str, Any] | Unset = UNSET
        if not isinstance(self.grouping_fields, Unset):
            grouping_fields = self.grouping_fields.to_dict()

        pricing_method: None | str | Unset
        if isinstance(self.pricing_method, Unset):
            pricing_method = UNSET
        elif isinstance(self.pricing_method, InheritedPricingRulePricingMethodType0):
            pricing_method = self.pricing_method.value
        else:
            pricing_method = self.pricing_method


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "book_id": book_id,
            "currency": currency,
            "event_type": event_type,
            "fixed_micros": fixed_micros,
            "measurement_key": measurement_key,
            "provider": provider,
            "rate_per_unit_micros": rate_per_unit_micros,
            "rate_structure": rate_structure,
            "rule_id": rule_id,
            "subtask_type": subtask_type,
            "task_type": task_type,
            "unit_quantity": unit_quantity,
        })
        if grouping_fields is not UNSET:
            field_dict["grouping_fields"] = grouping_fields
        if pricing_method is not UNSET:
            field_dict["pricing_method"] = pricing_method

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.inherited_pricing_rule_grouping_fields import InheritedPricingRuleGroupingFields
        d = dict(src_dict)
        book_id = d.pop("book_id")

        currency = d.pop("currency")

        event_type = d.pop("event_type")

        fixed_micros = d.pop("fixed_micros")

        measurement_key = d.pop("measurement_key")

        provider = d.pop("provider")

        rate_per_unit_micros = d.pop("rate_per_unit_micros")

        rate_structure = InheritedPricingRuleRateStructure(d.pop("rate_structure"))




        rule_id = d.pop("rule_id")

        subtask_type = d.pop("subtask_type")

        task_type = d.pop("task_type")

        unit_quantity = d.pop("unit_quantity")

        _grouping_fields = d.pop("grouping_fields", UNSET)
        grouping_fields: InheritedPricingRuleGroupingFields | Unset
        if isinstance(_grouping_fields,  Unset):
            grouping_fields = UNSET
        else:
            grouping_fields = InheritedPricingRuleGroupingFields.from_dict(_grouping_fields)




        def _parse_pricing_method(data: object) -> InheritedPricingRulePricingMethodType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_method_type_0 = InheritedPricingRulePricingMethodType0(data)



                return pricing_method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(InheritedPricingRulePricingMethodType0 | None | Unset, data)

        pricing_method = _parse_pricing_method(d.pop("pricing_method", UNSET))


        inherited_pricing_rule = cls(
            book_id=book_id,
            currency=currency,
            event_type=event_type,
            fixed_micros=fixed_micros,
            measurement_key=measurement_key,
            provider=provider,
            rate_per_unit_micros=rate_per_unit_micros,
            rate_structure=rate_structure,
            rule_id=rule_id,
            subtask_type=subtask_type,
            task_type=task_type,
            unit_quantity=unit_quantity,
            grouping_fields=grouping_fields,
            pricing_method=pricing_method,
        )


        inherited_pricing_rule.additional_properties = d
        return inherited_pricing_rule

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
