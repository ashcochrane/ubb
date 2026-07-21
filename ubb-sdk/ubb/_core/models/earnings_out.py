from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="EarningsOut")



@_attrs_define
class EarningsOut:
    """ 
        Attributes:
            active_referrals (int):
            referrer_customer_id (str):
            total_earned_micros (int):
            total_referrals (int):
            total_referred_spend_micros (int):
     """

    active_referrals: int
    referrer_customer_id: str
    total_earned_micros: int
    total_referrals: int
    total_referred_spend_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        active_referrals = self.active_referrals

        referrer_customer_id = self.referrer_customer_id

        total_earned_micros = self.total_earned_micros

        total_referrals = self.total_referrals

        total_referred_spend_micros = self.total_referred_spend_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "active_referrals": active_referrals,
            "referrer_customer_id": referrer_customer_id,
            "total_earned_micros": total_earned_micros,
            "total_referrals": total_referrals,
            "total_referred_spend_micros": total_referred_spend_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        active_referrals = d.pop("active_referrals")

        referrer_customer_id = d.pop("referrer_customer_id")

        total_earned_micros = d.pop("total_earned_micros")

        total_referrals = d.pop("total_referrals")

        total_referred_spend_micros = d.pop("total_referred_spend_micros")

        earnings_out = cls(
            active_referrals=active_referrals,
            referrer_customer_id=referrer_customer_id,
            total_earned_micros=total_earned_micros,
            total_referrals=total_referrals,
            total_referred_spend_micros=total_referred_spend_micros,
        )


        earnings_out.additional_properties = d
        return earnings_out

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
