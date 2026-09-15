from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.supplied_revenue_window_out_basis import SuppliedRevenueWindowOutBasis
from ..models.supplied_revenue_window_out_pricing_status import SuppliedRevenueWindowOutPricingStatus
from typing import cast

if TYPE_CHECKING:
  from ..models.attributed_supplied_revenue_out import AttributedSuppliedRevenueOut
  from ..models.period_window import PeriodWindow
  from ..models.supplied_revenue_total_out import SuppliedRevenueTotalOut





T = TypeVar("T", bound="SuppliedRevenueWindowOut")



@_attrs_define
class SuppliedRevenueWindowOut:
    """ The window's supplied revenue, under a basis the response NAMES (#495).

    **The totals are a list per currency and never a single figure**, because a
    single figure summed across currencies is a wrong number, and this slice's
    whole subject is revenue figures that say what they are. The normal answer
    is a one-element list; a customer whose supplied records are denominated
    two ways gets two entries rather than a total that is true of neither.

    **An empty list is how `unknown` is served, and it is never a zero.** A
    tenant that has supplied nothing for this window has revenue UBB does not
    know — margin is unavailable there, not nil — and a `0` here would be the
    silent-zero #153 §3.4 refuses by name.

        Attributes:
            basis (SuppliedRevenueWindowOutBasis):
            pricing_status (SuppliedRevenueWindowOutPricingStatus):
            records (list[AttributedSuppliedRevenueOut]):
            totals (list[SuppliedRevenueTotalOut]):
            window (PeriodWindow):
     """

    basis: SuppliedRevenueWindowOutBasis
    pricing_status: SuppliedRevenueWindowOutPricingStatus
    records: list[AttributedSuppliedRevenueOut]
    totals: list[SuppliedRevenueTotalOut]
    window: PeriodWindow
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.attributed_supplied_revenue_out import AttributedSuppliedRevenueOut
        from ..models.period_window import PeriodWindow
        from ..models.supplied_revenue_total_out import SuppliedRevenueTotalOut
        basis = self.basis.value

        pricing_status = self.pricing_status.value

        records = []
        for records_item_data in self.records:
            records_item = records_item_data.to_dict()
            records.append(records_item)



        totals = []
        for totals_item_data in self.totals:
            totals_item = totals_item_data.to_dict()
            totals.append(totals_item)



        window = self.window.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "basis": basis,
            "pricing_status": pricing_status,
            "records": records,
            "totals": totals,
            "window": window,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.attributed_supplied_revenue_out import AttributedSuppliedRevenueOut
        from ..models.period_window import PeriodWindow
        from ..models.supplied_revenue_total_out import SuppliedRevenueTotalOut
        d = dict(src_dict)
        basis = SuppliedRevenueWindowOutBasis(d.pop("basis"))




        pricing_status = SuppliedRevenueWindowOutPricingStatus(d.pop("pricing_status"))




        records = []
        _records = d.pop("records")
        for records_item_data in (_records):
            records_item = AttributedSuppliedRevenueOut.from_dict(records_item_data)



            records.append(records_item)


        totals = []
        _totals = d.pop("totals")
        for totals_item_data in (_totals):
            totals_item = SuppliedRevenueTotalOut.from_dict(totals_item_data)



            totals.append(totals_item)


        window = PeriodWindow.from_dict(d.pop("window"))




        supplied_revenue_window_out = cls(
            basis=basis,
            pricing_status=pricing_status,
            records=records,
            totals=totals,
            window=window,
        )


        supplied_revenue_window_out.additional_properties = d
        return supplied_revenue_window_out

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
