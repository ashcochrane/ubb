from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.program_out_reward_type import ProgramOutRewardType
from ..models.program_out_status import ProgramOutStatus
from typing import cast






T = TypeVar("T", bound="ProgramOut")



@_attrs_define
class ProgramOut:
    """ 
        Attributes:
            attribution_window_days (int):
            created_at (str):
            estimated_cost_basis_points (int | None): A profit share's fallback where the actual supplier cost is not known:
                the tenant's cost as a share of revenue, in basis points, 0..10000.
            id (str):
            max_referrals_per_day (int | None):
            max_reward_micros (int | None):
            min_customer_age_hours (int | None):
            reward_amount_micros (int | None): The flat fee, in micros, paid exactly once per referral. Required for
                reward_type flat_fee; must be absent for a share.
            reward_share_basis_points (int | None): The share of the referred customer's revenue (revenue_share) or of the
                profit on it (profit_share), in basis points, 1..10000 (10000 = the whole), applied by dividing by 10,000
                exactly. Required for a share; must be absent for flat_fee.
            reward_type (ProgramOutRewardType):
            reward_window_days (int | None):
            status (ProgramOutStatus):
            updated_at (str):
     """

    attribution_window_days: int
    created_at: str
    estimated_cost_basis_points: int | None
    id: str
    max_referrals_per_day: int | None
    max_reward_micros: int | None
    min_customer_age_hours: int | None
    reward_amount_micros: int | None
    reward_share_basis_points: int | None
    reward_type: ProgramOutRewardType
    reward_window_days: int | None
    status: ProgramOutStatus
    updated_at: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        attribution_window_days = self.attribution_window_days

        created_at = self.created_at

        estimated_cost_basis_points: int | None
        estimated_cost_basis_points = self.estimated_cost_basis_points

        id = self.id

        max_referrals_per_day: int | None
        max_referrals_per_day = self.max_referrals_per_day

        max_reward_micros: int | None
        max_reward_micros = self.max_reward_micros

        min_customer_age_hours: int | None
        min_customer_age_hours = self.min_customer_age_hours

        reward_amount_micros: int | None
        reward_amount_micros = self.reward_amount_micros

        reward_share_basis_points: int | None
        reward_share_basis_points = self.reward_share_basis_points

        reward_type = self.reward_type.value

        reward_window_days: int | None
        reward_window_days = self.reward_window_days

        status = self.status.value

        updated_at = self.updated_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "attribution_window_days": attribution_window_days,
            "created_at": created_at,
            "estimated_cost_basis_points": estimated_cost_basis_points,
            "id": id,
            "max_referrals_per_day": max_referrals_per_day,
            "max_reward_micros": max_reward_micros,
            "min_customer_age_hours": min_customer_age_hours,
            "reward_amount_micros": reward_amount_micros,
            "reward_share_basis_points": reward_share_basis_points,
            "reward_type": reward_type,
            "reward_window_days": reward_window_days,
            "status": status,
            "updated_at": updated_at,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        attribution_window_days = d.pop("attribution_window_days")

        created_at = d.pop("created_at")

        def _parse_estimated_cost_basis_points(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        estimated_cost_basis_points = _parse_estimated_cost_basis_points(d.pop("estimated_cost_basis_points"))


        id = d.pop("id")

        def _parse_max_referrals_per_day(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        max_referrals_per_day = _parse_max_referrals_per_day(d.pop("max_referrals_per_day"))


        def _parse_max_reward_micros(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        max_reward_micros = _parse_max_reward_micros(d.pop("max_reward_micros"))


        def _parse_min_customer_age_hours(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        min_customer_age_hours = _parse_min_customer_age_hours(d.pop("min_customer_age_hours"))


        def _parse_reward_amount_micros(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        reward_amount_micros = _parse_reward_amount_micros(d.pop("reward_amount_micros"))


        def _parse_reward_share_basis_points(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        reward_share_basis_points = _parse_reward_share_basis_points(d.pop("reward_share_basis_points"))


        reward_type = ProgramOutRewardType(d.pop("reward_type"))




        def _parse_reward_window_days(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        reward_window_days = _parse_reward_window_days(d.pop("reward_window_days"))


        status = ProgramOutStatus(d.pop("status"))




        updated_at = d.pop("updated_at")

        program_out = cls(
            attribution_window_days=attribution_window_days,
            created_at=created_at,
            estimated_cost_basis_points=estimated_cost_basis_points,
            id=id,
            max_referrals_per_day=max_referrals_per_day,
            max_reward_micros=max_reward_micros,
            min_customer_age_hours=min_customer_age_hours,
            reward_amount_micros=reward_amount_micros,
            reward_share_basis_points=reward_share_basis_points,
            reward_type=reward_type,
            reward_window_days=reward_window_days,
            status=status,
            updated_at=updated_at,
        )


        program_out.additional_properties = d
        return program_out

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
