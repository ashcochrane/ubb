from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RevenueProfileOut")



@_attrs_define
class RevenueProfileOut:
    """ 
        Attributes:
            currency (str):
            effective_from (str):
            interval (str):
            recurring_amount_micros (int):
            effective_to (None | str | Unset):
     """

    currency: str
    effective_from: str
    interval: str
    recurring_amount_micros: int
    effective_to: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        currency = self.currency

        effective_from = self.effective_from

        interval = self.interval

        recurring_amount_micros = self.recurring_amount_micros

        effective_to: None | str | Unset
        if isinstance(self.effective_to, Unset):
            effective_to = UNSET
        else:
            effective_to = self.effective_to


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "currency": currency,
            "effective_from": effective_from,
            "interval": interval,
            "recurring_amount_micros": recurring_amount_micros,
        })
        if effective_to is not UNSET:
            field_dict["effective_to"] = effective_to

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        currency = d.pop("currency")

        effective_from = d.pop("effective_from")

        interval = d.pop("interval")

        recurring_amount_micros = d.pop("recurring_amount_micros")

        def _parse_effective_to(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        effective_to = _parse_effective_to(d.pop("effective_to", UNSET))


        revenue_profile_out = cls(
            currency=currency,
            effective_from=effective_from,
            interval=interval,
            recurring_amount_micros=recurring_amount_micros,
            effective_to=effective_to,
        )


        revenue_profile_out.additional_properties = d
        return revenue_profile_out

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
