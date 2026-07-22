from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID






T = TypeVar("T", bound="WalletTransactionOut")



@_attrs_define
class WalletTransactionOut:
    """ 
        Attributes:
            amount_micros (int):
            balance_after_micros (int):
            created_at (str):
            description (str):
            id (UUID):
            transaction_type (str):
            reference_id (None | str | Unset):
     """

    amount_micros: int
    balance_after_micros: int
    created_at: str
    description: str
    id: UUID
    transaction_type: str
    reference_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        balance_after_micros = self.balance_after_micros

        created_at = self.created_at

        description = self.description

        id = str(self.id)

        transaction_type = self.transaction_type

        reference_id: None | str | Unset
        if isinstance(self.reference_id, Unset):
            reference_id = UNSET
        else:
            reference_id = self.reference_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "balance_after_micros": balance_after_micros,
            "created_at": created_at,
            "description": description,
            "id": id,
            "transaction_type": transaction_type,
        })
        if reference_id is not UNSET:
            field_dict["reference_id"] = reference_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_micros = d.pop("amount_micros")

        balance_after_micros = d.pop("balance_after_micros")

        created_at = d.pop("created_at")

        description = d.pop("description")

        id = UUID(d.pop("id"))




        transaction_type = d.pop("transaction_type")

        def _parse_reference_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reference_id = _parse_reference_id(d.pop("reference_id", UNSET))


        wallet_transaction_out = cls(
            amount_micros=amount_micros,
            balance_after_micros=balance_after_micros,
            created_at=created_at,
            description=description,
            id=id,
            transaction_type=transaction_type,
            reference_id=reference_id,
        )


        wallet_transaction_out.additional_properties = d
        return wallet_transaction_out

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
