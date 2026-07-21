from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="SyncResponse")



@_attrs_define
class SyncResponse:
    """ 
        Attributes:
            errors (int):
            skipped (int):
            synced (int):
     """

    errors: int
    skipped: int
    synced: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        errors = self.errors

        skipped = self.skipped

        synced = self.synced


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "errors": errors,
            "skipped": skipped,
            "synced": synced,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        errors = d.pop("errors")

        skipped = d.pop("skipped")

        synced = d.pop("synced")

        sync_response = cls(
            errors=errors,
            skipped=skipped,
            synced=synced,
        )


        sync_response.additional_properties = d
        return sync_response

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
