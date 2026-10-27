from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.debit_request_movement_reason_type_0 import DebitRequestMovementReasonType0
from ..types import UNSET, Unset
from typing import cast






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
            movement_reason (DebitRequestMovementReasonType0 | None | Unset): Why this money moved by hand — one of the
                registry's movement reasons. Optional: omit it, or send null, to record none. Stored on the wallet transaction
                for the audit trail.
     """

    amount_micros: int
    customer_id: str
    idempotency_key: str
    reference: str
    actor: str | Unset = ''
    allow_negative: bool | Unset = False
    movement_reason: DebitRequestMovementReasonType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        customer_id = self.customer_id

        idempotency_key = self.idempotency_key

        reference = self.reference

        actor = self.actor

        allow_negative = self.allow_negative

        movement_reason: None | str | Unset
        if isinstance(self.movement_reason, Unset):
            movement_reason = UNSET
        elif isinstance(self.movement_reason, DebitRequestMovementReasonType0):
            movement_reason = self.movement_reason.value
        else:
            movement_reason = self.movement_reason


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
        if movement_reason is not UNSET:
            field_dict["movement_reason"] = movement_reason

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

        def _parse_movement_reason(data: object) -> DebitRequestMovementReasonType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                movement_reason_type_0 = DebitRequestMovementReasonType0(data)



                return movement_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DebitRequestMovementReasonType0 | None | Unset, data)

        movement_reason = _parse_movement_reason(d.pop("movement_reason", UNSET))


        debit_request = cls(
            amount_micros=amount_micros,
            customer_id=customer_id,
            idempotency_key=idempotency_key,
            reference=reference,
            actor=actor,
            allow_negative=allow_negative,
            movement_reason=movement_reason,
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
