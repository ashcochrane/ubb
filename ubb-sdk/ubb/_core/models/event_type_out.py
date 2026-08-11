from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.event_type_out_costing_method import EventTypeOutCostingMethod
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.measurement_out import MeasurementOut
  from ..models.reported_cost_mapping_out import ReportedCostMappingOut





T = TypeVar("T", bound="EventTypeOut")



@_attrs_define
class EventTypeOut:
    """ 
        Attributes:
            costing_method (EventTypeOutCostingMethod):
            declaration_status (str):
            key (str):
            measurements (list[MeasurementOut]):
            publication_blockers (list[str]):
            published_revision (int):
            source_shape_id (str):
            source_shape_label (str):
            category_key (None | str | Unset):
            provider_key (None | str | Unset):
            published_at (None | str | Unset):
            reported_cost_mapping (None | ReportedCostMappingOut | Unset):
     """

    costing_method: EventTypeOutCostingMethod
    declaration_status: str
    key: str
    measurements: list[MeasurementOut]
    publication_blockers: list[str]
    published_revision: int
    source_shape_id: str
    source_shape_label: str
    category_key: None | str | Unset = UNSET
    provider_key: None | str | Unset = UNSET
    published_at: None | str | Unset = UNSET
    reported_cost_mapping: None | ReportedCostMappingOut | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.measurement_out import MeasurementOut
        from ..models.reported_cost_mapping_out import ReportedCostMappingOut
        costing_method = self.costing_method.value

        declaration_status = self.declaration_status

        key = self.key

        measurements = []
        for measurements_item_data in self.measurements:
            measurements_item = measurements_item_data.to_dict()
            measurements.append(measurements_item)



        publication_blockers = self.publication_blockers



        published_revision = self.published_revision

        source_shape_id = self.source_shape_id

        source_shape_label = self.source_shape_label

        category_key: None | str | Unset
        if isinstance(self.category_key, Unset):
            category_key = UNSET
        else:
            category_key = self.category_key

        provider_key: None | str | Unset
        if isinstance(self.provider_key, Unset):
            provider_key = UNSET
        else:
            provider_key = self.provider_key

        published_at: None | str | Unset
        if isinstance(self.published_at, Unset):
            published_at = UNSET
        else:
            published_at = self.published_at

        reported_cost_mapping: dict[str, Any] | None | Unset
        if isinstance(self.reported_cost_mapping, Unset):
            reported_cost_mapping = UNSET
        elif isinstance(self.reported_cost_mapping, ReportedCostMappingOut):
            reported_cost_mapping = self.reported_cost_mapping.to_dict()
        else:
            reported_cost_mapping = self.reported_cost_mapping


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "costing_method": costing_method,
            "declaration_status": declaration_status,
            "key": key,
            "measurements": measurements,
            "publication_blockers": publication_blockers,
            "published_revision": published_revision,
            "source_shape_id": source_shape_id,
            "source_shape_label": source_shape_label,
        })
        if category_key is not UNSET:
            field_dict["category_key"] = category_key
        if provider_key is not UNSET:
            field_dict["provider_key"] = provider_key
        if published_at is not UNSET:
            field_dict["published_at"] = published_at
        if reported_cost_mapping is not UNSET:
            field_dict["reported_cost_mapping"] = reported_cost_mapping

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.measurement_out import MeasurementOut
        from ..models.reported_cost_mapping_out import ReportedCostMappingOut
        d = dict(src_dict)
        costing_method = EventTypeOutCostingMethod(d.pop("costing_method"))




        declaration_status = d.pop("declaration_status")

        key = d.pop("key")

        measurements = []
        _measurements = d.pop("measurements")
        for measurements_item_data in (_measurements):
            measurements_item = MeasurementOut.from_dict(measurements_item_data)



            measurements.append(measurements_item)


        publication_blockers = cast(list[str], d.pop("publication_blockers"))


        published_revision = d.pop("published_revision")

        source_shape_id = d.pop("source_shape_id")

        source_shape_label = d.pop("source_shape_label")

        def _parse_category_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        category_key = _parse_category_key(d.pop("category_key", UNSET))


        def _parse_provider_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_key = _parse_provider_key(d.pop("provider_key", UNSET))


        def _parse_published_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        published_at = _parse_published_at(d.pop("published_at", UNSET))


        def _parse_reported_cost_mapping(data: object) -> None | ReportedCostMappingOut | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                reported_cost_mapping_type_0 = ReportedCostMappingOut.from_dict(data)



                return reported_cost_mapping_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ReportedCostMappingOut | Unset, data)

        reported_cost_mapping = _parse_reported_cost_mapping(d.pop("reported_cost_mapping", UNSET))


        event_type_out = cls(
            costing_method=costing_method,
            declaration_status=declaration_status,
            key=key,
            measurements=measurements,
            publication_blockers=publication_blockers,
            published_revision=published_revision,
            source_shape_id=source_shape_id,
            source_shape_label=source_shape_label,
            category_key=category_key,
            provider_key=provider_key,
            published_at=published_at,
            reported_cost_mapping=reported_cost_mapping,
        )


        event_type_out.additional_properties = d
        return event_type_out

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
