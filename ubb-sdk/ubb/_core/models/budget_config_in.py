from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="BudgetConfigIn")



@_attrs_define
class BudgetConfigIn:
    """ 
        Attributes:
            cap_micros (int):
            alert_levels (list[int] | None | Unset):
            enforce_mode (str | Unset):  Default: 'advisory'.
            fail_closed (bool | Unset):  Default: False.
            hard_stop_pct (int | Unset):  Default: 100.
     """

    cap_micros: int
    alert_levels: list[int] | None | Unset = UNSET
    enforce_mode: str | Unset = 'advisory'
    fail_closed: bool | Unset = False
    hard_stop_pct: int | Unset = 100
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        cap_micros = self.cap_micros

        alert_levels: list[int] | None | Unset
        if isinstance(self.alert_levels, Unset):
            alert_levels = UNSET
        elif isinstance(self.alert_levels, list):
            alert_levels = self.alert_levels


        else:
            alert_levels = self.alert_levels

        enforce_mode = self.enforce_mode

        fail_closed = self.fail_closed

        hard_stop_pct = self.hard_stop_pct


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "cap_micros": cap_micros,
        })
        if alert_levels is not UNSET:
            field_dict["alert_levels"] = alert_levels
        if enforce_mode is not UNSET:
            field_dict["enforce_mode"] = enforce_mode
        if fail_closed is not UNSET:
            field_dict["fail_closed"] = fail_closed
        if hard_stop_pct is not UNSET:
            field_dict["hard_stop_pct"] = hard_stop_pct

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cap_micros = d.pop("cap_micros")

        def _parse_alert_levels(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                alert_levels_type_0 = cast(list[int], data)

                return alert_levels_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        alert_levels = _parse_alert_levels(d.pop("alert_levels", UNSET))


        enforce_mode = d.pop("enforce_mode", UNSET)

        fail_closed = d.pop("fail_closed", UNSET)

        hard_stop_pct = d.pop("hard_stop_pct", UNSET)

        budget_config_in = cls(
            cap_micros=cap_micros,
            alert_levels=alert_levels,
            enforce_mode=enforce_mode,
            fail_closed=fail_closed,
            hard_stop_pct=hard_stop_pct,
        )


        budget_config_in.additional_properties = d
        return budget_config_in

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
