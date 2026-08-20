from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.waived_loss_row import WaivedLossRow





T = TypeVar("T", bound="WaivedLossOut")



@_attrs_define
class WaivedLossOut:
    """ What waiving has cost, as money, for the economic horizon.

        Attributes:
            basis (str):
            rows (list[WaivedLossRow]):
     """

    basis: str
    rows: list[WaivedLossRow]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.waived_loss_row import WaivedLossRow
        basis = self.basis

        rows = []
        for rows_item_data in self.rows:
            rows_item = rows_item_data.to_dict()
            rows.append(rows_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "basis": basis,
            "rows": rows,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.waived_loss_row import WaivedLossRow
        d = dict(src_dict)
        basis = d.pop("basis")

        rows = []
        _rows = d.pop("rows")
        for rows_item_data in (_rows):
            rows_item = WaivedLossRow.from_dict(rows_item_data)



            rows.append(rows_item)


        waived_loss_out = cls(
            basis=basis,
            rows=rows,
        )


        waived_loss_out.additional_properties = d
        return waived_loss_out

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
