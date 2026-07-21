from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.rate_out_dimensions import RateOutDimensions





T = TypeVar("T", bound="RateOut")



@_attrs_define
class RateOut:
    """ 
        Attributes:
            card_type (str):
            currency (str):
            dimensions (RateOutDimensions):
            event_type (str):
            fixed_micros (int):
            id (str):
            lineage_id (str):
            metric_name (str):
            pricing_model (str):
            product_id (str):
            provider (str):
            rate_card_id (str):
            rate_per_unit_micros (int):
            unit_quantity (int):
            valid_from (str):
            valid_to (None | str | Unset):
     """

    card_type: str
    currency: str
    dimensions: RateOutDimensions
    event_type: str
    fixed_micros: int
    id: str
    lineage_id: str
    metric_name: str
    pricing_model: str
    product_id: str
    provider: str
    rate_card_id: str
    rate_per_unit_micros: int
    unit_quantity: int
    valid_from: str
    valid_to: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.rate_out_dimensions import RateOutDimensions
        card_type = self.card_type

        currency = self.currency

        dimensions = self.dimensions.to_dict()

        event_type = self.event_type

        fixed_micros = self.fixed_micros

        id = self.id

        lineage_id = self.lineage_id

        metric_name = self.metric_name

        pricing_model = self.pricing_model

        product_id = self.product_id

        provider = self.provider

        rate_card_id = self.rate_card_id

        rate_per_unit_micros = self.rate_per_unit_micros

        unit_quantity = self.unit_quantity

        valid_from = self.valid_from

        valid_to: None | str | Unset
        if isinstance(self.valid_to, Unset):
            valid_to = UNSET
        else:
            valid_to = self.valid_to


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "card_type": card_type,
            "currency": currency,
            "dimensions": dimensions,
            "event_type": event_type,
            "fixed_micros": fixed_micros,
            "id": id,
            "lineage_id": lineage_id,
            "metric_name": metric_name,
            "pricing_model": pricing_model,
            "product_id": product_id,
            "provider": provider,
            "rate_card_id": rate_card_id,
            "rate_per_unit_micros": rate_per_unit_micros,
            "unit_quantity": unit_quantity,
            "valid_from": valid_from,
        })
        if valid_to is not UNSET:
            field_dict["valid_to"] = valid_to

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rate_out_dimensions import RateOutDimensions
        d = dict(src_dict)
        card_type = d.pop("card_type")

        currency = d.pop("currency")

        dimensions = RateOutDimensions.from_dict(d.pop("dimensions"))




        event_type = d.pop("event_type")

        fixed_micros = d.pop("fixed_micros")

        id = d.pop("id")

        lineage_id = d.pop("lineage_id")

        metric_name = d.pop("metric_name")

        pricing_model = d.pop("pricing_model")

        product_id = d.pop("product_id")

        provider = d.pop("provider")

        rate_card_id = d.pop("rate_card_id")

        rate_per_unit_micros = d.pop("rate_per_unit_micros")

        unit_quantity = d.pop("unit_quantity")

        valid_from = d.pop("valid_from")

        def _parse_valid_to(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        valid_to = _parse_valid_to(d.pop("valid_to", UNSET))


        rate_out = cls(
            card_type=card_type,
            currency=currency,
            dimensions=dimensions,
            event_type=event_type,
            fixed_micros=fixed_micros,
            id=id,
            lineage_id=lineage_id,
            metric_name=metric_name,
            pricing_model=pricing_model,
            product_id=product_id,
            provider=provider,
            rate_card_id=rate_card_id,
            rate_per_unit_micros=rate_per_unit_micros,
            unit_quantity=unit_quantity,
            valid_from=valid_from,
            valid_to=valid_to,
        )


        rate_out.additional_properties = d
        return rate_out

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
