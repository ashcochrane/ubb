from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pricing_receipt_pricing_method_type_0 import PricingReceiptPricingMethodType0
from ..models.pricing_receipt_pricing_status import PricingReceiptPricingStatus
from typing import cast

if TYPE_CHECKING:
  from ..models.pricing_receipt_pricing_detail import PricingReceiptPricingDetail





T = TypeVar("T", bound="PricingReceiptPricing")



@_attrs_define
class PricingReceiptPricing:
    """ The customer side, on the cost side's terms.

        Attributes:
            detail (PricingReceiptPricingDetail): Why the customer price is what it is — the regime the subject was
                priced under, and the reason beside a status that needs one.
            method (None | PricingReceiptPricingMethodType0):
            status (PricingReceiptPricingStatus):
     """

    detail: PricingReceiptPricingDetail
    method: None | PricingReceiptPricingMethodType0
    status: PricingReceiptPricingStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pricing_receipt_pricing_detail import PricingReceiptPricingDetail
        detail = self.detail.to_dict()

        method: None | str
        if isinstance(self.method, PricingReceiptPricingMethodType0):
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
        from ..models.pricing_receipt_pricing_detail import PricingReceiptPricingDetail
        d = dict(src_dict)
        detail = PricingReceiptPricingDetail.from_dict(d.pop("detail"))




        def _parse_method(data: object) -> None | PricingReceiptPricingMethodType0:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                method_type_0 = PricingReceiptPricingMethodType0(data)



                return method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptPricingMethodType0, data)

        method = _parse_method(d.pop("method"))


        status = PricingReceiptPricingStatus(d.pop("status"))




        pricing_receipt_pricing = cls(
            detail=detail,
            method=method,
            status=status,
        )


        pricing_receipt_pricing.additional_properties = d
        return pricing_receipt_pricing

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
