from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ProviderUpdateIn")



@_attrs_define
class ProviderUpdateIn:
    """ Rename or retire a supplier.

    There is no delete, here or anywhere: a Provider is retired and never
    removed, because supplier COGS attribution keys on its identity and
    deleting one would silently rewrite what historical postings say they cost.
    `retired` is a two-way switch rather than a timestamp a caller supplies —
    WHEN a supplier was retired is UBB's record of an act, not an input.

        Attributes:
            key (None | str | Unset):
            retired (bool | None | Unset):
     """

    key: None | str | Unset = UNSET
    retired: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key: None | str | Unset
        if isinstance(self.key, Unset):
            key = UNSET
        else:
            key = self.key

        retired: bool | None | Unset
        if isinstance(self.retired, Unset):
            retired = UNSET
        else:
            retired = self.retired


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if key is not UNSET:
            field_dict["key"] = key
        if retired is not UNSET:
            field_dict["retired"] = retired

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        key = _parse_key(d.pop("key", UNSET))


        def _parse_retired(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        retired = _parse_retired(d.pop("retired", UNSET))


        provider_update_in = cls(
            key=key,
            retired=retired,
        )


        provider_update_in.additional_properties = d
        return provider_update_in

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
