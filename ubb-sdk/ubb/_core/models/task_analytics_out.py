from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.task_analytics_row import TaskAnalyticsRow





T = TypeVar("T", bound="TaskAnalyticsOut")



@_attrs_define
class TaskAnalyticsOut:
    """ 
        Attributes:
            group_by (str):
            rows (list[TaskAnalyticsRow]):
     """

    group_by: str
    rows: list[TaskAnalyticsRow]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.task_analytics_row import TaskAnalyticsRow
        group_by = self.group_by

        rows = []
        for rows_item_data in self.rows:
            rows_item = rows_item_data.to_dict()
            rows.append(rows_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "group_by": group_by,
            "rows": rows,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_analytics_row import TaskAnalyticsRow
        d = dict(src_dict)
        group_by = d.pop("group_by")

        rows = []
        _rows = d.pop("rows")
        for rows_item_data in (_rows):
            rows_item = TaskAnalyticsRow.from_dict(rows_item_data)



            rows.append(rows_item)


        task_analytics_out = cls(
            group_by=group_by,
            rows=rows,
        )


        task_analytics_out.additional_properties = d
        return task_analytics_out

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
