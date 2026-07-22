from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.business_margin_totals import BusinessMarginTotals
  from ..models.seat_margin_out import SeatMarginOut





T = TypeVar("T", bound="BusinessMarginOut")



@_attrs_define
class BusinessMarginOut:
    """ 
        Attributes:
            business_id (str):
            external_id (str):
            seats (list[SeatMarginOut]):
            totals (BusinessMarginTotals):
     """

    business_id: str
    external_id: str
    seats: list[SeatMarginOut]
    totals: BusinessMarginTotals
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.business_margin_totals import BusinessMarginTotals
        from ..models.seat_margin_out import SeatMarginOut
        business_id = self.business_id

        external_id = self.external_id

        seats = []
        for seats_item_data in self.seats:
            seats_item = seats_item_data.to_dict()
            seats.append(seats_item)



        totals = self.totals.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "business_id": business_id,
            "external_id": external_id,
            "seats": seats,
            "totals": totals,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.business_margin_totals import BusinessMarginTotals
        from ..models.seat_margin_out import SeatMarginOut
        d = dict(src_dict)
        business_id = d.pop("business_id")

        external_id = d.pop("external_id")

        seats = []
        _seats = d.pop("seats")
        for seats_item_data in (_seats):
            seats_item = SeatMarginOut.from_dict(seats_item_data)



            seats.append(seats_item)


        totals = BusinessMarginTotals.from_dict(d.pop("totals"))




        business_margin_out = cls(
            business_id=business_id,
            external_id=external_id,
            seats=seats,
            totals=totals,
        )


        business_margin_out.additional_properties = d
        return business_margin_out

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
