from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.usage_invoice_out_skip_reason_type_0 import UsageInvoiceOutSkipReasonType0
from ..models.usage_invoice_out_status import UsageInvoiceOutStatus
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="UsageInvoiceOut")



@_attrs_define
class UsageInvoiceOut:
    """ 
        Attributes:
            currency (str):
            period_end (str):
            period_start (str):
            skip_reason (None | UsageInvoiceOutSkipReasonType0): Why this invoice was skipped rather than pushed; null
                unless status is 'skipped'.
            status (UsageInvoiceOutStatus):
            total_billed_micros (int):
            last_attempt_error (None | str | Unset):
            push_attempts (int | None | Unset):
            stripe_invoice_id (str | Unset):  Default: ''.
     """

    currency: str
    period_end: str
    period_start: str
    skip_reason: None | UsageInvoiceOutSkipReasonType0
    status: UsageInvoiceOutStatus
    total_billed_micros: int
    last_attempt_error: None | str | Unset = UNSET
    push_attempts: int | None | Unset = UNSET
    stripe_invoice_id: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        currency = self.currency

        period_end = self.period_end

        period_start = self.period_start

        skip_reason: None | str
        if isinstance(self.skip_reason, UsageInvoiceOutSkipReasonType0):
            skip_reason = self.skip_reason.value
        else:
            skip_reason = self.skip_reason

        status = self.status.value

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

        stripe_invoice_id = self.stripe_invoice_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "currency": currency,
            "period_end": period_end,
            "period_start": period_start,
            "skip_reason": skip_reason,
            "status": status,
            "total_billed_micros": total_billed_micros,
        })
        if last_attempt_error is not UNSET:
            field_dict["last_attempt_error"] = last_attempt_error
        if push_attempts is not UNSET:
            field_dict["push_attempts"] = push_attempts
        if stripe_invoice_id is not UNSET:
            field_dict["stripe_invoice_id"] = stripe_invoice_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        currency = d.pop("currency")

        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        def _parse_skip_reason(data: object) -> None | UsageInvoiceOutSkipReasonType0:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                skip_reason_type_0 = UsageInvoiceOutSkipReasonType0(data)



                return skip_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UsageInvoiceOutSkipReasonType0, data)

        skip_reason = _parse_skip_reason(d.pop("skip_reason"))


        status = UsageInvoiceOutStatus(d.pop("status"))




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


        stripe_invoice_id = d.pop("stripe_invoice_id", UNSET)

        usage_invoice_out = cls(
            currency=currency,
            period_end=period_end,
            period_start=period_start,
            skip_reason=skip_reason,
            status=status,
            total_billed_micros=total_billed_micros,
            last_attempt_error=last_attempt_error,
            push_attempts=push_attempts,
            stripe_invoice_id=stripe_invoice_id,
        )


        usage_invoice_out.additional_properties = d
        return usage_invoice_out

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
