from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.economics_out_basis import EconomicsOutBasis
from typing import cast

if TYPE_CHECKING:
  from ..models.economic_row_out import EconomicRowOut
  from ..models.revenue_context_out import RevenueContextOut





T = TypeVar("T", bound="EconomicsOut")



@_attrs_define
class EconomicsOut:
    """ What this tenant's AI work cost, what it earned, and the difference.

    One definition of two numbers, over any filters, at any declared grouping
    axes, at hour, day or month. The request is echoed back — the measures are
    on each row, and the axes and the bucket are here — because a row's values
    are positional and a response a reader cannot align is a response a reader
    will align wrongly.

        Attributes:
            basis (EconomicsOutBasis):
            bucket (None | str): The time grain the rows are bucketed at — 'hour', 'day' or 'month' — or null where the
                whole period is one row.
            context (list[RevenueContextOut]):
            economic_data_available_from (str):
            group_by (list[str]):
            measurement_data_available_from (str):
            period_end (str):
            period_start (str):
            rows (list[EconomicRowOut]):
     """

    basis: EconomicsOutBasis
    bucket: None | str
    context: list[RevenueContextOut]
    economic_data_available_from: str
    group_by: list[str]
    measurement_data_available_from: str
    period_end: str
    period_start: str
    rows: list[EconomicRowOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.economic_row_out import EconomicRowOut
        from ..models.revenue_context_out import RevenueContextOut
        basis = self.basis.value

        bucket: None | str
        bucket = self.bucket

        context = []
        for context_item_data in self.context:
            context_item = context_item_data.to_dict()
            context.append(context_item)



        economic_data_available_from = self.economic_data_available_from

        group_by = self.group_by



        measurement_data_available_from = self.measurement_data_available_from

        period_end = self.period_end

        period_start = self.period_start

        rows = []
        for rows_item_data in self.rows:
            rows_item = rows_item_data.to_dict()
            rows.append(rows_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "basis": basis,
            "bucket": bucket,
            "context": context,
            "economic_data_available_from": economic_data_available_from,
            "group_by": group_by,
            "measurement_data_available_from": measurement_data_available_from,
            "period_end": period_end,
            "period_start": period_start,
            "rows": rows,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.economic_row_out import EconomicRowOut
        from ..models.revenue_context_out import RevenueContextOut
        d = dict(src_dict)
        basis = EconomicsOutBasis(d.pop("basis"))




        def _parse_bucket(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        bucket = _parse_bucket(d.pop("bucket"))


        context = []
        _context = d.pop("context")
        for context_item_data in (_context):
            context_item = RevenueContextOut.from_dict(context_item_data)



            context.append(context_item)


        economic_data_available_from = d.pop("economic_data_available_from")

        group_by = cast(list[str], d.pop("group_by"))


        measurement_data_available_from = d.pop("measurement_data_available_from")

        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        rows = []
        _rows = d.pop("rows")
        for rows_item_data in (_rows):
            rows_item = EconomicRowOut.from_dict(rows_item_data)



            rows.append(rows_item)


        economics_out = cls(
            basis=basis,
            bucket=bucket,
            context=context,
            economic_data_available_from=economic_data_available_from,
            group_by=group_by,
            measurement_data_available_from=measurement_data_available_from,
            period_end=period_end,
            period_start=period_start,
            rows=rows,
        )


        economics_out.additional_properties = d
        return economics_out

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
