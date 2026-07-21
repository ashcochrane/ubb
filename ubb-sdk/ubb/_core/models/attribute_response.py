from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="AttributeResponse")



@_attrs_define
class AttributeResponse:
    """ 
        Attributes:
            referral_id (str):
            referred_customer_id (str):
            referrer_id (str):
            status (str):
     """

    referral_id: str
    referred_customer_id: str
    referrer_id: str
    status: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        referral_id = self.referral_id

        referred_customer_id = self.referred_customer_id

        referrer_id = self.referrer_id

        status = self.status


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "referral_id": referral_id,
            "referred_customer_id": referred_customer_id,
            "referrer_id": referrer_id,
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        referral_id = d.pop("referral_id")

        referred_customer_id = d.pop("referred_customer_id")

        referrer_id = d.pop("referrer_id")

        status = d.pop("status")

        attribute_response = cls(
            referral_id=referral_id,
            referred_customer_id=referred_customer_id,
            referrer_id=referrer_id,
            status=status,
        )


        attribute_response.additional_properties = d
        return attribute_response

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
