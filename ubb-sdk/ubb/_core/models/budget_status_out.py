from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="BudgetStatusOut")



@_attrs_define
class BudgetStatusOut:
    """ 
        Attributes:
            cap_micros (int):
            enforce_mode (str):
            pct (float):
            period (str):
            spend_micros (int):
     """

    cap_micros: int
    enforce_mode: str
    pct: float
    period: str
    spend_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        cap_micros = self.cap_micros

        enforce_mode = self.enforce_mode

        pct = self.pct

        period = self.period

        spend_micros = self.spend_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "cap_micros": cap_micros,
            "enforce_mode": enforce_mode,
            "pct": pct,
            "period": period,
            "spend_micros": spend_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cap_micros = d.pop("cap_micros")

        enforce_mode = d.pop("enforce_mode")

        pct = d.pop("pct")

        period = d.pop("period")

        spend_micros = d.pop("spend_micros")

        budget_status_out = cls(
            cap_micros=cap_micros,
            enforce_mode=enforce_mode,
            pct=pct,
            period=period,
            spend_micros=spend_micros,
        )


        budget_status_out.additional_properties = d
        return budget_status_out

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
