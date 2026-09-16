from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="RevenueContextOut")



@_attrs_define
class RevenueContextOut:
    """ Revenue that exists and could not be placed at the requested grouping.

    ⚠ **IT IS HERE PRECISELY SO THAT NO MARGIN CAN BE DRAWN OVER IT SILENTLY.**
    A subscription and a figure a tenant supplied are statements about a
    customer over a period; neither names a supplier, an event type or an event,
    so spreading one across an operational axis would invent a boundary the
    record never asserted. Rather than distribute it, bucket it as unattributed
    or drop it, the query states it here with the axes at which asking again
    WOULD produce a margin.

        Attributes:
            amount_micros (int):
            attributable_axes (list[str]):
            attributable_bucket (str): The finest time grain this money can honestly be placed at — 'hour', 'day' or
                'month'. A question bucketed more finely than this cannot attribute it, because the record behind it declares no
                finer a span.
            customer_id (str):
            source (str): Where a revenue figure came from: 'subscription' for a Stripe subscription UBB mirrors,
                'tenant_supplied' for a figure the tenant recorded itself. They are kept apart so a reader of a revenue number
                can say which kind of money it is.
            window_end (str):
            window_start (str):
     """

    amount_micros: int
    attributable_axes: list[str]
    attributable_bucket: str
    customer_id: str
    source: str
    window_end: str
    window_start: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        attributable_axes = self.attributable_axes



        attributable_bucket = self.attributable_bucket

        customer_id = self.customer_id

        source = self.source

        window_end = self.window_end

        window_start = self.window_start


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "attributable_axes": attributable_axes,
            "attributable_bucket": attributable_bucket,
            "customer_id": customer_id,
            "source": source,
            "window_end": window_end,
            "window_start": window_start,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_micros = d.pop("amount_micros")

        attributable_axes = cast(list[str], d.pop("attributable_axes"))


        attributable_bucket = d.pop("attributable_bucket")

        customer_id = d.pop("customer_id")

        source = d.pop("source")

        window_end = d.pop("window_end")

        window_start = d.pop("window_start")

        revenue_context_out = cls(
            amount_micros=amount_micros,
            attributable_axes=attributable_axes,
            attributable_bucket=attributable_bucket,
            customer_id=customer_id,
            source=source,
            window_end=window_end,
            window_start=window_start,
        )


        revenue_context_out.additional_properties = d
        return revenue_context_out

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
