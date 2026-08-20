from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.projected_adjustment_row import ProjectedAdjustmentRow





T = TypeVar("T", bound="ProjectedAdjustmentOut")



@_attrs_define
class ProjectedAdjustmentOut:
    """ What a recovery would be worth, per customer — and nothing that bills.

    A projection, never an instruction. UBB does not back-bill: it tells you
    what completing these postings would be worth and leaves the decision, and
    the money movement, with you. There is no grand total across currencies,
    because adding two denominations produces a number in neither.

        Attributes:
            basis (str):
            postings_examined (int):
            postings_not_examined (int):
            rows (list[ProjectedAdjustmentRow]):
     """

    basis: str
    postings_examined: int
    postings_not_examined: int
    rows: list[ProjectedAdjustmentRow]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.projected_adjustment_row import ProjectedAdjustmentRow
        basis = self.basis

        postings_examined = self.postings_examined

        postings_not_examined = self.postings_not_examined

        rows = []
        for rows_item_data in self.rows:
            rows_item = rows_item_data.to_dict()
            rows.append(rows_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "basis": basis,
            "postings_examined": postings_examined,
            "postings_not_examined": postings_not_examined,
            "rows": rows,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.projected_adjustment_row import ProjectedAdjustmentRow
        d = dict(src_dict)
        basis = d.pop("basis")

        postings_examined = d.pop("postings_examined")

        postings_not_examined = d.pop("postings_not_examined")

        rows = []
        _rows = d.pop("rows")
        for rows_item_data in (_rows):
            rows_item = ProjectedAdjustmentRow.from_dict(rows_item_data)



            rows.append(rows_item)


        projected_adjustment_out = cls(
            basis=basis,
            postings_examined=postings_examined,
            postings_not_examined=postings_not_examined,
            rows=rows,
        )


        projected_adjustment_out.additional_properties = d
        return projected_adjustment_out

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
