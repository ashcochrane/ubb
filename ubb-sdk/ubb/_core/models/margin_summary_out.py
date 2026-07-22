from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.period_window import PeriodWindow





T = TypeVar("T", bound="MarginSummaryOut")



@_attrs_define
class MarginSummaryOut:
    """ 
        Attributes:
            customer_count (int):
            gross_margin_micros (int):
            margin_percentage (float):
            period (PeriodWindow):
            provider_cost_micros (int):
            subscription_revenue_micros (int):
            total_revenue_micros (int):
            usage_billed_micros (int):
            usage_revenue_micros (int):
     """

    customer_count: int
    gross_margin_micros: int
    margin_percentage: float
    period: PeriodWindow
    provider_cost_micros: int
    subscription_revenue_micros: int
    total_revenue_micros: int
    usage_billed_micros: int
    usage_revenue_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.period_window import PeriodWindow
        customer_count = self.customer_count

        gross_margin_micros = self.gross_margin_micros

        margin_percentage = self.margin_percentage

        period = self.period.to_dict()

        provider_cost_micros = self.provider_cost_micros

        subscription_revenue_micros = self.subscription_revenue_micros

        total_revenue_micros = self.total_revenue_micros

        usage_billed_micros = self.usage_billed_micros

        usage_revenue_micros = self.usage_revenue_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_count": customer_count,
            "gross_margin_micros": gross_margin_micros,
            "margin_percentage": margin_percentage,
            "period": period,
            "provider_cost_micros": provider_cost_micros,
            "subscription_revenue_micros": subscription_revenue_micros,
            "total_revenue_micros": total_revenue_micros,
            "usage_billed_micros": usage_billed_micros,
            "usage_revenue_micros": usage_revenue_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.period_window import PeriodWindow
        d = dict(src_dict)
        customer_count = d.pop("customer_count")

        gross_margin_micros = d.pop("gross_margin_micros")

        margin_percentage = d.pop("margin_percentage")

        period = PeriodWindow.from_dict(d.pop("period"))




        provider_cost_micros = d.pop("provider_cost_micros")

        subscription_revenue_micros = d.pop("subscription_revenue_micros")

        total_revenue_micros = d.pop("total_revenue_micros")

        usage_billed_micros = d.pop("usage_billed_micros")

        usage_revenue_micros = d.pop("usage_revenue_micros")

        margin_summary_out = cls(
            customer_count=customer_count,
            gross_margin_micros=gross_margin_micros,
            margin_percentage=margin_percentage,
            period=period,
            provider_cost_micros=provider_cost_micros,
            subscription_revenue_micros=subscription_revenue_micros,
            total_revenue_micros=total_revenue_micros,
            usage_billed_micros=usage_billed_micros,
            usage_revenue_micros=usage_revenue_micros,
        )


        margin_summary_out.additional_properties = d
        return margin_summary_out

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
