from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="GrantOut")



@_attrs_define
class GrantOut:
    """ 
        Attributes:
            created_at (str):
            currency (str):
            expired_micros (int):
            granted_micros (int):
            id (str):
            kind (str):
            remaining_micros (int):
            source (str):
            status (str):
            voided_micros (int):
            balance_micros (int | None | Unset):
            expires_at (None | str | Unset):
            transaction_id (None | str | Unset):
            warning_sent_at (None | str | Unset):
     """

    created_at: str
    currency: str
    expired_micros: int
    granted_micros: int
    id: str
    kind: str
    remaining_micros: int
    source: str
    status: str
    voided_micros: int
    balance_micros: int | None | Unset = UNSET
    expires_at: None | str | Unset = UNSET
    transaction_id: None | str | Unset = UNSET
    warning_sent_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        currency = self.currency

        expired_micros = self.expired_micros

        granted_micros = self.granted_micros

        id = self.id

        kind = self.kind

        remaining_micros = self.remaining_micros

        source = self.source

        status = self.status

        voided_micros = self.voided_micros

        balance_micros: int | None | Unset
        if isinstance(self.balance_micros, Unset):
            balance_micros = UNSET
        else:
            balance_micros = self.balance_micros

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        else:
            expires_at = self.expires_at

        transaction_id: None | str | Unset
        if isinstance(self.transaction_id, Unset):
            transaction_id = UNSET
        else:
            transaction_id = self.transaction_id

        warning_sent_at: None | str | Unset
        if isinstance(self.warning_sent_at, Unset):
            warning_sent_at = UNSET
        else:
            warning_sent_at = self.warning_sent_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "currency": currency,
            "expired_micros": expired_micros,
            "granted_micros": granted_micros,
            "id": id,
            "kind": kind,
            "remaining_micros": remaining_micros,
            "source": source,
            "status": status,
            "voided_micros": voided_micros,
        })
        if balance_micros is not UNSET:
            field_dict["balance_micros"] = balance_micros
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at
        if transaction_id is not UNSET:
            field_dict["transaction_id"] = transaction_id
        if warning_sent_at is not UNSET:
            field_dict["warning_sent_at"] = warning_sent_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        currency = d.pop("currency")

        expired_micros = d.pop("expired_micros")

        granted_micros = d.pop("granted_micros")

        id = d.pop("id")

        kind = d.pop("kind")

        remaining_micros = d.pop("remaining_micros")

        source = d.pop("source")

        status = d.pop("status")

        voided_micros = d.pop("voided_micros")

        def _parse_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        balance_micros = _parse_balance_micros(d.pop("balance_micros", UNSET))


        def _parse_expires_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))


        def _parse_transaction_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        transaction_id = _parse_transaction_id(d.pop("transaction_id", UNSET))


        def _parse_warning_sent_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        warning_sent_at = _parse_warning_sent_at(d.pop("warning_sent_at", UNSET))


        grant_out = cls(
            created_at=created_at,
            currency=currency,
            expired_micros=expired_micros,
            granted_micros=granted_micros,
            id=id,
            kind=kind,
            remaining_micros=remaining_micros,
            source=source,
            status=status,
            voided_micros=voided_micros,
            balance_micros=balance_micros,
            expires_at=expires_at,
            transaction_id=transaction_id,
            warning_sent_at=warning_sent_at,
        )


        grant_out.additional_properties = d
        return grant_out

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
