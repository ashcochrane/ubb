from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pricing_receipt_subject_type import PricingReceiptSubjectType
from typing import cast

if TYPE_CHECKING:
  from ..models.pricing_receipt_costing import PricingReceiptCosting
  from ..models.pricing_receipt_pricing import PricingReceiptPricing
  from ..models.pricing_receipt_provenance import PricingReceiptProvenance
  from ..models.pricing_receipt_totals import PricingReceiptTotals





T = TypeVar("T", bound="PricingReceipt")



@_attrs_define
class PricingReceipt:
    """ The Pricing Receipt, version 2 — see `RECEIPT_DESCRIPTION`.

        Attributes:
            costing (PricingReceiptCosting): The supplier side: how the cost was derived (null where no method
                derived it), whether it is settled, and the detail that explains it.
            currency (str):
            effective_at (str):
            pricing (PricingReceiptPricing): The customer side, on the cost side's terms.
            pricing_engine_version (str):
            provenance (PricingReceiptProvenance): Cross-reference ids and nothing else (`receipts._validate_provenance`
                refuses a figure here). Absent keys stay absent: a usage event names the
                rules it read, a Charge names its agreed price line, and a completion names
                the Resolution Run or the held name that completed it (#363, #568).
            receipt_schema_version (int):
            subject_id (str):
            subject_type (PricingReceiptSubjectType):
            totals (PricingReceiptTotals): The amount each section resolved; null where it is not settled.
     """

    costing: PricingReceiptCosting
    currency: str
    effective_at: str
    pricing: PricingReceiptPricing
    pricing_engine_version: str
    provenance: PricingReceiptProvenance
    receipt_schema_version: int
    subject_id: str
    subject_type: PricingReceiptSubjectType
    totals: PricingReceiptTotals
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pricing_receipt_costing import PricingReceiptCosting
        from ..models.pricing_receipt_pricing import PricingReceiptPricing
        from ..models.pricing_receipt_provenance import PricingReceiptProvenance
        from ..models.pricing_receipt_totals import PricingReceiptTotals
        costing = self.costing.to_dict()

        currency = self.currency

        effective_at = self.effective_at

        pricing = self.pricing.to_dict()

        pricing_engine_version = self.pricing_engine_version

        provenance = self.provenance.to_dict()

        receipt_schema_version = self.receipt_schema_version

        subject_id = self.subject_id

        subject_type = self.subject_type.value

        totals = self.totals.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "costing": costing,
            "currency": currency,
            "effective_at": effective_at,
            "pricing": pricing,
            "pricing_engine_version": pricing_engine_version,
            "provenance": provenance,
            "receipt_schema_version": receipt_schema_version,
            "subject_id": subject_id,
            "subject_type": subject_type,
            "totals": totals,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pricing_receipt_costing import PricingReceiptCosting
        from ..models.pricing_receipt_pricing import PricingReceiptPricing
        from ..models.pricing_receipt_provenance import PricingReceiptProvenance
        from ..models.pricing_receipt_totals import PricingReceiptTotals
        d = dict(src_dict)
        costing = PricingReceiptCosting.from_dict(d.pop("costing"))




        currency = d.pop("currency")

        effective_at = d.pop("effective_at")

        pricing = PricingReceiptPricing.from_dict(d.pop("pricing"))




        pricing_engine_version = d.pop("pricing_engine_version")

        provenance = PricingReceiptProvenance.from_dict(d.pop("provenance"))




        receipt_schema_version = d.pop("receipt_schema_version")

        subject_id = d.pop("subject_id")

        subject_type = PricingReceiptSubjectType(d.pop("subject_type"))




        totals = PricingReceiptTotals.from_dict(d.pop("totals"))




        pricing_receipt = cls(
            costing=costing,
            currency=currency,
            effective_at=effective_at,
            pricing=pricing,
            pricing_engine_version=pricing_engine_version,
            provenance=provenance,
            receipt_schema_version=receipt_schema_version,
            subject_id=subject_id,
            subject_type=subject_type,
            totals=totals,
        )


        pricing_receipt.additional_properties = d
        return pricing_receipt

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
