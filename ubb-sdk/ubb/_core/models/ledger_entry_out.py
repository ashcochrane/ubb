from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="LedgerEntryOut")



@_attrs_define
class LedgerEntryOut:
    """ 
        Attributes:
            calculation_method (str):
            created_at (str):
            id (str):
            period_end (str):
            period_start (str):
            raw_cost_micros (int):
            referred_spend_micros (int):
            reward_micros (int):
     """

    calculation_method: str
    created_at: str
    id: str
    period_end: str
    period_start: str
    raw_cost_micros: int
    referred_spend_micros: int
    reward_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        calculation_method = self.calculation_method

        created_at = self.created_at

        id = self.id

        period_end = self.period_end

        period_start = self.period_start

        raw_cost_micros = self.raw_cost_micros

        referred_spend_micros = self.referred_spend_micros

        reward_micros = self.reward_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "calculation_method": calculation_method,
            "created_at": created_at,
            "id": id,
            "period_end": period_end,
            "period_start": period_start,
            "raw_cost_micros": raw_cost_micros,
            "referred_spend_micros": referred_spend_micros,
            "reward_micros": reward_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        calculation_method = d.pop("calculation_method")

        created_at = d.pop("created_at")

        id = d.pop("id")

        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        raw_cost_micros = d.pop("raw_cost_micros")

        referred_spend_micros = d.pop("referred_spend_micros")

        reward_micros = d.pop("reward_micros")

        ledger_entry_out = cls(
            calculation_method=calculation_method,
            created_at=created_at,
            id=id,
            period_end=period_end,
            period_start=period_start,
            raw_cost_micros=raw_cost_micros,
            referred_spend_micros=referred_spend_micros,
            reward_micros=reward_micros,
        )


        ledger_entry_out.additional_properties = d
        return ledger_entry_out

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
