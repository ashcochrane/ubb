from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pricing_receipt_costing_detail_reported_cost_source_kind_type_0 import PricingReceiptCostingDetailReportedCostSourceKindType0
from ..models.pricing_receipt_costing_detail_unresolved_reason_type_0 import PricingReceiptCostingDetailUnresolvedReasonType0
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.pricing_receipt_component import PricingReceiptComponent
  from ..models.pricing_receipt_costing_detail_uncosted_quantities_type_0 import PricingReceiptCostingDetailUncostedQuantitiesType0
  from ..models.pricing_receipt_costing_detail_undeclared_quantities_type_0 import PricingReceiptCostingDetailUndeclaredQuantitiesType0





T = TypeVar("T", bound="PricingReceiptCostingDetail")



@_attrs_define
class PricingReceiptCostingDetail:
    """ Why the supplier cost is what it is. Absent keys stay absent: a Task
    Charge's receipt holds none, because no supplier stands behind a Charge.

        Attributes:
            components (list[PricingReceiptComponent] | None | Unset):
            reported_cost_source_kind (None | PricingReceiptCostingDetailReportedCostSourceKindType0 | Unset):
            uncosted_measurement_keys (list[str] | None | Unset):
            uncosted_quantities (None | PricingReceiptCostingDetailUncostedQuantitiesType0 | Unset):
            undeclared_quantities (None | PricingReceiptCostingDetailUndeclaredQuantitiesType0 | Unset):
            unresolved_reason (None | PricingReceiptCostingDetailUnresolvedReasonType0 | Unset):
     """

    components: list[PricingReceiptComponent] | None | Unset = UNSET
    reported_cost_source_kind: None | PricingReceiptCostingDetailReportedCostSourceKindType0 | Unset = UNSET
    uncosted_measurement_keys: list[str] | None | Unset = UNSET
    uncosted_quantities: None | PricingReceiptCostingDetailUncostedQuantitiesType0 | Unset = UNSET
    undeclared_quantities: None | PricingReceiptCostingDetailUndeclaredQuantitiesType0 | Unset = UNSET
    unresolved_reason: None | PricingReceiptCostingDetailUnresolvedReasonType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pricing_receipt_component import PricingReceiptComponent
        from ..models.pricing_receipt_costing_detail_uncosted_quantities_type_0 import PricingReceiptCostingDetailUncostedQuantitiesType0
        from ..models.pricing_receipt_costing_detail_undeclared_quantities_type_0 import PricingReceiptCostingDetailUndeclaredQuantitiesType0
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

        reported_cost_source_kind: None | str | Unset
        if isinstance(self.reported_cost_source_kind, Unset):
            reported_cost_source_kind = UNSET
        elif isinstance(self.reported_cost_source_kind, PricingReceiptCostingDetailReportedCostSourceKindType0):
            reported_cost_source_kind = self.reported_cost_source_kind.value
        else:
            reported_cost_source_kind = self.reported_cost_source_kind

        uncosted_measurement_keys: list[str] | None | Unset
        if isinstance(self.uncosted_measurement_keys, Unset):
            uncosted_measurement_keys = UNSET
        elif isinstance(self.uncosted_measurement_keys, list):
            uncosted_measurement_keys = self.uncosted_measurement_keys


        else:
            uncosted_measurement_keys = self.uncosted_measurement_keys

        uncosted_quantities: dict[str, Any] | None | Unset
        if isinstance(self.uncosted_quantities, Unset):
            uncosted_quantities = UNSET
        elif isinstance(self.uncosted_quantities, PricingReceiptCostingDetailUncostedQuantitiesType0):
            uncosted_quantities = self.uncosted_quantities.to_dict()
        else:
            uncosted_quantities = self.uncosted_quantities

        undeclared_quantities: dict[str, Any] | None | Unset
        if isinstance(self.undeclared_quantities, Unset):
            undeclared_quantities = UNSET
        elif isinstance(self.undeclared_quantities, PricingReceiptCostingDetailUndeclaredQuantitiesType0):
            undeclared_quantities = self.undeclared_quantities.to_dict()
        else:
            undeclared_quantities = self.undeclared_quantities

        unresolved_reason: None | str | Unset
        if isinstance(self.unresolved_reason, Unset):
            unresolved_reason = UNSET
        elif isinstance(self.unresolved_reason, PricingReceiptCostingDetailUnresolvedReasonType0):
            unresolved_reason = self.unresolved_reason.value
        else:
            unresolved_reason = self.unresolved_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if components is not UNSET:
            field_dict["components"] = components
        if reported_cost_source_kind is not UNSET:
            field_dict["reported_cost_source_kind"] = reported_cost_source_kind
        if uncosted_measurement_keys is not UNSET:
            field_dict["uncosted_measurement_keys"] = uncosted_measurement_keys
        if uncosted_quantities is not UNSET:
            field_dict["uncosted_quantities"] = uncosted_quantities
        if undeclared_quantities is not UNSET:
            field_dict["undeclared_quantities"] = undeclared_quantities
        if unresolved_reason is not UNSET:
            field_dict["unresolved_reason"] = unresolved_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pricing_receipt_component import PricingReceiptComponent
        from ..models.pricing_receipt_costing_detail_uncosted_quantities_type_0 import PricingReceiptCostingDetailUncostedQuantitiesType0
        from ..models.pricing_receipt_costing_detail_undeclared_quantities_type_0 import PricingReceiptCostingDetailUndeclaredQuantitiesType0
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


        def _parse_reported_cost_source_kind(data: object) -> None | PricingReceiptCostingDetailReportedCostSourceKindType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                reported_cost_source_kind_type_0 = PricingReceiptCostingDetailReportedCostSourceKindType0(data)



                return reported_cost_source_kind_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptCostingDetailReportedCostSourceKindType0 | Unset, data)

        reported_cost_source_kind = _parse_reported_cost_source_kind(d.pop("reported_cost_source_kind", UNSET))


        def _parse_uncosted_measurement_keys(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                uncosted_measurement_keys_type_0 = cast(list[str], data)

                return uncosted_measurement_keys_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        uncosted_measurement_keys = _parse_uncosted_measurement_keys(d.pop("uncosted_measurement_keys", UNSET))


        def _parse_uncosted_quantities(data: object) -> None | PricingReceiptCostingDetailUncostedQuantitiesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                uncosted_quantities_type_0 = PricingReceiptCostingDetailUncostedQuantitiesType0.from_dict(data)



                return uncosted_quantities_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptCostingDetailUncostedQuantitiesType0 | Unset, data)

        uncosted_quantities = _parse_uncosted_quantities(d.pop("uncosted_quantities", UNSET))


        def _parse_undeclared_quantities(data: object) -> None | PricingReceiptCostingDetailUndeclaredQuantitiesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                undeclared_quantities_type_0 = PricingReceiptCostingDetailUndeclaredQuantitiesType0.from_dict(data)



                return undeclared_quantities_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptCostingDetailUndeclaredQuantitiesType0 | Unset, data)

        undeclared_quantities = _parse_undeclared_quantities(d.pop("undeclared_quantities", UNSET))


        def _parse_unresolved_reason(data: object) -> None | PricingReceiptCostingDetailUnresolvedReasonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                unresolved_reason_type_0 = PricingReceiptCostingDetailUnresolvedReasonType0(data)



                return unresolved_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptCostingDetailUnresolvedReasonType0 | Unset, data)

        unresolved_reason = _parse_unresolved_reason(d.pop("unresolved_reason", UNSET))


        pricing_receipt_costing_detail = cls(
            components=components,
            reported_cost_source_kind=reported_cost_source_kind,
            uncosted_measurement_keys=uncosted_measurement_keys,
            uncosted_quantities=uncosted_quantities,
            undeclared_quantities=undeclared_quantities,
            unresolved_reason=unresolved_reason,
        )


        pricing_receipt_costing_detail.additional_properties = d
        return pricing_receipt_costing_detail

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
