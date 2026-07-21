from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="PlanOut")



@_attrs_define
class PlanOut:
    """ 
        Attributes:
            access_fee_micros (int):
            id (str):
            interval (str):
            key (str):
            name (str):
            per_seat_micros (int):
     """

    access_fee_micros: int
    id: str
    interval: str
    key: str
    name: str
    per_seat_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        access_fee_micros = self.access_fee_micros

        id = self.id

        interval = self.interval

        key = self.key

        name = self.name

        per_seat_micros = self.per_seat_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "access_fee_micros": access_fee_micros,
            "id": id,
            "interval": interval,
            "key": key,
            "name": name,
            "per_seat_micros": per_seat_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        access_fee_micros = d.pop("access_fee_micros")

        id = d.pop("id")

        interval = d.pop("interval")

        key = d.pop("key")

        name = d.pop("name")

        per_seat_micros = d.pop("per_seat_micros")

        plan_out = cls(
            access_fee_micros=access_fee_micros,
            id=id,
            interval=interval,
            key=key,
            name=name,
            per_seat_micros=per_seat_micros,
        )


        plan_out.additional_properties = d
        return plan_out

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
