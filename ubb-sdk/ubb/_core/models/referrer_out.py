from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="ReferrerOut")



@_attrs_define
class ReferrerOut:
    """ 
        Attributes:
            created_at (str):
            customer_id (str):
            id (str):
            is_active (bool):
            referral_code (str):
            referral_link_token (str):
     """

    created_at: str
    customer_id: str
    id: str
    is_active: bool
    referral_code: str
    referral_link_token: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        customer_id = self.customer_id

        id = self.id

        is_active = self.is_active

        referral_code = self.referral_code

        referral_link_token = self.referral_link_token


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "customer_id": customer_id,
            "id": id,
            "is_active": is_active,
            "referral_code": referral_code,
            "referral_link_token": referral_link_token,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        customer_id = d.pop("customer_id")

        id = d.pop("id")

        is_active = d.pop("is_active")

        referral_code = d.pop("referral_code")

        referral_link_token = d.pop("referral_link_token")

        referrer_out = cls(
            created_at=created_at,
            customer_id=customer_id,
            id=id,
            is_active=is_active,
            referral_code=referral_code,
            referral_link_token=referral_link_token,
        )


        referrer_out.additional_properties = d
        return referrer_out

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
