from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TenantDefaultMarkupOut")



@_attrs_define
class TenantDefaultMarkupOut:
    """ What the tenant has declared, or that they have declared nothing.

    ⚠ **NULL MEANS NO RUNG, AND IT IS NOT A ZERO.** The two are different facts
    and reading one as the other is how a customer gets billed exactly what a
    call cost with nobody having decided that: a declared zero says *charge
    cost* and settles, and an absent declaration resolves to `unknown` with no
    amount at all. One nullable field rather than a percentage beside a
    `declared` flag, because two fields encoding one fact is two fields that can
    disagree.

        Attributes:
            markup_micro_percent (int | None | Unset):
     """

    markup_micro_percent: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        markup_micro_percent: int | None | Unset
        if isinstance(self.markup_micro_percent, Unset):
            markup_micro_percent = UNSET
        else:
            markup_micro_percent = self.markup_micro_percent


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if markup_micro_percent is not UNSET:
            field_dict["markup_micro_percent"] = markup_micro_percent

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_markup_micro_percent(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        markup_micro_percent = _parse_markup_micro_percent(d.pop("markup_micro_percent", UNSET))


        tenant_default_markup_out = cls(
            markup_micro_percent=markup_micro_percent,
        )


        tenant_default_markup_out.additional_properties = d
        return tenant_default_markup_out

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
