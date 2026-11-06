from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.me_usage_invoice_out_payment_status_type_0 import MeUsageInvoiceOutPaymentStatusType0
from ..models.me_usage_invoice_out_skip_reason_type_0 import MeUsageInvoiceOutSkipReasonType0
from ..models.me_usage_invoice_out_status import MeUsageInvoiceOutStatus
from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="MeUsageInvoiceOut")



@_attrs_define
class MeUsageInvoiceOut:
    """ The end customer's own usage invoice: exactly the one shared base
    (R10 Stage C5, F-15) — never the operator's push internals
    (`push_attempts`, `last_attempt_error`), which the tenant's two routes
    add and this one does not.

        Attributes:
            created_at (datetime.datetime):
            currency (str):
            customer_id (str): The platform UUID of the customer the invoice is for — the billing owner's own invoice.
            external_id (str): That customer's tenant-side external id.
            id (str):
            period_end (datetime.date):
            period_start (datetime.date):
            skip_reason (MeUsageInvoiceOutSkipReasonType0 | None): Why this invoice was skipped rather than pushed; null
                unless status is 'skipped'.
            status (MeUsageInvoiceOutStatus):
            total_billed_micros (int):
            hosted_invoice_url (str | Unset): Stripe's hosted invoice page; empty until the invoice exists. Default: ''.
            invoice_pdf (str | Unset): Stripe's invoice PDF; empty until the invoice exists. Default: ''.
            paid_at (datetime.datetime | None | Unset): When Stripe reported the invoice paid; null until then.
            payment_failed_at (datetime.datetime | None | Unset): When the last payment attempt failed and the invoice began
                to stand as a payment failure against its billing owner; null while none stands (cleared once the invoice is
                paid or voided).
            payment_status (MeUsageInvoiceOutPaymentStatusType0 | None | Unset): Where the Stripe invoice behind a pushed
                usage invoice stands as a receivable: open, paid, void or uncollectible. Null while the invoice is not yet
                collectible — no Stripe invoice has been issued for it, or none has reported a status yet; null is that meaning,
                not a fifth value.
            pushed_at (datetime.datetime | None | Unset): When the period was pushed to Stripe; null until it was.
            stripe_invoice_id (str | Unset): The Stripe invoice the period was pushed to; empty until it was. Default: ''.
     """

    created_at: datetime.datetime
    currency: str
    customer_id: str
    external_id: str
    id: str
    period_end: datetime.date
    period_start: datetime.date
    skip_reason: MeUsageInvoiceOutSkipReasonType0 | None
    status: MeUsageInvoiceOutStatus
    total_billed_micros: int
    hosted_invoice_url: str | Unset = ''
    invoice_pdf: str | Unset = ''
    paid_at: datetime.datetime | None | Unset = UNSET
    payment_failed_at: datetime.datetime | None | Unset = UNSET
    payment_status: MeUsageInvoiceOutPaymentStatusType0 | None | Unset = UNSET
    pushed_at: datetime.datetime | None | Unset = UNSET
    stripe_invoice_id: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        currency = self.currency

        customer_id = self.customer_id

        external_id = self.external_id

        id = self.id

        period_end = self.period_end.isoformat()

        period_start = self.period_start.isoformat()

        skip_reason: None | str
        if isinstance(self.skip_reason, MeUsageInvoiceOutSkipReasonType0):
            skip_reason = self.skip_reason.value
        else:
            skip_reason = self.skip_reason

        status = self.status.value

        total_billed_micros = self.total_billed_micros

        hosted_invoice_url = self.hosted_invoice_url

        invoice_pdf = self.invoice_pdf

        paid_at: None | str | Unset
        if isinstance(self.paid_at, Unset):
            paid_at = UNSET
        elif isinstance(self.paid_at, datetime.datetime):
            paid_at = self.paid_at.isoformat()
        else:
            paid_at = self.paid_at

        payment_failed_at: None | str | Unset
        if isinstance(self.payment_failed_at, Unset):
            payment_failed_at = UNSET
        elif isinstance(self.payment_failed_at, datetime.datetime):
            payment_failed_at = self.payment_failed_at.isoformat()
        else:
            payment_failed_at = self.payment_failed_at

        payment_status: None | str | Unset
        if isinstance(self.payment_status, Unset):
            payment_status = UNSET
        elif isinstance(self.payment_status, MeUsageInvoiceOutPaymentStatusType0):
            payment_status = self.payment_status.value
        else:
            payment_status = self.payment_status

        pushed_at: None | str | Unset
        if isinstance(self.pushed_at, Unset):
            pushed_at = UNSET
        elif isinstance(self.pushed_at, datetime.datetime):
            pushed_at = self.pushed_at.isoformat()
        else:
            pushed_at = self.pushed_at

        stripe_invoice_id = self.stripe_invoice_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "currency": currency,
            "customer_id": customer_id,
            "external_id": external_id,
            "id": id,
            "period_end": period_end,
            "period_start": period_start,
            "skip_reason": skip_reason,
            "status": status,
            "total_billed_micros": total_billed_micros,
        })
        if hosted_invoice_url is not UNSET:
            field_dict["hosted_invoice_url"] = hosted_invoice_url
        if invoice_pdf is not UNSET:
            field_dict["invoice_pdf"] = invoice_pdf
        if paid_at is not UNSET:
            field_dict["paid_at"] = paid_at
        if payment_failed_at is not UNSET:
            field_dict["payment_failed_at"] = payment_failed_at
        if payment_status is not UNSET:
            field_dict["payment_status"] = payment_status
        if pushed_at is not UNSET:
            field_dict["pushed_at"] = pushed_at
        if stripe_invoice_id is not UNSET:
            field_dict["stripe_invoice_id"] = stripe_invoice_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        currency = d.pop("currency")

        customer_id = d.pop("customer_id")

        external_id = d.pop("external_id")

        id = d.pop("id")

        period_end = datetime.date.fromisoformat(d.pop("period_end"))




        period_start = datetime.date.fromisoformat(d.pop("period_start"))




        def _parse_skip_reason(data: object) -> MeUsageInvoiceOutSkipReasonType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                skip_reason_type_0 = MeUsageInvoiceOutSkipReasonType0(data)



                return skip_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MeUsageInvoiceOutSkipReasonType0 | None, data)

        skip_reason = _parse_skip_reason(d.pop("skip_reason"))


        status = MeUsageInvoiceOutStatus(d.pop("status"))




        total_billed_micros = d.pop("total_billed_micros")

        hosted_invoice_url = d.pop("hosted_invoice_url", UNSET)

        invoice_pdf = d.pop("invoice_pdf", UNSET)

        def _parse_paid_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                paid_at_type_0 = datetime.datetime.fromisoformat(data)



                return paid_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        paid_at = _parse_paid_at(d.pop("paid_at", UNSET))


        def _parse_payment_failed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                payment_failed_at_type_0 = datetime.datetime.fromisoformat(data)



                return payment_failed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        payment_failed_at = _parse_payment_failed_at(d.pop("payment_failed_at", UNSET))


        def _parse_payment_status(data: object) -> MeUsageInvoiceOutPaymentStatusType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                payment_status_type_0 = MeUsageInvoiceOutPaymentStatusType0(data)



                return payment_status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MeUsageInvoiceOutPaymentStatusType0 | None | Unset, data)

        payment_status = _parse_payment_status(d.pop("payment_status", UNSET))


        def _parse_pushed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pushed_at_type_0 = datetime.datetime.fromisoformat(data)



                return pushed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        pushed_at = _parse_pushed_at(d.pop("pushed_at", UNSET))


        stripe_invoice_id = d.pop("stripe_invoice_id", UNSET)

        me_usage_invoice_out = cls(
            created_at=created_at,
            currency=currency,
            customer_id=customer_id,
            external_id=external_id,
            id=id,
            period_end=period_end,
            period_start=period_start,
            skip_reason=skip_reason,
            status=status,
            total_billed_micros=total_billed_micros,
            hosted_invoice_url=hosted_invoice_url,
            invoice_pdf=invoice_pdf,
            paid_at=paid_at,
            payment_failed_at=payment_failed_at,
            payment_status=payment_status,
            pushed_at=pushed_at,
            stripe_invoice_id=stripe_invoice_id,
        )


        me_usage_invoice_out.additional_properties = d
        return me_usage_invoice_out

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
