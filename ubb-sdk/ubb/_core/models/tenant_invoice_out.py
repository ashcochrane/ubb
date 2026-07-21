from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="TenantInvoiceOut")



@_attrs_define
class TenantInvoiceOut:
    """ 
        Attributes:
            billing_period_id (str):
            created_at (str):
            id (str):
            status (str):
            stripe_invoice_id (str):
            total_amount_micros (int):
     """

    billing_period_id: str
    created_at: str
    id: str
    status: str
    stripe_invoice_id: str
    total_amount_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        billing_period_id = self.billing_period_id

        created_at = self.created_at

        id = self.id

        status = self.status

        stripe_invoice_id = self.stripe_invoice_id

        total_amount_micros = self.total_amount_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billing_period_id": billing_period_id,
            "created_at": created_at,
            "id": id,
            "status": status,
            "stripe_invoice_id": stripe_invoice_id,
            "total_amount_micros": total_amount_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        billing_period_id = d.pop("billing_period_id")

        created_at = d.pop("created_at")

        id = d.pop("id")

        status = d.pop("status")

        stripe_invoice_id = d.pop("stripe_invoice_id")

        total_amount_micros = d.pop("total_amount_micros")

        tenant_invoice_out = cls(
            billing_period_id=billing_period_id,
            created_at=created_at,
            id=id,
            status=status,
            stripe_invoice_id=stripe_invoice_id,
            total_amount_micros=total_amount_micros,
        )


        tenant_invoice_out.additional_properties = d
        return tenant_invoice_out

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
