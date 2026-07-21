from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ApiKeyOut")



@_attrs_define
class ApiKeyOut:
    """ 
        Attributes:
            created_at (str):
            id (str):
            is_active (bool):
            key_prefix (str):
            label (str):
            last_used_at (None | str | Unset):
     """

    created_at: str
    id: str
    is_active: bool
    key_prefix: str
    label: str
    last_used_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        id = self.id

        is_active = self.is_active

        key_prefix = self.key_prefix

        label = self.label

        last_used_at: None | str | Unset
        if isinstance(self.last_used_at, Unset):
            last_used_at = UNSET
        else:
            last_used_at = self.last_used_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "id": id,
            "is_active": is_active,
            "key_prefix": key_prefix,
            "label": label,
        })
        if last_used_at is not UNSET:
            field_dict["last_used_at"] = last_used_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        id = d.pop("id")

        is_active = d.pop("is_active")

        key_prefix = d.pop("key_prefix")

        label = d.pop("label")

        def _parse_last_used_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_used_at = _parse_last_used_at(d.pop("last_used_at", UNSET))


        api_key_out = cls(
            created_at=created_at,
            id=id,
            is_active=is_active,
            key_prefix=key_prefix,
            label=label,
            last_used_at=last_used_at,
        )


        api_key_out.additional_properties = d
        return api_key_out

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
