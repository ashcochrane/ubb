from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="DebitRequest")



@_attrs_define
class DebitRequest:
    """ 
        Attributes:
            amount_micros (int):
            customer_id (str):
            idempotency_key (str):
            reference (str):
            actor (str | Unset):  Default: ''.
            allow_negative (bool | Unset):  Default: False.
            reason_code (str | Unset):  Default: ''.
     """

    amount_micros: int
    customer_id: str
    idempotency_key: str
    reference: str
    actor: str | Unset = ''
    allow_negative: bool | Unset = False
    reason_code: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        customer_id = self.customer_id

        idempotency_key = self.idempotency_key

        reference = self.reference

        actor = self.actor

        allow_negative = self.allow_negative

        reason_code = self.reason_code


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "customer_id": customer_id,
            "idempotency_key": idempotency_key,
            "reference": reference,
        })
        if actor is not UNSET:
            field_dict["actor"] = actor
        if allow_negative is not UNSET:
            field_dict["allow_negative"] = allow_negative
        if reason_code is not UNSET:
            field_dict["reason_code"] = reason_code

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_micros = d.pop("amount_micros")

        customer_id = d.pop("customer_id")

        idempotency_key = d.pop("idempotency_key")

        reference = d.pop("reference")

        actor = d.pop("actor", UNSET)

        allow_negative = d.pop("allow_negative", UNSET)

        reason_code = d.pop("reason_code", UNSET)

        debit_request = cls(
            amount_micros=amount_micros,
            customer_id=customer_id,
            idempotency_key=idempotency_key,
            reference=reference,
            actor=actor,
            allow_negative=allow_negative,
            reason_code=reason_code,
        )


        debit_request.additional_properties = d
        return debit_request

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
