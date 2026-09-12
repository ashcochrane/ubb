from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="AffordabilityResponse")



@_attrs_define
class AffordabilityResponse:
    """ Whether this customer's spending state would let new work proceed.

    ADVISORY, NEVER AUTHORITATIVE. A start (`POST /api/v1/tasks`) re-runs
    every check this answers, under its own locks, so `allowed: true` here
    reserves nothing and a start after it may still be refused. Asking
    registers nothing and consumes none of the customer's admission
    allowance.

    A denial is `allowed: false` with a `reason` from the
    `affordability_reason` vocabulary — an open set, so render a value you
    have not seen rather than fail on it. `balance_micros` is the billing
    owner's wallet balance and `available_micros` is that balance less the
    agreed prices reserved by work already started and not yet ended — the
    figure every floor is tested against. `min_balance_micros` and
    `soft_min_balance_micros` are the hard and soft floors as resolved for
    this customer, in the orientation the billing profile publishes them
    (the allowed overdraft: the line sits at minus the value); the soft
    floor is null where no wind-down line applies to the work asked about —
    contained work under a running parent, a tenant not enforcing, or none
    configured. The two balance figures are null where the answer was made
    before a wallet was read (a standing refusal); the two floors are null
    there too, and for a postpaid tenant, which has no wallet floors.

        Attributes:
            allowed (bool):
            available_micros (int | None | Unset):
            balance_micros (int | None | Unset):
            min_balance_micros (int | None | Unset):
            reason (None | str | Unset):
            soft_min_balance_micros (int | None | Unset):
     """

    allowed: bool
    available_micros: int | None | Unset = UNSET
    balance_micros: int | None | Unset = UNSET
    min_balance_micros: int | None | Unset = UNSET
    reason: None | str | Unset = UNSET
    soft_min_balance_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        allowed = self.allowed

        available_micros: int | None | Unset
        if isinstance(self.available_micros, Unset):
            available_micros = UNSET
        else:
            available_micros = self.available_micros

        balance_micros: int | None | Unset
        if isinstance(self.balance_micros, Unset):
            balance_micros = UNSET
        else:
            balance_micros = self.balance_micros

        min_balance_micros: int | None | Unset
        if isinstance(self.min_balance_micros, Unset):
            min_balance_micros = UNSET
        else:
            min_balance_micros = self.min_balance_micros

        reason: None | str | Unset
        if isinstance(self.reason, Unset):
            reason = UNSET
        else:
            reason = self.reason

        soft_min_balance_micros: int | None | Unset
        if isinstance(self.soft_min_balance_micros, Unset):
            soft_min_balance_micros = UNSET
        else:
            soft_min_balance_micros = self.soft_min_balance_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "allowed": allowed,
        })
        if available_micros is not UNSET:
            field_dict["available_micros"] = available_micros
        if balance_micros is not UNSET:
            field_dict["balance_micros"] = balance_micros
        if min_balance_micros is not UNSET:
            field_dict["min_balance_micros"] = min_balance_micros
        if reason is not UNSET:
            field_dict["reason"] = reason
        if soft_min_balance_micros is not UNSET:
            field_dict["soft_min_balance_micros"] = soft_min_balance_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        allowed = d.pop("allowed")

        def _parse_available_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        available_micros = _parse_available_micros(d.pop("available_micros", UNSET))


        def _parse_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        balance_micros = _parse_balance_micros(d.pop("balance_micros", UNSET))


        def _parse_min_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_balance_micros = _parse_min_balance_micros(d.pop("min_balance_micros", UNSET))


        def _parse_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason = _parse_reason(d.pop("reason", UNSET))


        def _parse_soft_min_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        soft_min_balance_micros = _parse_soft_min_balance_micros(d.pop("soft_min_balance_micros", UNSET))


        affordability_response = cls(
            allowed=allowed,
            available_micros=available_micros,
            balance_micros=balance_micros,
            min_balance_micros=min_balance_micros,
            reason=reason,
            soft_min_balance_micros=soft_min_balance_micros,
        )


        affordability_response.additional_properties = d
        return affordability_response

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
