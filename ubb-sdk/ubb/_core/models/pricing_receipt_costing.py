from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pricing_receipt_costing_method_type_0 import PricingReceiptCostingMethodType0
from ..models.pricing_receipt_costing_status import PricingReceiptCostingStatus
from typing import cast

if TYPE_CHECKING:
  from ..models.pricing_receipt_costing_detail import PricingReceiptCostingDetail





T = TypeVar("T", bound="PricingReceiptCosting")



@_attrs_define
class PricingReceiptCosting:
    """ The supplier side: how the cost was derived (null where no method
    derived it), whether it is settled, and the detail that explains it.

        Attributes:
            detail (PricingReceiptCostingDetail): Why the supplier cost is what it is. Absent keys stay absent: a Task
                Charge's receipt holds none, because no supplier stands behind a Charge.
            method (None | PricingReceiptCostingMethodType0):
            status (PricingReceiptCostingStatus):
     """

    detail: PricingReceiptCostingDetail
    method: None | PricingReceiptCostingMethodType0
    status: PricingReceiptCostingStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pricing_receipt_costing_detail import PricingReceiptCostingDetail
        detail = self.detail.to_dict()

        method: None | str
        if isinstance(self.method, PricingReceiptCostingMethodType0):
            method = self.method.value
        else:
            method = self.method

        status = self.status.value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "detail": detail,
            "method": method,
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pricing_receipt_costing_detail import PricingReceiptCostingDetail
        d = dict(src_dict)
        detail = PricingReceiptCostingDetail.from_dict(d.pop("detail"))




        def _parse_method(data: object) -> None | PricingReceiptCostingMethodType0:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                method_type_0 = PricingReceiptCostingMethodType0(data)



                return method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptCostingMethodType0, data)

        method = _parse_method(d.pop("method"))


        status = PricingReceiptCostingStatus(d.pop("status"))




        pricing_receipt_costing = cls(
            detail=detail,
            method=method,
            status=status,
        )


        pricing_receipt_costing.additional_properties = d
        return pricing_receipt_costing

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
