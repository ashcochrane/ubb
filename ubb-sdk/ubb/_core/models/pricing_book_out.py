from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="PricingBookOut")



@_attrs_define
class PricingBookOut:
    """ 
        Attributes:
            customer_id (None | str):
            id (str):
            is_default (bool):
            key (str):
            name (str):
            version (int):
     """

    customer_id: None | str
    id: str
    is_default: bool
    key: str
    name: str
    version: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        customer_id: None | str
        customer_id = self.customer_id

        id = self.id

        is_default = self.is_default

        key = self.key

        name = self.name

        version = self.version


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_id": customer_id,
            "id": id,
            "is_default": is_default,
            "key": key,
            "name": name,
            "version": version,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_customer_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        customer_id = _parse_customer_id(d.pop("customer_id"))


        id = d.pop("id")

        is_default = d.pop("is_default")

        key = d.pop("key")

        name = d.pop("name")

        version = d.pop("version")

        pricing_book_out = cls(
            customer_id=customer_id,
            id=id,
            is_default=is_default,
            key=key,
            name=name,
            version=version,
        )


        pricing_book_out.additional_properties = d
        return pricing_book_out

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
