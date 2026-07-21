from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="TenantBillingPeriodOut")



@_attrs_define
class TenantBillingPeriodOut:
    """ 
        Attributes:
            event_count (int):
            id (str):
            period_end (str):
            period_start (str):
            platform_fee_micros (int):
            status (str):
            total_usage_cost_micros (int):
     """

    event_count: int
    id: str
    period_end: str
    period_start: str
    platform_fee_micros: int
    status: str
    total_usage_cost_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        event_count = self.event_count

        id = self.id

        period_end = self.period_end

        period_start = self.period_start

        platform_fee_micros = self.platform_fee_micros

        status = self.status

        total_usage_cost_micros = self.total_usage_cost_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event_count": event_count,
            "id": id,
            "period_end": period_end,
            "period_start": period_start,
            "platform_fee_micros": platform_fee_micros,
            "status": status,
            "total_usage_cost_micros": total_usage_cost_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        event_count = d.pop("event_count")

        id = d.pop("id")

        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        platform_fee_micros = d.pop("platform_fee_micros")

        status = d.pop("status")

        total_usage_cost_micros = d.pop("total_usage_cost_micros")

        tenant_billing_period_out = cls(
            event_count=event_count,
            id=id,
            period_end=period_end,
            period_start=period_start,
            platform_fee_micros=platform_fee_micros,
            status=status,
            total_usage_cost_micros=total_usage_cost_micros,
        )


        tenant_billing_period_out.additional_properties = d
        return tenant_billing_period_out

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
