from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="CreateGrantRequest")



@_attrs_define
class CreateGrantRequest:
    """ 
        Attributes:
            amount_micros (int):
            idempotency_key (str):
            kind (str):
            description (str | Unset):  Default: ''.
            expires_at (datetime.datetime | None | Unset):
            expires_in_days (int | None | Unset):
     """

    amount_micros: int
    idempotency_key: str
    kind: str
    description: str | Unset = ''
    expires_at: datetime.datetime | None | Unset = UNSET
    expires_in_days: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        idempotency_key = self.idempotency_key

        kind = self.kind

        description = self.description

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        elif isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        expires_in_days: int | None | Unset
        if isinstance(self.expires_in_days, Unset):
            expires_in_days = UNSET
        else:
            expires_in_days = self.expires_in_days


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "idempotency_key": idempotency_key,
            "kind": kind,
        })
        if description is not UNSET:
            field_dict["description"] = description
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at
        if expires_in_days is not UNSET:
            field_dict["expires_in_days"] = expires_in_days

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_micros = d.pop("amount_micros")

        idempotency_key = d.pop("idempotency_key")

        kind = d.pop("kind")

        description = d.pop("description", UNSET)

        def _parse_expires_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                expires_at_type_0 = datetime.datetime.fromisoformat(data)



                return expires_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))


        def _parse_expires_in_days(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        expires_in_days = _parse_expires_in_days(d.pop("expires_in_days", UNSET))


        create_grant_request = cls(
            amount_micros=amount_micros,
            idempotency_key=idempotency_key,
            kind=kind,
            description=description,
            expires_at=expires_at,
            expires_in_days=expires_in_days,
        )


        create_grant_request.additional_properties = d
        return create_grant_request

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
