from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.usage_analytics_response_breakdowns import UsageAnalyticsResponseBreakdowns
  from ..models.usage_analytics_response_by_customer_item import UsageAnalyticsResponseByCustomerItem
  from ..models.usage_analytics_response_by_event_type_item import UsageAnalyticsResponseByEventTypeItem
  from ..models.usage_analytics_response_by_provider_item import UsageAnalyticsResponseByProviderItem
  from ..models.usage_analytics_response_by_tag_item import UsageAnalyticsResponseByTagItem
  from ..models.usage_analytics_response_by_task_type_item import UsageAnalyticsResponseByTaskTypeItem





T = TypeVar("T", bound="UsageAnalyticsResponse")



@_attrs_define
class UsageAnalyticsResponse:
    """ 
        Attributes:
            by_customer (list[UsageAnalyticsResponseByCustomerItem]):
            by_event_type (list[UsageAnalyticsResponseByEventTypeItem]):
            by_provider (list[UsageAnalyticsResponseByProviderItem]):
            by_tag (list[UsageAnalyticsResponseByTagItem]):
            by_task_type (list[UsageAnalyticsResponseByTaskTypeItem]):
            total_billed_cost_micros (int):
            total_events (int):
            total_provider_cost_micros (int):
            usage_markup_margin_micros (int):
            breakdowns (UsageAnalyticsResponseBreakdowns | Unset):
     """

    by_customer: list[UsageAnalyticsResponseByCustomerItem]
    by_event_type: list[UsageAnalyticsResponseByEventTypeItem]
    by_provider: list[UsageAnalyticsResponseByProviderItem]
    by_tag: list[UsageAnalyticsResponseByTagItem]
    by_task_type: list[UsageAnalyticsResponseByTaskTypeItem]
    total_billed_cost_micros: int
    total_events: int
    total_provider_cost_micros: int
    usage_markup_margin_micros: int
    breakdowns: UsageAnalyticsResponseBreakdowns | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_analytics_response_breakdowns import UsageAnalyticsResponseBreakdowns
        from ..models.usage_analytics_response_by_customer_item import UsageAnalyticsResponseByCustomerItem
        from ..models.usage_analytics_response_by_event_type_item import UsageAnalyticsResponseByEventTypeItem
        from ..models.usage_analytics_response_by_provider_item import UsageAnalyticsResponseByProviderItem
        from ..models.usage_analytics_response_by_tag_item import UsageAnalyticsResponseByTagItem
        from ..models.usage_analytics_response_by_task_type_item import UsageAnalyticsResponseByTaskTypeItem
        by_customer = []
        for by_customer_item_data in self.by_customer:
            by_customer_item = by_customer_item_data.to_dict()
            by_customer.append(by_customer_item)



        by_event_type = []
        for by_event_type_item_data in self.by_event_type:
            by_event_type_item = by_event_type_item_data.to_dict()
            by_event_type.append(by_event_type_item)



        by_provider = []
        for by_provider_item_data in self.by_provider:
            by_provider_item = by_provider_item_data.to_dict()
            by_provider.append(by_provider_item)



        by_tag = []
        for by_tag_item_data in self.by_tag:
            by_tag_item = by_tag_item_data.to_dict()
            by_tag.append(by_tag_item)



        by_task_type = []
        for by_task_type_item_data in self.by_task_type:
            by_task_type_item = by_task_type_item_data.to_dict()
            by_task_type.append(by_task_type_item)



        total_billed_cost_micros = self.total_billed_cost_micros

        total_events = self.total_events

        total_provider_cost_micros = self.total_provider_cost_micros

        usage_markup_margin_micros = self.usage_markup_margin_micros

        breakdowns: dict[str, Any] | Unset = UNSET
        if not isinstance(self.breakdowns, Unset):
            breakdowns = self.breakdowns.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "by_customer": by_customer,
            "by_event_type": by_event_type,
            "by_provider": by_provider,
            "by_tag": by_tag,
            "by_task_type": by_task_type,
            "total_billed_cost_micros": total_billed_cost_micros,
            "total_events": total_events,
            "total_provider_cost_micros": total_provider_cost_micros,
            "usage_markup_margin_micros": usage_markup_margin_micros,
        })
        if breakdowns is not UNSET:
            field_dict["breakdowns"] = breakdowns

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_analytics_response_breakdowns import UsageAnalyticsResponseBreakdowns
        from ..models.usage_analytics_response_by_customer_item import UsageAnalyticsResponseByCustomerItem
        from ..models.usage_analytics_response_by_event_type_item import UsageAnalyticsResponseByEventTypeItem
        from ..models.usage_analytics_response_by_provider_item import UsageAnalyticsResponseByProviderItem
        from ..models.usage_analytics_response_by_tag_item import UsageAnalyticsResponseByTagItem
        from ..models.usage_analytics_response_by_task_type_item import UsageAnalyticsResponseByTaskTypeItem
        d = dict(src_dict)
        by_customer = []
        _by_customer = d.pop("by_customer")
        for by_customer_item_data in (_by_customer):
            by_customer_item = UsageAnalyticsResponseByCustomerItem.from_dict(by_customer_item_data)



            by_customer.append(by_customer_item)


        by_event_type = []
        _by_event_type = d.pop("by_event_type")
        for by_event_type_item_data in (_by_event_type):
            by_event_type_item = UsageAnalyticsResponseByEventTypeItem.from_dict(by_event_type_item_data)



            by_event_type.append(by_event_type_item)


        by_provider = []
        _by_provider = d.pop("by_provider")
        for by_provider_item_data in (_by_provider):
            by_provider_item = UsageAnalyticsResponseByProviderItem.from_dict(by_provider_item_data)



            by_provider.append(by_provider_item)


        by_tag = []
        _by_tag = d.pop("by_tag")
        for by_tag_item_data in (_by_tag):
            by_tag_item = UsageAnalyticsResponseByTagItem.from_dict(by_tag_item_data)



            by_tag.append(by_tag_item)


        by_task_type = []
        _by_task_type = d.pop("by_task_type")
        for by_task_type_item_data in (_by_task_type):
            by_task_type_item = UsageAnalyticsResponseByTaskTypeItem.from_dict(by_task_type_item_data)



            by_task_type.append(by_task_type_item)


        total_billed_cost_micros = d.pop("total_billed_cost_micros")

        total_events = d.pop("total_events")

        total_provider_cost_micros = d.pop("total_provider_cost_micros")

        usage_markup_margin_micros = d.pop("usage_markup_margin_micros")

        _breakdowns = d.pop("breakdowns", UNSET)
        breakdowns: UsageAnalyticsResponseBreakdowns | Unset
        if isinstance(_breakdowns,  Unset):
            breakdowns = UNSET
        else:
            breakdowns = UsageAnalyticsResponseBreakdowns.from_dict(_breakdowns)




        usage_analytics_response = cls(
            by_customer=by_customer,
            by_event_type=by_event_type,
            by_provider=by_provider,
            by_tag=by_tag,
            by_task_type=by_task_type,
            total_billed_cost_micros=total_billed_cost_micros,
            total_events=total_events,
            total_provider_cost_micros=total_provider_cost_micros,
            usage_markup_margin_micros=usage_markup_margin_micros,
            breakdowns=breakdowns,
        )


        usage_analytics_response.additional_properties = d
        return usage_analytics_response

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
