from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.rate_change_in_dimensions import RateChangeInDimensions





T = TypeVar("T", bound="RateChangeIn")



@_attrs_define
class RateChangeIn:
    """ One reprice in a publish. Match keys (metric_name/provider/event_type/
    dimensions) locate the active rate; the remaining (nullable) fields, when
    present, override it in the new version.

        Attributes:
            metric_name (str):
            dimensions (RateChangeInDimensions | Unset):
            event_type (str | Unset):  Default: ''.
            fixed_micros (int | None | Unset):
            pricing_model (None | str | Unset):
            provider (str | Unset):  Default: ''.
            rate_per_unit_micros (int | None | Unset):
            unit_quantity (int | None | Unset):
     """

    metric_name: str
    dimensions: RateChangeInDimensions | Unset = UNSET
    event_type: str | Unset = ''
    fixed_micros: int | None | Unset = UNSET
    pricing_model: None | str | Unset = UNSET
    provider: str | Unset = ''
    rate_per_unit_micros: int | None | Unset = UNSET
    unit_quantity: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.rate_change_in_dimensions import RateChangeInDimensions
        metric_name = self.metric_name

        dimensions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.dimensions, Unset):
            dimensions = self.dimensions.to_dict()

        event_type = self.event_type

        fixed_micros: int | None | Unset
        if isinstance(self.fixed_micros, Unset):
            fixed_micros = UNSET
        else:
            fixed_micros = self.fixed_micros

        pricing_model: None | str | Unset
        if isinstance(self.pricing_model, Unset):
            pricing_model = UNSET
        else:
            pricing_model = self.pricing_model

        provider = self.provider

        rate_per_unit_micros: int | None | Unset
        if isinstance(self.rate_per_unit_micros, Unset):
            rate_per_unit_micros = UNSET
        else:
            rate_per_unit_micros = self.rate_per_unit_micros

        unit_quantity: int | None | Unset
        if isinstance(self.unit_quantity, Unset):
            unit_quantity = UNSET
        else:
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
        if provider is not UNSET:
            field_dict["provider"] = provider
        if rate_per_unit_micros is not UNSET:
            field_dict["rate_per_unit_micros"] = rate_per_unit_micros
        if unit_quantity is not UNSET:
            field_dict["unit_quantity"] = unit_quantity

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rate_change_in_dimensions import RateChangeInDimensions
        d = dict(src_dict)
        metric_name = d.pop("metric_name")

        _dimensions = d.pop("dimensions", UNSET)
        dimensions: RateChangeInDimensions | Unset
        if isinstance(_dimensions,  Unset):
            dimensions = UNSET
        else:
            dimensions = RateChangeInDimensions.from_dict(_dimensions)




        event_type = d.pop("event_type", UNSET)

        def _parse_fixed_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fixed_micros = _parse_fixed_micros(d.pop("fixed_micros", UNSET))


        def _parse_pricing_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pricing_model = _parse_pricing_model(d.pop("pricing_model", UNSET))


        provider = d.pop("provider", UNSET)

        def _parse_rate_per_unit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rate_per_unit_micros = _parse_rate_per_unit_micros(d.pop("rate_per_unit_micros", UNSET))


        def _parse_unit_quantity(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        unit_quantity = _parse_unit_quantity(d.pop("unit_quantity", UNSET))


        rate_change_in = cls(
            metric_name=metric_name,
            dimensions=dimensions,
            event_type=event_type,
            fixed_micros=fixed_micros,
            pricing_model=pricing_model,
            provider=provider,
            rate_per_unit_micros=rate_per_unit_micros,
            unit_quantity=unit_quantity,
        )


        rate_change_in.additional_properties = d
        return rate_change_in

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
