from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="MeUsageInvoiceOut")



@_attrs_define
class MeUsageInvoiceOut:
    """ 
        Attributes:
            created_at (datetime.datetime):
            id (str):
            total_billed_micros (int):
            hosted_invoice_url (str | Unset):  Default: ''.
            invoice_pdf (str | Unset):  Default: ''.
            payment_status (None | str | Unset):
            period_end (datetime.date | None | Unset):
            period_start (datetime.date | None | Unset):
            stripe_invoice_id (str | Unset):  Default: ''.
     """

    created_at: datetime.datetime
    id: str
    total_billed_micros: int
    hosted_invoice_url: str | Unset = ''
    invoice_pdf: str | Unset = ''
    payment_status: None | str | Unset = UNSET
    period_end: datetime.date | None | Unset = UNSET
    period_start: datetime.date | None | Unset = UNSET
    stripe_invoice_id: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        id = self.id

        total_billed_micros = self.total_billed_micros

        hosted_invoice_url = self.hosted_invoice_url

        invoice_pdf = self.invoice_pdf

        payment_status: None | str | Unset
        if isinstance(self.payment_status, Unset):
            payment_status = UNSET
        else:
            payment_status = self.payment_status

        period_end: None | str | Unset
        if isinstance(self.period_end, Unset):
            period_end = UNSET
        elif isinstance(self.period_end, datetime.date):
            period_end = self.period_end.isoformat()
        else:
            period_end = self.period_end

        period_start: None | str | Unset
        if isinstance(self.period_start, Unset):
            period_start = UNSET
        elif isinstance(self.period_start, datetime.date):
            period_start = self.period_start.isoformat()
        else:
            period_start = self.period_start

        stripe_invoice_id = self.stripe_invoice_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "id": id,
            "total_billed_micros": total_billed_micros,
        })
        if hosted_invoice_url is not UNSET:
            field_dict["hosted_invoice_url"] = hosted_invoice_url
        if invoice_pdf is not UNSET:
            field_dict["invoice_pdf"] = invoice_pdf
        if payment_status is not UNSET:
            field_dict["payment_status"] = payment_status
        if period_end is not UNSET:
            field_dict["period_end"] = period_end
        if period_start is not UNSET:
            field_dict["period_start"] = period_start
        if stripe_invoice_id is not UNSET:
            field_dict["stripe_invoice_id"] = stripe_invoice_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))




        id = d.pop("id")

        total_billed_micros = d.pop("total_billed_micros")

        hosted_invoice_url = d.pop("hosted_invoice_url", UNSET)

        invoice_pdf = d.pop("invoice_pdf", UNSET)

        def _parse_payment_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        payment_status = _parse_payment_status(d.pop("payment_status", UNSET))


        def _parse_period_end(data: object) -> datetime.date | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                period_end_type_0 = datetime.date.fromisoformat(data)



                return period_end_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None | Unset, data)

        period_end = _parse_period_end(d.pop("period_end", UNSET))


        def _parse_period_start(data: object) -> datetime.date | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                period_start_type_0 = datetime.date.fromisoformat(data)



                return period_start_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None | Unset, data)

        period_start = _parse_period_start(d.pop("period_start", UNSET))


        stripe_invoice_id = d.pop("stripe_invoice_id", UNSET)

        me_usage_invoice_out = cls(
            created_at=created_at,
            id=id,
            total_billed_micros=total_billed_micros,
            hosted_invoice_url=hosted_invoice_url,
            invoice_pdf=invoice_pdf,
            payment_status=payment_status,
            period_end=period_end,
            period_start=period_start,
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
