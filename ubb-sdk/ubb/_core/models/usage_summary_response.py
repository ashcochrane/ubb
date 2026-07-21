from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.usage_metric_out import UsageMetricOut





T = TypeVar("T", bound="UsageSummaryResponse")



@_attrs_define
class UsageSummaryResponse:
    """ 
        Attributes:
            currency (str):
            metrics (list[UsageMetricOut]):
            period_end (str):
            period_start (str):
            total_billed_micros (int):
            total_units (int):
     """

    currency: str
    metrics: list[UsageMetricOut]
    period_end: str
    period_start: str
    total_billed_micros: int
    total_units: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_metric_out import UsageMetricOut
        currency = self.currency

        metrics = []
        for metrics_item_data in self.metrics:
            metrics_item = metrics_item_data.to_dict()
            metrics.append(metrics_item)



        period_end = self.period_end

        period_start = self.period_start

        total_billed_micros = self.total_billed_micros

        total_units = self.total_units


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "currency": currency,
            "metrics": metrics,
            "period_end": period_end,
            "period_start": period_start,
            "total_billed_micros": total_billed_micros,
            "total_units": total_units,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_metric_out import UsageMetricOut
        d = dict(src_dict)
        currency = d.pop("currency")

        metrics = []
        _metrics = d.pop("metrics")
        for metrics_item_data in (_metrics):
            metrics_item = UsageMetricOut.from_dict(metrics_item_data)



            metrics.append(metrics_item)


        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        total_billed_micros = d.pop("total_billed_micros")

        total_units = d.pop("total_units")

        usage_summary_response = cls(
            currency=currency,
            metrics=metrics,
            period_end=period_end,
            period_start=period_start,
            total_billed_micros=total_billed_micros,
            total_units=total_units,
        )


        usage_summary_response.additional_properties = d
        return usage_summary_response

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
