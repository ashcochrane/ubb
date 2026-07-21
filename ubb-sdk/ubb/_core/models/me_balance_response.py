from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="MeBalanceResponse")



@_attrs_define
class MeBalanceResponse:
    """ 
        Attributes:
            balance_micros (int):
            currency (str):
            expiring_micros (int | None | Unset):
            next_expiry_at (None | str | Unset):
            promo_micros (int | None | Unset):
     """

    balance_micros: int
    currency: str
    expiring_micros: int | None | Unset = UNSET
    next_expiry_at: None | str | Unset = UNSET
    promo_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        balance_micros = self.balance_micros

        currency = self.currency

        expiring_micros: int | None | Unset
        if isinstance(self.expiring_micros, Unset):
            expiring_micros = UNSET
        else:
            expiring_micros = self.expiring_micros

        next_expiry_at: None | str | Unset
        if isinstance(self.next_expiry_at, Unset):
            next_expiry_at = UNSET
        else:
            next_expiry_at = self.next_expiry_at

        promo_micros: int | None | Unset
        if isinstance(self.promo_micros, Unset):
            promo_micros = UNSET
        else:
            promo_micros = self.promo_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "balance_micros": balance_micros,
            "currency": currency,
        })
        if expiring_micros is not UNSET:
            field_dict["expiring_micros"] = expiring_micros
        if next_expiry_at is not UNSET:
            field_dict["next_expiry_at"] = next_expiry_at
        if promo_micros is not UNSET:
            field_dict["promo_micros"] = promo_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        balance_micros = d.pop("balance_micros")

        currency = d.pop("currency")

        def _parse_expiring_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        expiring_micros = _parse_expiring_micros(d.pop("expiring_micros", UNSET))


        def _parse_next_expiry_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        next_expiry_at = _parse_next_expiry_at(d.pop("next_expiry_at", UNSET))


        def _parse_promo_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        promo_micros = _parse_promo_micros(d.pop("promo_micros", UNSET))


        me_balance_response = cls(
            balance_micros=balance_micros,
            currency=currency,
            expiring_micros=expiring_micros,
            next_expiry_at=next_expiry_at,
            promo_micros=promo_micros,
        )


        me_balance_response.additional_properties = d
        return me_balance_response

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
