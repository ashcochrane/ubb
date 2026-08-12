from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.usage_event_detail_out_measurements_status import UsageEventDetailOutMeasurementsStatus
from ..types import UNSET, Unset
from typing import cast
from uuid import UUID

if TYPE_CHECKING:
  from ..models.usage_event_detail_out_grouping_fields import UsageEventDetailOutGroupingFields
  from ..models.usage_event_detail_out_measurements import UsageEventDetailOutMeasurements
  from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
  from ..models.usage_event_detail_out_pricing_provenance import UsageEventDetailOutPricingProvenance





T = TypeVar("T", bound="UsageEventDetailOut")



@_attrs_define
class UsageEventDetailOut:
    """ 
        Attributes:
            billed_cost_micros (int):
            created_at (str):
            effective_at (str):
            id (UUID):
            idempotency_key (str):
            measurements_status (UsageEventDetailOutMeasurementsStatus):
            provider_cost_micros (int):
            request_id (str):
            currency (str | Unset):  Default: 'usd'.
            event_type (str | Unset):  Default: ''.
            grouping_fields (UsageEventDetailOutGroupingFields | Unset):
            measurements (UsageEventDetailOutMeasurements | Unset):
            metadata (UsageEventDetailOutMetadata | Unset):
            pricing_provenance (UsageEventDetailOutPricingProvenance | Unset):
            provider (str | Unset):  Default: ''.
            stop_context (list[Any] | None | Unset):
            task_id (None | str | Unset):
     """

    billed_cost_micros: int
    created_at: str
    effective_at: str
    id: UUID
    idempotency_key: str
    measurements_status: UsageEventDetailOutMeasurementsStatus
    provider_cost_micros: int
    request_id: str
    currency: str | Unset = 'usd'
    event_type: str | Unset = ''
    grouping_fields: UsageEventDetailOutGroupingFields | Unset = UNSET
    measurements: UsageEventDetailOutMeasurements | Unset = UNSET
    metadata: UsageEventDetailOutMetadata | Unset = UNSET
    pricing_provenance: UsageEventDetailOutPricingProvenance | Unset = UNSET
    provider: str | Unset = ''
    stop_context: list[Any] | None | Unset = UNSET
    task_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_event_detail_out_grouping_fields import UsageEventDetailOutGroupingFields
        from ..models.usage_event_detail_out_measurements import UsageEventDetailOutMeasurements
        from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
        from ..models.usage_event_detail_out_pricing_provenance import UsageEventDetailOutPricingProvenance
        billed_cost_micros = self.billed_cost_micros

        created_at = self.created_at

        effective_at = self.effective_at

        id = str(self.id)

        idempotency_key = self.idempotency_key

        measurements_status = self.measurements_status.value

        provider_cost_micros = self.provider_cost_micros

        request_id = self.request_id

        currency = self.currency

        event_type = self.event_type

        grouping_fields: dict[str, Any] | Unset = UNSET
        if not isinstance(self.grouping_fields, Unset):
            grouping_fields = self.grouping_fields.to_dict()

        measurements: dict[str, Any] | Unset = UNSET
        if not isinstance(self.measurements, Unset):
            measurements = self.measurements.to_dict()

        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        pricing_provenance: dict[str, Any] | Unset = UNSET
        if not isinstance(self.pricing_provenance, Unset):
            pricing_provenance = self.pricing_provenance.to_dict()

        provider = self.provider

        stop_context: list[Any] | None | Unset
        if isinstance(self.stop_context, Unset):
            stop_context = UNSET
        elif isinstance(self.stop_context, list):
            stop_context = self.stop_context


        else:
            stop_context = self.stop_context

        task_id: None | str | Unset
        if isinstance(self.task_id, Unset):
            task_id = UNSET
        else:
            task_id = self.task_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billed_cost_micros": billed_cost_micros,
            "created_at": created_at,
            "effective_at": effective_at,
            "id": id,
            "idempotency_key": idempotency_key,
            "measurements_status": measurements_status,
            "provider_cost_micros": provider_cost_micros,
            "request_id": request_id,
        })
        if currency is not UNSET:
            field_dict["currency"] = currency
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if grouping_fields is not UNSET:
            field_dict["grouping_fields"] = grouping_fields
        if measurements is not UNSET:
            field_dict["measurements"] = measurements
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if pricing_provenance is not UNSET:
            field_dict["pricing_provenance"] = pricing_provenance
        if provider is not UNSET:
            field_dict["provider"] = provider
        if stop_context is not UNSET:
            field_dict["stop_context"] = stop_context
        if task_id is not UNSET:
            field_dict["task_id"] = task_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_event_detail_out_grouping_fields import UsageEventDetailOutGroupingFields
        from ..models.usage_event_detail_out_measurements import UsageEventDetailOutMeasurements
        from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
        from ..models.usage_event_detail_out_pricing_provenance import UsageEventDetailOutPricingProvenance
        d = dict(src_dict)
        billed_cost_micros = d.pop("billed_cost_micros")

        created_at = d.pop("created_at")

        effective_at = d.pop("effective_at")

        id = UUID(d.pop("id"))




        idempotency_key = d.pop("idempotency_key")

        measurements_status = UsageEventDetailOutMeasurementsStatus(d.pop("measurements_status"))




        provider_cost_micros = d.pop("provider_cost_micros")

        request_id = d.pop("request_id")

        currency = d.pop("currency", UNSET)

        event_type = d.pop("event_type", UNSET)

        _grouping_fields = d.pop("grouping_fields", UNSET)
        grouping_fields: UsageEventDetailOutGroupingFields | Unset
        if isinstance(_grouping_fields,  Unset):
            grouping_fields = UNSET
        else:
            grouping_fields = UsageEventDetailOutGroupingFields.from_dict(_grouping_fields)




        _measurements = d.pop("measurements", UNSET)
        measurements: UsageEventDetailOutMeasurements | Unset
        if isinstance(_measurements,  Unset):
            measurements = UNSET
        else:
            measurements = UsageEventDetailOutMeasurements.from_dict(_measurements)




        _metadata = d.pop("metadata", UNSET)
        metadata: UsageEventDetailOutMetadata | Unset
        if isinstance(_metadata,  Unset):
            metadata = UNSET
        else:
            metadata = UsageEventDetailOutMetadata.from_dict(_metadata)




        _pricing_provenance = d.pop("pricing_provenance", UNSET)
        pricing_provenance: UsageEventDetailOutPricingProvenance | Unset
        if isinstance(_pricing_provenance,  Unset):
            pricing_provenance = UNSET
        else:
            pricing_provenance = UsageEventDetailOutPricingProvenance.from_dict(_pricing_provenance)




        provider = d.pop("provider", UNSET)

        def _parse_stop_context(data: object) -> list[Any] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                stop_context_type_0 = cast(list[Any], data)

                return stop_context_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None | Unset, data)

        stop_context = _parse_stop_context(d.pop("stop_context", UNSET))


        def _parse_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_id = _parse_task_id(d.pop("task_id", UNSET))


        usage_event_detail_out = cls(
            billed_cost_micros=billed_cost_micros,
            created_at=created_at,
            effective_at=effective_at,
            id=id,
            idempotency_key=idempotency_key,
            measurements_status=measurements_status,
            provider_cost_micros=provider_cost_micros,
            request_id=request_id,
            currency=currency,
            event_type=event_type,
            grouping_fields=grouping_fields,
            measurements=measurements,
            metadata=metadata,
            pricing_provenance=pricing_provenance,
            provider=provider,
            stop_context=stop_context,
            task_id=task_id,
        )


        usage_event_detail_out.additional_properties = d
        return usage_event_detail_out

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
