from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="StatusResponse")



@_attrs_define
class StatusResponse:
    """ The tiny cross-product acknowledgement body: ``{"status": "<word>"}``.

    One shared out-type (#98) for the endpoints that answer a mutation with a
    single status word (``ok`` / ``deleted`` / ``no_override`` / ``deactivated``
    / ``revoked`` / …) — kernel-owned so every product can declare it without
    crossing a product boundary (ADR-001). The value stays an open string
    (ADR-003 open enums).

        Attributes:
            status (str):
     """

    status: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        status = self.status


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        status = d.pop("status")

        status_response = cls(
            status=status,
        )


        status_response.additional_properties = d
        return status_response

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
