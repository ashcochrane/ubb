from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="AnalyticsSummaryOut")



@_attrs_define
class AnalyticsSummaryOut:
    """ 
        Attributes:
            active_referrals (int):
            total_referrals (int):
            total_referred_spend_micros (int):
            total_referrers (int):
            total_rewards_earned_micros (int):
     """

    active_referrals: int
    total_referrals: int
    total_referred_spend_micros: int
    total_referrers: int
    total_rewards_earned_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        active_referrals = self.active_referrals

        total_referrals = self.total_referrals

        total_referred_spend_micros = self.total_referred_spend_micros

        total_referrers = self.total_referrers

        total_rewards_earned_micros = self.total_rewards_earned_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "active_referrals": active_referrals,
            "total_referrals": total_referrals,
            "total_referred_spend_micros": total_referred_spend_micros,
            "total_referrers": total_referrers,
            "total_rewards_earned_micros": total_rewards_earned_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        active_referrals = d.pop("active_referrals")

        total_referrals = d.pop("total_referrals")

        total_referred_spend_micros = d.pop("total_referred_spend_micros")

        total_referrers = d.pop("total_referrers")

        total_rewards_earned_micros = d.pop("total_rewards_earned_micros")

        analytics_summary_out = cls(
            active_referrals=active_referrals,
            total_referrals=total_referrals,
            total_referred_spend_micros=total_referred_spend_micros,
            total_referrers=total_referrers,
            total_rewards_earned_micros=total_rewards_earned_micros,
        )


        analytics_summary_out.additional_properties = d
        return analytics_summary_out

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
