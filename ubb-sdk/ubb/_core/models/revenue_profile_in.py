from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RevenueProfileIn")



@_attrs_define
class RevenueProfileIn:
    """ 
        Attributes:
            recurring_amount_micros (int):
            currency (str | Unset):  Default: 'usd'.
            effective_from (None | str | Unset):
            effective_to (None | str | Unset):
            interval (str | Unset):  Default: 'month'.
     """

    recurring_amount_micros: int
    currency: str | Unset = 'usd'
    effective_from: None | str | Unset = UNSET
    effective_to: None | str | Unset = UNSET
    interval: str | Unset = 'month'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        recurring_amount_micros = self.recurring_amount_micros

        currency = self.currency

        effective_from: None | str | Unset
        if isinstance(self.effective_from, Unset):
            effective_from = UNSET
        else:
            effective_from = self.effective_from

        effective_to: None | str | Unset
        if isinstance(self.effective_to, Unset):
            effective_to = UNSET
        else:
            effective_to = self.effective_to

        interval = self.interval


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "recurring_amount_micros": recurring_amount_micros,
        })
        if currency is not UNSET:
            field_dict["currency"] = currency
        if effective_from is not UNSET:
            field_dict["effective_from"] = effective_from
        if effective_to is not UNSET:
            field_dict["effective_to"] = effective_to
        if interval is not UNSET:
            field_dict["interval"] = interval

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        recurring_amount_micros = d.pop("recurring_amount_micros")

        currency = d.pop("currency", UNSET)

        def _parse_effective_from(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        effective_from = _parse_effective_from(d.pop("effective_from", UNSET))


        def _parse_effective_to(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        effective_to = _parse_effective_to(d.pop("effective_to", UNSET))


        interval = d.pop("interval", UNSET)

        revenue_profile_in = cls(
            recurring_amount_micros=recurring_amount_micros,
            currency=currency,
            effective_from=effective_from,
            effective_to=effective_to,
            interval=interval,
        )


        revenue_profile_in.additional_properties = d
        return revenue_profile_in

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
