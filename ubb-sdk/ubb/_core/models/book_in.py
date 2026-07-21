from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="BookIn")



@_attrs_define
class BookIn:
    """ 
        Attributes:
            card_type (str):
            key (str):
            currency (None | str | Unset):
            is_default (bool | Unset):  Default: False.
            name (str | Unset):  Default: ''.
            provider_key (str | Unset):  Default: ''.
     """

    card_type: str
    key: str
    currency: None | str | Unset = UNSET
    is_default: bool | Unset = False
    name: str | Unset = ''
    provider_key: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        card_type = self.card_type

        key = self.key

        currency: None | str | Unset
        if isinstance(self.currency, Unset):
            currency = UNSET
        else:
            currency = self.currency

        is_default = self.is_default

        name = self.name

        provider_key = self.provider_key


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "card_type": card_type,
            "key": key,
        })
        if currency is not UNSET:
            field_dict["currency"] = currency
        if is_default is not UNSET:
            field_dict["is_default"] = is_default
        if name is not UNSET:
            field_dict["name"] = name
        if provider_key is not UNSET:
            field_dict["provider_key"] = provider_key

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        card_type = d.pop("card_type")

        key = d.pop("key")

        def _parse_currency(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        currency = _parse_currency(d.pop("currency", UNSET))


        is_default = d.pop("is_default", UNSET)

        name = d.pop("name", UNSET)

        provider_key = d.pop("provider_key", UNSET)

        book_in = cls(
            card_type=card_type,
            key=key,
            currency=currency,
            is_default=is_default,
            name=name,
            provider_key=provider_key,
        )


        book_in.additional_properties = d
        return book_in

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
