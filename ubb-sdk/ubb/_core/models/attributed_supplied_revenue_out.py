from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.attributed_supplied_revenue_out_recognition_method import AttributedSuppliedRevenueOutRecognitionMethod
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="AttributedSuppliedRevenueOut")



@_attrs_define
class AttributedSuppliedRevenueOut:
    """ One supplied record and what a window gets of it under one basis.

        Attributes:
            amount_micros (int):
            attributed_amount_micros (int):
            currency (str):
            id (str):
            period_start (str):
            recognition_method (AttributedSuppliedRevenueOutRecognitionMethod):
            recorded_at (str):
            source_reference (str):
            period_end (None | str | Unset):
     """

    amount_micros: int
    attributed_amount_micros: int
    currency: str
    id: str
    period_start: str
    recognition_method: AttributedSuppliedRevenueOutRecognitionMethod
    recorded_at: str
    source_reference: str
    period_end: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        attributed_amount_micros = self.attributed_amount_micros

        currency = self.currency

        id = self.id

        period_start = self.period_start

        recognition_method = self.recognition_method.value

        recorded_at = self.recorded_at

        source_reference = self.source_reference

        period_end: None | str | Unset
        if isinstance(self.period_end, Unset):
            period_end = UNSET
        else:
            period_end = self.period_end


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "attributed_amount_micros": attributed_amount_micros,
            "currency": currency,
            "id": id,
            "period_start": period_start,
            "recognition_method": recognition_method,
            "recorded_at": recorded_at,
            "source_reference": source_reference,
        })
        if period_end is not UNSET:
            field_dict["period_end"] = period_end

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_micros = d.pop("amount_micros")

        attributed_amount_micros = d.pop("attributed_amount_micros")

        currency = d.pop("currency")

        id = d.pop("id")

        period_start = d.pop("period_start")

        recognition_method = AttributedSuppliedRevenueOutRecognitionMethod(d.pop("recognition_method"))




        recorded_at = d.pop("recorded_at")

        source_reference = d.pop("source_reference")

        def _parse_period_end(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        period_end = _parse_period_end(d.pop("period_end", UNSET))


        attributed_supplied_revenue_out = cls(
            amount_micros=amount_micros,
            attributed_amount_micros=attributed_amount_micros,
            currency=currency,
            id=id,
            period_start=period_start,
            recognition_method=recognition_method,
            recorded_at=recorded_at,
            source_reference=source_reference,
            period_end=period_end,
        )


        attributed_supplied_revenue_out.additional_properties = d
        return attributed_supplied_revenue_out

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
