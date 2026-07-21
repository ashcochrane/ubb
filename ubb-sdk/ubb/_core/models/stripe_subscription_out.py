from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="StripeSubscriptionOut")



@_attrs_define
class StripeSubscriptionOut:
    """ 
        Attributes:
            amount_micros (int):
            currency (str):
            current_period_end (str):
            current_period_start (str):
            id (str):
            interval (str):
            last_synced_at (str):
            status (str):
            stripe_product_name (str):
            stripe_subscription_id (str):
     """

    amount_micros: int
    currency: str
    current_period_end: str
    current_period_start: str
    id: str
    interval: str
    last_synced_at: str
    status: str
    stripe_product_name: str
    stripe_subscription_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_micros = self.amount_micros

        currency = self.currency

        current_period_end = self.current_period_end

        current_period_start = self.current_period_start

        id = self.id

        interval = self.interval

        last_synced_at = self.last_synced_at

        status = self.status

        stripe_product_name = self.stripe_product_name

        stripe_subscription_id = self.stripe_subscription_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_micros": amount_micros,
            "currency": currency,
            "current_period_end": current_period_end,
            "current_period_start": current_period_start,
            "id": id,
            "interval": interval,
            "last_synced_at": last_synced_at,
            "status": status,
            "stripe_product_name": stripe_product_name,
            "stripe_subscription_id": stripe_subscription_id,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_micros = d.pop("amount_micros")

        currency = d.pop("currency")

        current_period_end = d.pop("current_period_end")

        current_period_start = d.pop("current_period_start")

        id = d.pop("id")

        interval = d.pop("interval")

        last_synced_at = d.pop("last_synced_at")

        status = d.pop("status")

        stripe_product_name = d.pop("stripe_product_name")

        stripe_subscription_id = d.pop("stripe_subscription_id")

        stripe_subscription_out = cls(
            amount_micros=amount_micros,
            currency=currency,
            current_period_end=current_period_end,
            current_period_start=current_period_start,
            id=id,
            interval=interval,
            last_synced_at=last_synced_at,
            status=status,
            stripe_product_name=stripe_product_name,
            stripe_subscription_id=stripe_subscription_id,
        )


        stripe_subscription_out.additional_properties = d
        return stripe_subscription_out

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
