from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="TaskAnalyticsRow")



@_attrs_define
class TaskAnalyticsRow:
    """ 
        Attributes:
            avg_provider_cost_micros (int):
            limit_hit_count (int):
            p95_provider_cost_micros (int):
            run_count (int):
            task_type (str):
            total_billed_cost_micros (int):
            total_provider_cost_micros (int):
            unpriced_event_count (int):
            unresolved_event_count (int):
     """

    avg_provider_cost_micros: int
    limit_hit_count: int
    p95_provider_cost_micros: int
    run_count: int
    task_type: str
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    unpriced_event_count: int
    unresolved_event_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        avg_provider_cost_micros = self.avg_provider_cost_micros

        limit_hit_count = self.limit_hit_count

        p95_provider_cost_micros = self.p95_provider_cost_micros

        run_count = self.run_count

        task_type = self.task_type

        total_billed_cost_micros = self.total_billed_cost_micros

        total_provider_cost_micros = self.total_provider_cost_micros

        unpriced_event_count = self.unpriced_event_count

        unresolved_event_count = self.unresolved_event_count


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "avg_provider_cost_micros": avg_provider_cost_micros,
            "limit_hit_count": limit_hit_count,
            "p95_provider_cost_micros": p95_provider_cost_micros,
            "run_count": run_count,
            "task_type": task_type,
            "total_billed_cost_micros": total_billed_cost_micros,
            "total_provider_cost_micros": total_provider_cost_micros,
            "unpriced_event_count": unpriced_event_count,
            "unresolved_event_count": unresolved_event_count,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        avg_provider_cost_micros = d.pop("avg_provider_cost_micros")

        limit_hit_count = d.pop("limit_hit_count")

        p95_provider_cost_micros = d.pop("p95_provider_cost_micros")

        run_count = d.pop("run_count")

        task_type = d.pop("task_type")

        total_billed_cost_micros = d.pop("total_billed_cost_micros")

        total_provider_cost_micros = d.pop("total_provider_cost_micros")

        unpriced_event_count = d.pop("unpriced_event_count")

        unresolved_event_count = d.pop("unresolved_event_count")

        task_analytics_row = cls(
            avg_provider_cost_micros=avg_provider_cost_micros,
            limit_hit_count=limit_hit_count,
            p95_provider_cost_micros=p95_provider_cost_micros,
            run_count=run_count,
            task_type=task_type,
            total_billed_cost_micros=total_billed_cost_micros,
            total_provider_cost_micros=total_provider_cost_micros,
            unpriced_event_count=unpriced_event_count,
            unresolved_event_count=unresolved_event_count,
        )


        task_analytics_row.additional_properties = d
        return task_analytics_row

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
