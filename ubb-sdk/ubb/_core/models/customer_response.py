from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="CustomerResponse")



@_attrs_define
class CustomerResponse:
    """ 
        Attributes:
            external_id (str):
            id (str):
            status (str):
            stripe_customer_id (str):
     """

    external_id: str
    id: str
    status: str
    stripe_customer_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        external_id = self.external_id

        id = self.id

        status = self.status

        stripe_customer_id = self.stripe_customer_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "external_id": external_id,
            "id": id,
            "status": status,
            "stripe_customer_id": stripe_customer_id,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        external_id = d.pop("external_id")

        id = d.pop("id")

        status = d.pop("status")

        stripe_customer_id = d.pop("stripe_customer_id")

        customer_response = cls(
            external_id=external_id,
            id=id,
            status=status,
            stripe_customer_id=stripe_customer_id,
        )


        customer_response.additional_properties = d
        return customer_response

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
