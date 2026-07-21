from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.rate_in_dimensions import RateInDimensions





T = TypeVar("T", bound="RateIn")



@_attrs_define
class RateIn:
    """ A single Rate added under a book. card_type and currency are inherited
    from the book, so they are NOT accepted here (the book owns them).

        Attributes:
            metric_name (str):
            dimensions (RateInDimensions | Unset):
            event_type (str | Unset):  Default: ''.
            fixed_micros (int | Unset):  Default: 0.
            pricing_model (str | Unset):  Default: 'per_unit'.
            product_id (str | Unset):  Default: ''.
            provider (str | Unset):  Default: ''.
            rate_per_unit_micros (int | Unset):  Default: 0.
            unit_quantity (int | Unset):  Default: 1000000.
     """

    metric_name: str
    dimensions: RateInDimensions | Unset = UNSET
    event_type: str | Unset = ''
    fixed_micros: int | Unset = 0
    pricing_model: str | Unset = 'per_unit'
    product_id: str | Unset = ''
    provider: str | Unset = ''
    rate_per_unit_micros: int | Unset = 0
    unit_quantity: int | Unset = 1000000
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.rate_in_dimensions import RateInDimensions
        metric_name = self.metric_name

        dimensions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.dimensions, Unset):
            dimensions = self.dimensions.to_dict()

        event_type = self.event_type

        fixed_micros = self.fixed_micros

        pricing_model = self.pricing_model

        product_id = self.product_id

        provider = self.provider

        rate_per_unit_micros = self.rate_per_unit_micros

        unit_quantity = self.unit_quantity


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "metric_name": metric_name,
        })
        if dimensions is not UNSET:
            field_dict["dimensions"] = dimensions
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if fixed_micros is not UNSET:
            field_dict["fixed_micros"] = fixed_micros
        if pricing_model is not UNSET:
            field_dict["pricing_model"] = pricing_model
        if product_id is not UNSET:
            field_dict["product_id"] = product_id
        if provider is not UNSET:
            field_dict["provider"] = provider
        if rate_per_unit_micros is not UNSET:
            field_dict["rate_per_unit_micros"] = rate_per_unit_micros
        if unit_quantity is not UNSET:
            field_dict["unit_quantity"] = unit_quantity

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rate_in_dimensions import RateInDimensions
        d = dict(src_dict)
        metric_name = d.pop("metric_name")

        _dimensions = d.pop("dimensions", UNSET)
        dimensions: RateInDimensions | Unset
        if isinstance(_dimensions,  Unset):
            dimensions = UNSET
        else:
            dimensions = RateInDimensions.from_dict(_dimensions)




        event_type = d.pop("event_type", UNSET)

        fixed_micros = d.pop("fixed_micros", UNSET)

        pricing_model = d.pop("pricing_model", UNSET)

        product_id = d.pop("product_id", UNSET)

        provider = d.pop("provider", UNSET)

        rate_per_unit_micros = d.pop("rate_per_unit_micros", UNSET)

        unit_quantity = d.pop("unit_quantity", UNSET)

        rate_in = cls(
            metric_name=metric_name,
            dimensions=dimensions,
            event_type=event_type,
            fixed_micros=fixed_micros,
            pricing_model=pricing_model,
            product_id=product_id,
            provider=provider,
            rate_per_unit_micros=rate_per_unit_micros,
            unit_quantity=unit_quantity,
        )


        rate_in.additional_properties = d
        return rate_in

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
