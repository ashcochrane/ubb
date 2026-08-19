from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="TenantDefaultMarkupIn")



@_attrs_define
class TenantDefaultMarkupIn:
    """ The tenant's default markup rung, as the tenant declares it (#357).

    ⚠ **REQUIRED, WITH NO DEFAULT, WHICH IS THE WHOLE POINT.** UBB ships no
    catalogue: there is no starter percentage anywhere, and a tenant that has
    declared nothing has no markup rung at all. A default of zero here would let
    a caller declare a rung by accident, and a rung of zero is a decision — it
    says *charge my customer exactly what the call cost* — so it has to be
    stated.

    **ONE TERM, BECAUSE A MARGIN NEVER COMPOSES** (#147 §2). No floor, no cap
    and no flat addend beside the percentage: a resolved price is explicable by
    naming one thing, and a chain whose middle terms are on no record is what
    that rule exists to prevent.

        Attributes:
            markup_micro_percent (int):
     """

    markup_micro_percent: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        markup_micro_percent = self.markup_micro_percent


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "markup_micro_percent": markup_micro_percent,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        markup_micro_percent = d.pop("markup_micro_percent")

        tenant_default_markup_in = cls(
            markup_micro_percent=markup_micro_percent,
        )


        tenant_default_markup_in.additional_properties = d
        return tenant_default_markup_in

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
