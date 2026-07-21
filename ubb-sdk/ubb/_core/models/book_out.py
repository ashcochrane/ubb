from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="BookOut")



@_attrs_define
class BookOut:
    """ 
        Attributes:
            card_type (str):
            currency (str):
            id (str):
            is_default (bool):
            key (str):
            name (str):
            provider_key (str):
            version (int):
     """

    card_type: str
    currency: str
    id: str
    is_default: bool
    key: str
    name: str
    provider_key: str
    version: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        card_type = self.card_type

        currency = self.currency

        id = self.id

        is_default = self.is_default

        key = self.key

        name = self.name

        provider_key = self.provider_key

        version = self.version


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "card_type": card_type,
            "currency": currency,
            "id": id,
            "is_default": is_default,
            "key": key,
            "name": name,
            "provider_key": provider_key,
            "version": version,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        card_type = d.pop("card_type")

        currency = d.pop("currency")

        id = d.pop("id")

        is_default = d.pop("is_default")

        key = d.pop("key")

        name = d.pop("name")

        provider_key = d.pop("provider_key")

        version = d.pop("version")

        book_out = cls(
            card_type=card_type,
            currency=currency,
            id=id,
            is_default=is_default,
            key=key,
            name=name,
            provider_key=provider_key,
            version=version,
        )


        book_out.additional_properties = d
        return book_out

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
