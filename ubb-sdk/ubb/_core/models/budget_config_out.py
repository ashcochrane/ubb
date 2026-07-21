from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="BudgetConfigOut")



@_attrs_define
class BudgetConfigOut:
    """ 
        Attributes:
            alert_levels (list[int]):
            cap_micros (int):
            enforce_mode (str):
            fail_closed (bool):
            hard_stop_pct (int):
     """

    alert_levels: list[int]
    cap_micros: int
    enforce_mode: str
    fail_closed: bool
    hard_stop_pct: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        alert_levels = self.alert_levels



        cap_micros = self.cap_micros

        enforce_mode = self.enforce_mode

        fail_closed = self.fail_closed

        hard_stop_pct = self.hard_stop_pct


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "alert_levels": alert_levels,
            "cap_micros": cap_micros,
            "enforce_mode": enforce_mode,
            "fail_closed": fail_closed,
            "hard_stop_pct": hard_stop_pct,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        alert_levels = cast(list[int], d.pop("alert_levels"))


        cap_micros = d.pop("cap_micros")

        enforce_mode = d.pop("enforce_mode")

        fail_closed = d.pop("fail_closed")

        hard_stop_pct = d.pop("hard_stop_pct")

        budget_config_out = cls(
            alert_levels=alert_levels,
            cap_micros=cap_micros,
            enforce_mode=enforce_mode,
            fail_closed=fail_closed,
            hard_stop_pct=hard_stop_pct,
        )


        budget_config_out.additional_properties = d
        return budget_config_out

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
