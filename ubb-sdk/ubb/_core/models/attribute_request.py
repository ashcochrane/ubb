from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="AttributeRequest")



@_attrs_define
class AttributeRequest:
    """ 
        Attributes:
            customer_id (str):
            code (None | str | Unset):
            link_token (None | str | Unset):
     """

    customer_id: str
    code: None | str | Unset = UNSET
    link_token: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        customer_id = self.customer_id

        code: None | str | Unset
        if isinstance(self.code, Unset):
            code = UNSET
        else:
            code = self.code

        link_token: None | str | Unset
        if isinstance(self.link_token, Unset):
            link_token = UNSET
        else:
            link_token = self.link_token


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_id": customer_id,
        })
        if code is not UNSET:
            field_dict["code"] = code
        if link_token is not UNSET:
            field_dict["link_token"] = link_token

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        customer_id = d.pop("customer_id")

        def _parse_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        code = _parse_code(d.pop("code", UNSET))


        def _parse_link_token(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        link_token = _parse_link_token(d.pop("link_token", UNSET))


        attribute_request = cls(
            customer_id=customer_id,
            code=code,
            link_token=link_token,
        )


        attribute_request.additional_properties = d
        return attribute_request

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
