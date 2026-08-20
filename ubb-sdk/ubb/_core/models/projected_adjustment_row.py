from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="ProjectedAdjustmentRow")



@_attrs_define
class ProjectedAdjustmentRow:
    """ What recovering this filter would be worth for one customer.

        Attributes:
            currency (str):
            customer_id (str):
            projected_billed_cost_micros (int):
            recoverable_event_count (int):
            unpriced_event_count (int):
            usage_event_ids (list[str]):
     """

    currency: str
    customer_id: str
    projected_billed_cost_micros: int
    recoverable_event_count: int
    unpriced_event_count: int
    usage_event_ids: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        currency = self.currency

        customer_id = self.customer_id

        projected_billed_cost_micros = self.projected_billed_cost_micros

        recoverable_event_count = self.recoverable_event_count

        unpriced_event_count = self.unpriced_event_count

        usage_event_ids = self.usage_event_ids




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "currency": currency,
            "customer_id": customer_id,
            "projected_billed_cost_micros": projected_billed_cost_micros,
            "recoverable_event_count": recoverable_event_count,
            "unpriced_event_count": unpriced_event_count,
            "usage_event_ids": usage_event_ids,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        currency = d.pop("currency")

        customer_id = d.pop("customer_id")

        projected_billed_cost_micros = d.pop("projected_billed_cost_micros")

        recoverable_event_count = d.pop("recoverable_event_count")

        unpriced_event_count = d.pop("unpriced_event_count")

        usage_event_ids = cast(list[str], d.pop("usage_event_ids"))


        projected_adjustment_row = cls(
            currency=currency,
            customer_id=customer_id,
            projected_billed_cost_micros=projected_billed_cost_micros,
            recoverable_event_count=recoverable_event_count,
            unpriced_event_count=unpriced_event_count,
            usage_event_ids=usage_event_ids,
        )


        projected_adjustment_row.additional_properties = d
        return projected_adjustment_row

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
