from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="SubscriptionInvoiceOut")



@_attrs_define
class SubscriptionInvoiceOut:
    """ 
        Attributes:
            amount_paid_micros (int):
            currency (str):
            id (str):
            paid_at (str):
            period_end (str):
            period_start (str):
            stripe_invoice_id (str):
     """

    amount_paid_micros: int
    currency: str
    id: str
    paid_at: str
    period_end: str
    period_start: str
    stripe_invoice_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_paid_micros = self.amount_paid_micros

        currency = self.currency

        id = self.id

        paid_at = self.paid_at

        period_end = self.period_end

        period_start = self.period_start

        stripe_invoice_id = self.stripe_invoice_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_paid_micros": amount_paid_micros,
            "currency": currency,
            "id": id,
            "paid_at": paid_at,
            "period_end": period_end,
            "period_start": period_start,
            "stripe_invoice_id": stripe_invoice_id,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_paid_micros = d.pop("amount_paid_micros")

        currency = d.pop("currency")

        id = d.pop("id")

        paid_at = d.pop("paid_at")

        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        stripe_invoice_id = d.pop("stripe_invoice_id")

        subscription_invoice_out = cls(
            amount_paid_micros=amount_paid_micros,
            currency=currency,
            id=id,
            paid_at=paid_at,
            period_end=period_end,
            period_start=period_start,
            stripe_invoice_id=stripe_invoice_id,
        )


        subscription_invoice_out.additional_properties = d
        return subscription_invoice_out

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
