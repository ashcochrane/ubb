from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.dimension_margin_row import DimensionMarginRow
  from ..models.period_window import PeriodWindow





T = TypeVar("T", bound="MarginByDimensionOut")



@_attrs_define
class MarginByDimensionOut:
    """ 
        Attributes:
            period (PeriodWindow):
            rows (list[DimensionMarginRow]):
     """

    period: PeriodWindow
    rows: list[DimensionMarginRow]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.dimension_margin_row import DimensionMarginRow
        from ..models.period_window import PeriodWindow
        period = self.period.to_dict()

        rows = []
        for rows_item_data in self.rows:
            rows_item = rows_item_data.to_dict()
            rows.append(rows_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "period": period,
            "rows": rows,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dimension_margin_row import DimensionMarginRow
        from ..models.period_window import PeriodWindow
        d = dict(src_dict)
        period = PeriodWindow.from_dict(d.pop("period"))




        rows = []
        _rows = d.pop("rows")
        for rows_item_data in (_rows):
            rows_item = DimensionMarginRow.from_dict(rows_item_data)



            rows.append(rows_item)


        margin_by_dimension_out = cls(
            period=period,
            rows=rows,
        )


        margin_by_dimension_out.additional_properties = d
        return margin_by_dimension_out

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
