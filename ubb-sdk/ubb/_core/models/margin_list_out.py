from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.customer_margin_list_row import CustomerMarginListRow
  from ..models.period_window import PeriodWindow





T = TypeVar("T", bound="MarginListOut")



@_attrs_define
class MarginListOut:
    """ 
        Attributes:
            customers (list[CustomerMarginListRow]):
            period (PeriodWindow):
     """

    customers: list[CustomerMarginListRow]
    period: PeriodWindow
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.customer_margin_list_row import CustomerMarginListRow
        from ..models.period_window import PeriodWindow
        customers = []
        for customers_item_data in self.customers:
            customers_item = customers_item_data.to_dict()
            customers.append(customers_item)



        period = self.period.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customers": customers,
            "period": period,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.customer_margin_list_row import CustomerMarginListRow
        from ..models.period_window import PeriodWindow
        d = dict(src_dict)
        customers = []
        _customers = d.pop("customers")
        for customers_item_data in (_customers):
            customers_item = CustomerMarginListRow.from_dict(customers_item_data)



            customers.append(customers_item)


        period = PeriodWindow.from_dict(d.pop("period"))




        margin_list_out = cls(
            customers=customers,
            period=period,
        )


        margin_list_out.additional_properties = d
        return margin_list_out

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
