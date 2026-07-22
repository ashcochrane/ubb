from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="ReferralOut")



@_attrs_define
class ReferralOut:
    """ 
        Attributes:
            attributed_at (str):
            id (str):
            referral_code_used (str):
            referred_customer_id (str):
            referred_external_id (str):
            reward_type (str):
            reward_window_ends_at (None | str):
            status (str):
            total_earned_micros (int):
            total_referred_spend_micros (int):
     """

    attributed_at: str
    id: str
    referral_code_used: str
    referred_customer_id: str
    referred_external_id: str
    reward_type: str
    reward_window_ends_at: None | str
    status: str
    total_earned_micros: int
    total_referred_spend_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        attributed_at = self.attributed_at

        id = self.id

        referral_code_used = self.referral_code_used

        referred_customer_id = self.referred_customer_id

        referred_external_id = self.referred_external_id

        reward_type = self.reward_type

        reward_window_ends_at: None | str
        reward_window_ends_at = self.reward_window_ends_at

        status = self.status

        total_earned_micros = self.total_earned_micros

        total_referred_spend_micros = self.total_referred_spend_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "attributed_at": attributed_at,
            "id": id,
            "referral_code_used": referral_code_used,
            "referred_customer_id": referred_customer_id,
            "referred_external_id": referred_external_id,
            "reward_type": reward_type,
            "reward_window_ends_at": reward_window_ends_at,
            "status": status,
            "total_earned_micros": total_earned_micros,
            "total_referred_spend_micros": total_referred_spend_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        attributed_at = d.pop("attributed_at")

        id = d.pop("id")

        referral_code_used = d.pop("referral_code_used")

        referred_customer_id = d.pop("referred_customer_id")

        referred_external_id = d.pop("referred_external_id")

        reward_type = d.pop("reward_type")

        def _parse_reward_window_ends_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        reward_window_ends_at = _parse_reward_window_ends_at(d.pop("reward_window_ends_at"))


        status = d.pop("status")

        total_earned_micros = d.pop("total_earned_micros")

        total_referred_spend_micros = d.pop("total_referred_spend_micros")

        referral_out = cls(
            attributed_at=attributed_at,
            id=id,
            referral_code_used=referral_code_used,
            referred_customer_id=referred_customer_id,
            referred_external_id=referred_external_id,
            reward_type=reward_type,
            reward_window_ends_at=reward_window_ends_at,
            status=status,
            total_earned_micros=total_earned_micros,
            total_referred_spend_micros=total_referred_spend_micros,
        )


        referral_out.additional_properties = d
        return referral_out

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
