from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.margin_trend_point_out import MarginTrendPointOut





T = TypeVar("T", bound="MarginTrendOut")



@_attrs_define
class MarginTrendOut:
    """ 
        Attributes:
            customer_id (str):
            points (list[MarginTrendPointOut]):
     """

    customer_id: str
    points: list[MarginTrendPointOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.margin_trend_point_out import MarginTrendPointOut
        customer_id = self.customer_id

        points = []
        for points_item_data in self.points:
            points_item = points_item_data.to_dict()
            points.append(points_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_id": customer_id,
            "points": points,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.margin_trend_point_out import MarginTrendPointOut
        d = dict(src_dict)
        customer_id = d.pop("customer_id")

        points = []
        _points = d.pop("points")
        for points_item_data in (_points):
            points_item = MarginTrendPointOut.from_dict(points_item_data)



            points.append(points_item)


        margin_trend_out = cls(
            customer_id=customer_id,
            points=points,
        )


        margin_trend_out.additional_properties = d
        return margin_trend_out

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
