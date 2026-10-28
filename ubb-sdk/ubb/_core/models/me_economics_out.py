from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.me_economics_out_basis import MeEconomicsOutBasis
from typing import cast

if TYPE_CHECKING:
  from ..models.me_customer_revenue_out import MeCustomerRevenueOut
  from ..models.me_recorded_events_out import MeRecordedEventsOut





T = TypeVar("T", bound="MeEconomicsOut")



@_attrs_define
class MeEconomicsOut:
    """ Your own usage over a window: what it earned, and how many events.

    The window is echoed so a caller who left it to the default can see it.

        Attributes:
            basis (MeEconomicsOutBasis):
            currency (str):
            customer_revenue (MeCustomerRevenueOut): What your usage in the window earned, under the basis the answer names.

                `amount_micros` is null wherever no figure can be stated — no revenue is
                ever shown as zero because it is unknown or unavailable — and `status` says
                which: `known` (every input resolved), `incomplete` (the sum of what
                resolved; some is still being priced), or
                `unavailable_outside_retention_horizon` (the window reaches back past what
                UBB still holds; `available_from` says from when it can start).
            foreign_currency_subscription_count (int): How many of your subscriptions the revenue above leaves out because
                they are billed in a currency UBB does not admit. Where it is not 0, your revenue is higher by an amount UBB
                cannot state; 0 where nothing was left out.
            period_end (str): The last calendar date (UTC) in the window, inclusive.
            period_start (str): The first calendar date (UTC) in the window, inclusive.
            recorded_events (MeRecordedEventsOut): How many metered usage events you recorded in the window.

                `status` is `known`, or `unavailable_outside_retention_horizon` where the
                window reaches back past what UBB still holds (`available_from` says
                from when it can start) — `count` is then null, never a zero.
     """

    basis: MeEconomicsOutBasis
    currency: str
    customer_revenue: MeCustomerRevenueOut
    foreign_currency_subscription_count: int
    period_end: str
    period_start: str
    recorded_events: MeRecordedEventsOut
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.me_customer_revenue_out import MeCustomerRevenueOut
        from ..models.me_recorded_events_out import MeRecordedEventsOut
        basis = self.basis.value

        currency = self.currency

        customer_revenue = self.customer_revenue.to_dict()

        foreign_currency_subscription_count = self.foreign_currency_subscription_count

        period_end = self.period_end

        period_start = self.period_start

        recorded_events = self.recorded_events.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "basis": basis,
            "currency": currency,
            "customer_revenue": customer_revenue,
            "foreign_currency_subscription_count": foreign_currency_subscription_count,
            "period_end": period_end,
            "period_start": period_start,
            "recorded_events": recorded_events,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.me_customer_revenue_out import MeCustomerRevenueOut
        from ..models.me_recorded_events_out import MeRecordedEventsOut
        d = dict(src_dict)
        basis = MeEconomicsOutBasis(d.pop("basis"))




        currency = d.pop("currency")

        customer_revenue = MeCustomerRevenueOut.from_dict(d.pop("customer_revenue"))




        foreign_currency_subscription_count = d.pop("foreign_currency_subscription_count")

        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        recorded_events = MeRecordedEventsOut.from_dict(d.pop("recorded_events"))




        me_economics_out = cls(
            basis=basis,
            currency=currency,
            customer_revenue=customer_revenue,
            foreign_currency_subscription_count=foreign_currency_subscription_count,
            period_end=period_end,
            period_start=period_start,
            recorded_events=recorded_events,
        )


        me_economics_out.additional_properties = d
        return me_economics_out

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
