from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.me_customer_revenue_out_status import MeCustomerRevenueOutStatus
from typing import cast






T = TypeVar("T", bound="MeCustomerRevenueOut")



@_attrs_define
class MeCustomerRevenueOut:
    """ What your usage in the window earned, under the basis the answer names.

    `amount_micros` is null wherever no figure can be stated — no revenue is
    ever shown as zero because it is unknown or unavailable — and `status` says
    which: `known` (every input resolved), `incomplete` (the sum of what
    resolved; some is still being priced), or
    `unavailable_outside_retention_horizon` (the window reaches back past what
    UBB still holds; `available_from` says from when it can start).

        Attributes:
            amount_micros (int | None): The revenue in micros of the answer's currency, or null where no figure can be
                stated — never a zero standing in.
            available_from (None | str): The first day this figure can be stated from, non-null exactly where `status` is
                `unavailable_outside_retention_horizon`.
            status (MeCustomerRevenueOutStatus):
     """

    amount_micros: int | None
    available_from: None | str
    status: MeCustomerRevenueOutStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros: int | None
        amount_micros = self.amount_micros

        available_from: None | str
        available_from = self.available_from

        status = self.status.value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "available_from": available_from,
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_amount_micros(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        amount_micros = _parse_amount_micros(d.pop("amount_micros"))


        def _parse_available_from(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        available_from = _parse_available_from(d.pop("available_from"))


        status = MeCustomerRevenueOutStatus(d.pop("status"))




        me_customer_revenue_out = cls(
            amount_micros=amount_micros,
            available_from=available_from,
            status=status,
        )


        me_customer_revenue_out.additional_properties = d
        return me_customer_revenue_out

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
