from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="ApiKeyCreateIn")



@_attrs_define
class ApiKeyCreateIn:
    """ 
        Attributes:
            is_test (bool | Unset):  Default: False.
            label (str | Unset):  Default: ''.
     """

    is_test: bool | Unset = False
    label: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        is_test = self.is_test

        label = self.label


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if is_test is not UNSET:
            field_dict["is_test"] = is_test
        if label is not UNSET:
            field_dict["label"] = label

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        is_test = d.pop("is_test", UNSET)

        label = d.pop("label", UNSET)

        api_key_create_in = cls(
            is_test=is_test,
            label=label,
        )


        api_key_create_in.additional_properties = d
        return api_key_create_in

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
