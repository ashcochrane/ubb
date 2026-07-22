from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="BusinessMarginTotals")



@_attrs_define
class BusinessMarginTotals:
    """ 
        Attributes:
            event_count (int):
            gross_margin_micros (int):
            provider_cost_micros (int):
            subscription_revenue_micros (int):
            total_revenue_micros (int):
            usage_revenue_micros (int):
     """

    event_count: int
    gross_margin_micros: int
    provider_cost_micros: int
    subscription_revenue_micros: int
    total_revenue_micros: int
    usage_revenue_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        event_count = self.event_count

        gross_margin_micros = self.gross_margin_micros

        provider_cost_micros = self.provider_cost_micros

        subscription_revenue_micros = self.subscription_revenue_micros

        total_revenue_micros = self.total_revenue_micros

        usage_revenue_micros = self.usage_revenue_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event_count": event_count,
            "gross_margin_micros": gross_margin_micros,
            "provider_cost_micros": provider_cost_micros,
            "subscription_revenue_micros": subscription_revenue_micros,
            "total_revenue_micros": total_revenue_micros,
            "usage_revenue_micros": usage_revenue_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        event_count = d.pop("event_count")

        gross_margin_micros = d.pop("gross_margin_micros")

        provider_cost_micros = d.pop("provider_cost_micros")

        subscription_revenue_micros = d.pop("subscription_revenue_micros")

        total_revenue_micros = d.pop("total_revenue_micros")

        usage_revenue_micros = d.pop("usage_revenue_micros")

        business_margin_totals = cls(
            event_count=event_count,
            gross_margin_micros=gross_margin_micros,
            provider_cost_micros=provider_cost_micros,
            subscription_revenue_micros=subscription_revenue_micros,
            total_revenue_micros=total_revenue_micros,
            usage_revenue_micros=usage_revenue_micros,
        )


        business_margin_totals.additional_properties = d
        return business_margin_totals

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
