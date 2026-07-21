from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="CustomerBillingProfileIn")



@_attrs_define
class CustomerBillingProfileIn:
    """ 
        Attributes:
            min_balance_micros (int | None | Unset):
            soft_min_balance_micros (int | None | Unset):
            topup_grant_expiry_days (int | None | Unset):
     """

    min_balance_micros: int | None | Unset = UNSET
    soft_min_balance_micros: int | None | Unset = UNSET
    topup_grant_expiry_days: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        min_balance_micros: int | None | Unset
        if isinstance(self.min_balance_micros, Unset):
            min_balance_micros = UNSET
        else:
            min_balance_micros = self.min_balance_micros

        soft_min_balance_micros: int | None | Unset
        if isinstance(self.soft_min_balance_micros, Unset):
            soft_min_balance_micros = UNSET
        else:
            soft_min_balance_micros = self.soft_min_balance_micros

        topup_grant_expiry_days: int | None | Unset
        if isinstance(self.topup_grant_expiry_days, Unset):
            topup_grant_expiry_days = UNSET
        else:
            topup_grant_expiry_days = self.topup_grant_expiry_days


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if min_balance_micros is not UNSET:
            field_dict["min_balance_micros"] = min_balance_micros
        if soft_min_balance_micros is not UNSET:
            field_dict["soft_min_balance_micros"] = soft_min_balance_micros
        if topup_grant_expiry_days is not UNSET:
            field_dict["topup_grant_expiry_days"] = topup_grant_expiry_days

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_min_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_balance_micros = _parse_min_balance_micros(d.pop("min_balance_micros", UNSET))


        def _parse_soft_min_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        soft_min_balance_micros = _parse_soft_min_balance_micros(d.pop("soft_min_balance_micros", UNSET))


        def _parse_topup_grant_expiry_days(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        topup_grant_expiry_days = _parse_topup_grant_expiry_days(d.pop("topup_grant_expiry_days", UNSET))


        customer_billing_profile_in = cls(
            min_balance_micros=min_balance_micros,
            soft_min_balance_micros=soft_min_balance_micros,
            topup_grant_expiry_days=topup_grant_expiry_days,
        )


        customer_billing_profile_in.additional_properties = d
        return customer_billing_profile_in

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
