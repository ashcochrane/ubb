from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.program_create_request_reward_type import ProgramCreateRequestRewardType
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ProgramCreateRequest")



@_attrs_define
class ProgramCreateRequest:
    """ 
        Attributes:
            reward_type (ProgramCreateRequestRewardType):
            reward_value (float):
            attribution_window_days (int | Unset):  Default: 30.
            estimated_cost_percentage (float | None | Unset):
            max_referrals_per_day (int | None | Unset):
            max_reward_micros (int | None | Unset):
            min_customer_age_hours (int | None | Unset):
            reward_window_days (int | None | Unset):
     """

    reward_type: ProgramCreateRequestRewardType
    reward_value: float
    attribution_window_days: int | Unset = 30
    estimated_cost_percentage: float | None | Unset = UNSET
    max_referrals_per_day: int | None | Unset = UNSET
    max_reward_micros: int | None | Unset = UNSET
    min_customer_age_hours: int | None | Unset = UNSET
    reward_window_days: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        reward_type = self.reward_type.value

        reward_value = self.reward_value

        attribution_window_days = self.attribution_window_days

        estimated_cost_percentage: float | None | Unset
        if isinstance(self.estimated_cost_percentage, Unset):
            estimated_cost_percentage = UNSET
        else:
            estimated_cost_percentage = self.estimated_cost_percentage

        max_referrals_per_day: int | None | Unset
        if isinstance(self.max_referrals_per_day, Unset):
            max_referrals_per_day = UNSET
        else:
            max_referrals_per_day = self.max_referrals_per_day

        max_reward_micros: int | None | Unset
        if isinstance(self.max_reward_micros, Unset):
            max_reward_micros = UNSET
        else:
            max_reward_micros = self.max_reward_micros

        min_customer_age_hours: int | None | Unset
        if isinstance(self.min_customer_age_hours, Unset):
            min_customer_age_hours = UNSET
        else:
            min_customer_age_hours = self.min_customer_age_hours

        reward_window_days: int | None | Unset
        if isinstance(self.reward_window_days, Unset):
            reward_window_days = UNSET
        else:
            reward_window_days = self.reward_window_days


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "reward_type": reward_type,
            "reward_value": reward_value,
        })
        if attribution_window_days is not UNSET:
            field_dict["attribution_window_days"] = attribution_window_days
        if estimated_cost_percentage is not UNSET:
            field_dict["estimated_cost_percentage"] = estimated_cost_percentage
        if max_referrals_per_day is not UNSET:
            field_dict["max_referrals_per_day"] = max_referrals_per_day
        if max_reward_micros is not UNSET:
            field_dict["max_reward_micros"] = max_reward_micros
        if min_customer_age_hours is not UNSET:
            field_dict["min_customer_age_hours"] = min_customer_age_hours
        if reward_window_days is not UNSET:
            field_dict["reward_window_days"] = reward_window_days

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        reward_type = ProgramCreateRequestRewardType(d.pop("reward_type"))




        reward_value = d.pop("reward_value")

        attribution_window_days = d.pop("attribution_window_days", UNSET)

        def _parse_estimated_cost_percentage(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        estimated_cost_percentage = _parse_estimated_cost_percentage(d.pop("estimated_cost_percentage", UNSET))


        def _parse_max_referrals_per_day(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_referrals_per_day = _parse_max_referrals_per_day(d.pop("max_referrals_per_day", UNSET))


        def _parse_max_reward_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_reward_micros = _parse_max_reward_micros(d.pop("max_reward_micros", UNSET))


        def _parse_min_customer_age_hours(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_customer_age_hours = _parse_min_customer_age_hours(d.pop("min_customer_age_hours", UNSET))


        def _parse_reward_window_days(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        reward_window_days = _parse_reward_window_days(d.pop("reward_window_days", UNSET))


        program_create_request = cls(
            reward_type=reward_type,
            reward_value=reward_value,
            attribution_window_days=attribution_window_days,
            estimated_cost_percentage=estimated_cost_percentage,
            max_referrals_per_day=max_referrals_per_day,
            max_reward_micros=max_reward_micros,
            min_customer_age_hours=min_customer_age_hours,
            reward_window_days=reward_window_days,
        )


        program_create_request.additional_properties = d
        return program_create_request

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
