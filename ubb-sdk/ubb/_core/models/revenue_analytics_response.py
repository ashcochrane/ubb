from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.revenue_analytics_response_daily_item import RevenueAnalyticsResponseDailyItem





T = TypeVar("T", bound="RevenueAnalyticsResponse")



@_attrs_define
class RevenueAnalyticsResponse:
    """ 
        Attributes:
            daily (list[RevenueAnalyticsResponseDailyItem]):
            total_billed_cost_micros (int):
            total_markup_micros (int):
            total_provider_cost_micros (int):
     """

    daily: list[RevenueAnalyticsResponseDailyItem]
    total_billed_cost_micros: int
    total_markup_micros: int
    total_provider_cost_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.revenue_analytics_response_daily_item import RevenueAnalyticsResponseDailyItem
        daily = []
        for daily_item_data in self.daily:
            daily_item = daily_item_data.to_dict()
            daily.append(daily_item)



        total_billed_cost_micros = self.total_billed_cost_micros

        total_markup_micros = self.total_markup_micros

        total_provider_cost_micros = self.total_provider_cost_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "daily": daily,
            "total_billed_cost_micros": total_billed_cost_micros,
            "total_markup_micros": total_markup_micros,
            "total_provider_cost_micros": total_provider_cost_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.revenue_analytics_response_daily_item import RevenueAnalyticsResponseDailyItem
        d = dict(src_dict)
        daily = []
        _daily = d.pop("daily")
        for daily_item_data in (_daily):
            daily_item = RevenueAnalyticsResponseDailyItem.from_dict(daily_item_data)



            daily.append(daily_item)


        total_billed_cost_micros = d.pop("total_billed_cost_micros")

        total_markup_micros = d.pop("total_markup_micros")

        total_provider_cost_micros = d.pop("total_provider_cost_micros")

        revenue_analytics_response = cls(
            daily=daily,
            total_billed_cost_micros=total_billed_cost_micros,
            total_markup_micros=total_markup_micros,
            total_provider_cost_micros=total_provider_cost_micros,
        )


        revenue_analytics_response.additional_properties = d
        return revenue_analytics_response

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
