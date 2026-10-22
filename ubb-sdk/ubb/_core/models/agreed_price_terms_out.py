from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="AgreedPriceTermsOut")



@_attrs_define
class AgreedPriceTermsOut:
    """ What one delivered unit of the kind of work sells for, in USD micros.

        Attributes:
            agreed_price_micros (int):
     """

    agreed_price_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        agreed_price_micros = self.agreed_price_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "agreed_price_micros": agreed_price_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        agreed_price_micros = d.pop("agreed_price_micros")

        agreed_price_terms_out = cls(
            agreed_price_micros=agreed_price_micros,
        )


        agreed_price_terms_out.additional_properties = d
        return agreed_price_terms_out

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
