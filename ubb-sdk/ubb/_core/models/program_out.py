from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="ProgramOut")



@_attrs_define
class ProgramOut:
    """ 
        Attributes:
            attribution_window_days (int):
            created_at (str):
            estimated_cost_percentage (float | None):
            id (str):
            max_referrals_per_day (int | None):
            max_reward_micros (int | None):
            min_customer_age_hours (int | None):
            reward_type (str):
            reward_value (float):
            reward_window_days (int | None):
            status (str):
            updated_at (str):
     """

    attribution_window_days: int
    created_at: str
    estimated_cost_percentage: float | None
    id: str
    max_referrals_per_day: int | None
    max_reward_micros: int | None
    min_customer_age_hours: int | None
    reward_type: str
    reward_value: float
    reward_window_days: int | None
    status: str
    updated_at: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        attribution_window_days = self.attribution_window_days

        created_at = self.created_at

        estimated_cost_percentage: float | None
        estimated_cost_percentage = self.estimated_cost_percentage

        id = self.id

        max_referrals_per_day: int | None
        max_referrals_per_day = self.max_referrals_per_day

        max_reward_micros: int | None
        max_reward_micros = self.max_reward_micros

        min_customer_age_hours: int | None
        min_customer_age_hours = self.min_customer_age_hours

        reward_type = self.reward_type

        reward_value = self.reward_value

        reward_window_days: int | None
        reward_window_days = self.reward_window_days

        status = self.status

        updated_at = self.updated_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "attribution_window_days": attribution_window_days,
            "created_at": created_at,
            "estimated_cost_percentage": estimated_cost_percentage,
            "id": id,
            "max_referrals_per_day": max_referrals_per_day,
            "max_reward_micros": max_reward_micros,
            "min_customer_age_hours": min_customer_age_hours,
            "reward_type": reward_type,
            "reward_value": reward_value,
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

        def _parse_estimated_cost_percentage(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        estimated_cost_percentage = _parse_estimated_cost_percentage(d.pop("estimated_cost_percentage"))


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


        reward_type = d.pop("reward_type")

        reward_value = d.pop("reward_value")

        def _parse_reward_window_days(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        reward_window_days = _parse_reward_window_days(d.pop("reward_window_days"))


        status = d.pop("status")

        updated_at = d.pop("updated_at")

        program_out = cls(
            attribution_window_days=attribution_window_days,
            created_at=created_at,
            estimated_cost_percentage=estimated_cost_percentage,
            id=id,
            max_referrals_per_day=max_referrals_per_day,
            max_reward_micros=max_reward_micros,
            min_customer_age_hours=min_customer_age_hours,
            reward_type=reward_type,
            reward_value=reward_value,
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
