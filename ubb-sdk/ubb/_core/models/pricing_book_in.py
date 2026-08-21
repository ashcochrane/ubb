from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="PricingBookIn")



@_attrs_define
class PricingBookIn:
    """ Declare a Pricing Book: a catalogue of what this tenant charges.

    It names neither a supplier nor a currency, and both absences are
    deliberate. A tenant's price for a unit of work does not change because
    they switched supplier, and a tenant has exactly one currency
    (per-tenant single currency; multi-currency and FX are not supported), so
    a book that repeated either would be repeating a decision made elsewhere.
    A rule that should price one supplier's work differently pins `provider`
    as a selector, which is where that belongs.

    `is_default` marks the book a customer is priced from when nothing
    narrower applies. A tenant has at most one; declaring a second answers
    409.

        Attributes:
            key (str):
            is_default (bool | Unset):  Default: False.
            name (str | Unset):  Default: ''.
     """

    key: str
    is_default: bool | Unset = False
    name: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        is_default = self.is_default

        name = self.name


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
        })
        if is_default is not UNSET:
            field_dict["is_default"] = is_default
        if name is not UNSET:
            field_dict["name"] = name

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        is_default = d.pop("is_default", UNSET)

        name = d.pop("name", UNSET)

        pricing_book_in = cls(
            key=key,
            is_default=is_default,
            name=name,
        )


        pricing_book_in.additional_properties = d
        return pricing_book_in

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
