from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="PlanIn")



@_attrs_define
class PlanIn:
    """ 
        Attributes:
            key (str):
            name (str):
            access_fee_micros (int | Unset):  Default: 0.
            interval (str | Unset):  Default: 'month'.
            per_seat_micros (int | Unset):  Default: 0.
     """

    key: str
    name: str
    access_fee_micros: int | Unset = 0
    interval: str | Unset = 'month'
    per_seat_micros: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        name = self.name

        access_fee_micros = self.access_fee_micros

        interval = self.interval

        per_seat_micros = self.per_seat_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
            "name": name,
        })
        if access_fee_micros is not UNSET:
            field_dict["access_fee_micros"] = access_fee_micros
        if interval is not UNSET:
            field_dict["interval"] = interval
        if per_seat_micros is not UNSET:
            field_dict["per_seat_micros"] = per_seat_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        name = d.pop("name")

        access_fee_micros = d.pop("access_fee_micros", UNSET)

        interval = d.pop("interval", UNSET)

        per_seat_micros = d.pop("per_seat_micros", UNSET)

        plan_in = cls(
            key=key,
            name=name,
            access_fee_micros=access_fee_micros,
            interval=interval,
            per_seat_micros=per_seat_micros,
        )


        plan_in.additional_properties = d
        return plan_in

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
