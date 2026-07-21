from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="TenantMarkupOut")



@_attrs_define
class TenantMarkupOut:
    """ 
        Attributes:
            fixed_uplift_micros (int):
            markup_percentage_micros (int):
     """

    fixed_uplift_micros: int
    markup_percentage_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        fixed_uplift_micros = self.fixed_uplift_micros

        markup_percentage_micros = self.markup_percentage_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "fixed_uplift_micros": fixed_uplift_micros,
            "markup_percentage_micros": markup_percentage_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fixed_uplift_micros = d.pop("fixed_uplift_micros")

        markup_percentage_micros = d.pop("markup_percentage_micros")

        tenant_markup_out = cls(
            fixed_uplift_micros=fixed_uplift_micros,
            markup_percentage_micros=markup_percentage_micros,
        )


        tenant_markup_out.additional_properties = d
        return tenant_markup_out

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
