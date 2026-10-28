from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pricing_receipt_pricing_detail_not_applicable_reason_type_0 import PricingReceiptPricingDetailNotApplicableReasonType0
from ..models.pricing_receipt_pricing_detail_pricing_mode_type_0 import PricingReceiptPricingDetailPricingModeType0
from ..models.pricing_receipt_pricing_detail_pricing_status_reason_type_0 import PricingReceiptPricingDetailPricingStatusReasonType0
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.pricing_receipt_component import PricingReceiptComponent
  from ..models.pricing_receipt_markup_terms import PricingReceiptMarkupTerms





T = TypeVar("T", bound="PricingReceiptPricingDetail")



@_attrs_define
class PricingReceiptPricingDetail:
    """ Why the customer price is what it is — the regime the subject was
    priced under, and the reason beside a status that needs one.

        Attributes:
            components (list[PricingReceiptComponent] | None | Unset):
            markup (None | PricingReceiptMarkupTerms | Unset):
            not_applicable_reason (None | PricingReceiptPricingDetailNotApplicableReasonType0 | Unset):
            pricing_mode (None | PricingReceiptPricingDetailPricingModeType0 | Unset):
            pricing_status_reason (None | PricingReceiptPricingDetailPricingStatusReasonType0 | Unset):
     """

    components: list[PricingReceiptComponent] | None | Unset = UNSET
    markup: None | PricingReceiptMarkupTerms | Unset = UNSET
    not_applicable_reason: None | PricingReceiptPricingDetailNotApplicableReasonType0 | Unset = UNSET
    pricing_mode: None | PricingReceiptPricingDetailPricingModeType0 | Unset = UNSET
    pricing_status_reason: None | PricingReceiptPricingDetailPricingStatusReasonType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pricing_receipt_component import PricingReceiptComponent
        from ..models.pricing_receipt_markup_terms import PricingReceiptMarkupTerms
        components: list[dict[str, Any]] | None | Unset
        if isinstance(self.components, Unset):
            components = UNSET
        elif isinstance(self.components, list):
            components = []
            for components_type_0_item_data in self.components:
                components_type_0_item = components_type_0_item_data.to_dict()
                components.append(components_type_0_item)


        else:
            components = self.components

        markup: dict[str, Any] | None | Unset
        if isinstance(self.markup, Unset):
            markup = UNSET
        elif isinstance(self.markup, PricingReceiptMarkupTerms):
            markup = self.markup.to_dict()
        else:
            markup = self.markup

        not_applicable_reason: None | str | Unset
        if isinstance(self.not_applicable_reason, Unset):
            not_applicable_reason = UNSET
        elif isinstance(self.not_applicable_reason, PricingReceiptPricingDetailNotApplicableReasonType0):
            not_applicable_reason = self.not_applicable_reason.value
        else:
            not_applicable_reason = self.not_applicable_reason

        pricing_mode: None | str | Unset
        if isinstance(self.pricing_mode, Unset):
            pricing_mode = UNSET
        elif isinstance(self.pricing_mode, PricingReceiptPricingDetailPricingModeType0):
            pricing_mode = self.pricing_mode.value
        else:
            pricing_mode = self.pricing_mode

        pricing_status_reason: None | str | Unset
        if isinstance(self.pricing_status_reason, Unset):
            pricing_status_reason = UNSET
        elif isinstance(self.pricing_status_reason, PricingReceiptPricingDetailPricingStatusReasonType0):
            pricing_status_reason = self.pricing_status_reason.value
        else:
            pricing_status_reason = self.pricing_status_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if components is not UNSET:
            field_dict["components"] = components
        if markup is not UNSET:
            field_dict["markup"] = markup
        if not_applicable_reason is not UNSET:
            field_dict["not_applicable_reason"] = not_applicable_reason
        if pricing_mode is not UNSET:
            field_dict["pricing_mode"] = pricing_mode
        if pricing_status_reason is not UNSET:
            field_dict["pricing_status_reason"] = pricing_status_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pricing_receipt_component import PricingReceiptComponent
        from ..models.pricing_receipt_markup_terms import PricingReceiptMarkupTerms
        d = dict(src_dict)
        def _parse_components(data: object) -> list[PricingReceiptComponent] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                components_type_0 = []
                _components_type_0 = data
                for components_type_0_item_data in (_components_type_0):
                    components_type_0_item = PricingReceiptComponent.from_dict(components_type_0_item_data)



                    components_type_0.append(components_type_0_item)

                return components_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[PricingReceiptComponent] | None | Unset, data)

        components = _parse_components(d.pop("components", UNSET))


        def _parse_markup(data: object) -> None | PricingReceiptMarkupTerms | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                markup_type_0 = PricingReceiptMarkupTerms.from_dict(data)



                return markup_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptMarkupTerms | Unset, data)

        markup = _parse_markup(d.pop("markup", UNSET))


        def _parse_not_applicable_reason(data: object) -> None | PricingReceiptPricingDetailNotApplicableReasonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                not_applicable_reason_type_0 = PricingReceiptPricingDetailNotApplicableReasonType0(data)



                return not_applicable_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptPricingDetailNotApplicableReasonType0 | Unset, data)

        not_applicable_reason = _parse_not_applicable_reason(d.pop("not_applicable_reason", UNSET))


        def _parse_pricing_mode(data: object) -> None | PricingReceiptPricingDetailPricingModeType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_mode_type_0 = PricingReceiptPricingDetailPricingModeType0(data)



                return pricing_mode_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptPricingDetailPricingModeType0 | Unset, data)

        pricing_mode = _parse_pricing_mode(d.pop("pricing_mode", UNSET))


        def _parse_pricing_status_reason(data: object) -> None | PricingReceiptPricingDetailPricingStatusReasonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_status_reason_type_0 = PricingReceiptPricingDetailPricingStatusReasonType0(data)



                return pricing_status_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptPricingDetailPricingStatusReasonType0 | Unset, data)

        pricing_status_reason = _parse_pricing_status_reason(d.pop("pricing_status_reason", UNSET))


        pricing_receipt_pricing_detail = cls(
            components=components,
            markup=markup,
            not_applicable_reason=not_applicable_reason,
            pricing_mode=pricing_mode,
            pricing_status_reason=pricing_status_reason,
        )


        pricing_receipt_pricing_detail.additional_properties = d
        return pricing_receipt_pricing_detail

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
