from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TenantUsageInvoiceOut")



@_attrs_define
class TenantUsageInvoiceOut:
    """ 
        Attributes:
            customer_id (str):
            external_id (str):
            period_start (str):
            status (str):
            total_billed_micros (int):
            last_attempt_error (None | str | Unset):
            push_attempts (int | None | Unset):
            skip_reason (str | Unset):  Default: ''.
            stripe_invoice_id (str | Unset):  Default: ''.
     """

    customer_id: str
    external_id: str
    period_start: str
    status: str
    total_billed_micros: int
    last_attempt_error: None | str | Unset = UNSET
    push_attempts: int | None | Unset = UNSET
    skip_reason: str | Unset = ''
    stripe_invoice_id: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        customer_id = self.customer_id

        external_id = self.external_id

        period_start = self.period_start

        status = self.status

        total_billed_micros = self.total_billed_micros

        last_attempt_error: None | str | Unset
        if isinstance(self.last_attempt_error, Unset):
            last_attempt_error = UNSET
        else:
            last_attempt_error = self.last_attempt_error

        push_attempts: int | None | Unset
        if isinstance(self.push_attempts, Unset):
            push_attempts = UNSET
        else:
            push_attempts = self.push_attempts

        skip_reason = self.skip_reason

        stripe_invoice_id = self.stripe_invoice_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_id": customer_id,
            "external_id": external_id,
            "period_start": period_start,
            "status": status,
            "total_billed_micros": total_billed_micros,
        })
        if last_attempt_error is not UNSET:
            field_dict["last_attempt_error"] = last_attempt_error
        if push_attempts is not UNSET:
            field_dict["push_attempts"] = push_attempts
        if skip_reason is not UNSET:
            field_dict["skip_reason"] = skip_reason
        if stripe_invoice_id is not UNSET:
            field_dict["stripe_invoice_id"] = stripe_invoice_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        customer_id = d.pop("customer_id")

        external_id = d.pop("external_id")

        period_start = d.pop("period_start")

        status = d.pop("status")

        total_billed_micros = d.pop("total_billed_micros")

        def _parse_last_attempt_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_attempt_error = _parse_last_attempt_error(d.pop("last_attempt_error", UNSET))


        def _parse_push_attempts(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        push_attempts = _parse_push_attempts(d.pop("push_attempts", UNSET))


        skip_reason = d.pop("skip_reason", UNSET)

        stripe_invoice_id = d.pop("stripe_invoice_id", UNSET)

        tenant_usage_invoice_out = cls(
            customer_id=customer_id,
            external_id=external_id,
            period_start=period_start,
            status=status,
            total_billed_micros=total_billed_micros,
            last_attempt_error=last_attempt_error,
            push_attempts=push_attempts,
            skip_reason=skip_reason,
            stripe_invoice_id=stripe_invoice_id,
        )


        tenant_usage_invoice_out.additional_properties = d
        return tenant_usage_invoice_out

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
