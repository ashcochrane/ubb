from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.tenant_billing_period_out_status import TenantBillingPeriodOutStatus






T = TypeVar("T", bound="TenantBillingPeriodOut")



@_attrs_define
class TenantBillingPeriodOut:
    """ 
        Attributes:
            id (str):
            period_end (str):
            period_start (str):
            platform_fee_micros (int):
            recorded_events (int): Every metered usage event recorded in this period, whatever it was priced at — unpriced
                and zero-priced events included. It EXCLUDES the synthetic charge for a unit of work sold at one agreed price,
                whose money `total_billed_cost_micros` includes.
            status (TenantBillingPeriodOutStatus):
            total_billed_cost_micros (int): What the tenant's customers were billed in this period: the sum of
                `billed_cost_micros` over the period's postings, placed by when UBB received them. It INCLUDES the charge for a
                unit of work sold at one agreed price, which is revenue, so it can include money that `recorded_events` does not
                count an event for. The same name and meaning as the stop payload's sum over one unit of work. UBB's platform
                fee is a percentage of it.
     """

    id: str
    period_end: str
    period_start: str
    platform_fee_micros: int
    recorded_events: int
    status: TenantBillingPeriodOutStatus
    total_billed_cost_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        id = self.id

        period_end = self.period_end

        period_start = self.period_start

        platform_fee_micros = self.platform_fee_micros

        recorded_events = self.recorded_events

        status = self.status.value

        total_billed_cost_micros = self.total_billed_cost_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "period_end": period_end,
            "period_start": period_start,
            "platform_fee_micros": platform_fee_micros,
            "recorded_events": recorded_events,
            "status": status,
            "total_billed_cost_micros": total_billed_cost_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        platform_fee_micros = d.pop("platform_fee_micros")

        recorded_events = d.pop("recorded_events")

        status = TenantBillingPeriodOutStatus(d.pop("status"))




        total_billed_cost_micros = d.pop("total_billed_cost_micros")

        tenant_billing_period_out = cls(
            id=id,
            period_end=period_end,
            period_start=period_start,
            platform_fee_micros=platform_fee_micros,
            recorded_events=recorded_events,
            status=status,
            total_billed_cost_micros=total_billed_cost_micros,
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
