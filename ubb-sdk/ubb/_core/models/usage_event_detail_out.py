from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID

if TYPE_CHECKING:
  from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
  from ..models.usage_event_detail_out_pricing_provenance import UsageEventDetailOutPricingProvenance
  from ..models.usage_event_detail_out_tags_type_0 import UsageEventDetailOutTagsType0
  from ..models.usage_event_detail_out_usage_metrics import UsageEventDetailOutUsageMetrics





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
            provider_cost_micros (int):
            request_id (str):
            agent_id (str | Unset):  Default: ''.
            currency (str | Unset):  Default: 'usd'.
            event_type (str | Unset):  Default: ''.
            metadata (UsageEventDetailOutMetadata | Unset):
            pricing_provenance (UsageEventDetailOutPricingProvenance | Unset):
            product_id (str | Unset):  Default: ''.
            provider (str | Unset):  Default: ''.
            service_id (str | Unset):  Default: ''.
            stop_context (list[Any] | None | Unset):
            tags (None | Unset | UsageEventDetailOutTagsType0):
            task_id (None | str | Unset):
            units (int | None | Unset):
            usage_metrics (UsageEventDetailOutUsageMetrics | Unset):
     """

    billed_cost_micros: int
    created_at: str
    effective_at: str
    id: UUID
    idempotency_key: str
    provider_cost_micros: int
    request_id: str
    agent_id: str | Unset = ''
    currency: str | Unset = 'usd'
    event_type: str | Unset = ''
    metadata: UsageEventDetailOutMetadata | Unset = UNSET
    pricing_provenance: UsageEventDetailOutPricingProvenance | Unset = UNSET
    product_id: str | Unset = ''
    provider: str | Unset = ''
    service_id: str | Unset = ''
    stop_context: list[Any] | None | Unset = UNSET
    tags: None | Unset | UsageEventDetailOutTagsType0 = UNSET
    task_id: None | str | Unset = UNSET
    units: int | None | Unset = UNSET
    usage_metrics: UsageEventDetailOutUsageMetrics | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
        from ..models.usage_event_detail_out_pricing_provenance import UsageEventDetailOutPricingProvenance
        from ..models.usage_event_detail_out_tags_type_0 import UsageEventDetailOutTagsType0
        from ..models.usage_event_detail_out_usage_metrics import UsageEventDetailOutUsageMetrics
        billed_cost_micros = self.billed_cost_micros

        created_at = self.created_at

        effective_at = self.effective_at

        id = str(self.id)

        idempotency_key = self.idempotency_key

        provider_cost_micros = self.provider_cost_micros

        request_id = self.request_id

        agent_id = self.agent_id

        currency = self.currency

        event_type = self.event_type

        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        pricing_provenance: dict[str, Any] | Unset = UNSET
        if not isinstance(self.pricing_provenance, Unset):
            pricing_provenance = self.pricing_provenance.to_dict()

        product_id = self.product_id

        provider = self.provider

        service_id = self.service_id

        stop_context: list[Any] | None | Unset
        if isinstance(self.stop_context, Unset):
            stop_context = UNSET
        elif isinstance(self.stop_context, list):
            stop_context = self.stop_context


        else:
            stop_context = self.stop_context

        tags: dict[str, Any] | None | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, UsageEventDetailOutTagsType0):
            tags = self.tags.to_dict()
        else:
            tags = self.tags

        task_id: None | str | Unset
        if isinstance(self.task_id, Unset):
            task_id = UNSET
        else:
            task_id = self.task_id

        units: int | None | Unset
        if isinstance(self.units, Unset):
            units = UNSET
        else:
            units = self.units

        usage_metrics: dict[str, Any] | Unset = UNSET
        if not isinstance(self.usage_metrics, Unset):
            usage_metrics = self.usage_metrics.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billed_cost_micros": billed_cost_micros,
            "created_at": created_at,
            "effective_at": effective_at,
            "id": id,
            "idempotency_key": idempotency_key,
            "provider_cost_micros": provider_cost_micros,
            "request_id": request_id,
        })
        if agent_id is not UNSET:
            field_dict["agent_id"] = agent_id
        if currency is not UNSET:
            field_dict["currency"] = currency
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if pricing_provenance is not UNSET:
            field_dict["pricing_provenance"] = pricing_provenance
        if product_id is not UNSET:
            field_dict["product_id"] = product_id
        if provider is not UNSET:
            field_dict["provider"] = provider
        if service_id is not UNSET:
            field_dict["service_id"] = service_id
        if stop_context is not UNSET:
            field_dict["stop_context"] = stop_context
        if tags is not UNSET:
            field_dict["tags"] = tags
        if task_id is not UNSET:
            field_dict["task_id"] = task_id
        if units is not UNSET:
            field_dict["units"] = units
        if usage_metrics is not UNSET:
            field_dict["usage_metrics"] = usage_metrics

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
        from ..models.usage_event_detail_out_pricing_provenance import UsageEventDetailOutPricingProvenance
        from ..models.usage_event_detail_out_tags_type_0 import UsageEventDetailOutTagsType0
        from ..models.usage_event_detail_out_usage_metrics import UsageEventDetailOutUsageMetrics
        d = dict(src_dict)
        billed_cost_micros = d.pop("billed_cost_micros")

        created_at = d.pop("created_at")

        effective_at = d.pop("effective_at")

        id = UUID(d.pop("id"))




        idempotency_key = d.pop("idempotency_key")

        provider_cost_micros = d.pop("provider_cost_micros")

        request_id = d.pop("request_id")

        agent_id = d.pop("agent_id", UNSET)

        currency = d.pop("currency", UNSET)

        event_type = d.pop("event_type", UNSET)

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




        product_id = d.pop("product_id", UNSET)

        provider = d.pop("provider", UNSET)

        service_id = d.pop("service_id", UNSET)

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


        def _parse_tags(data: object) -> None | Unset | UsageEventDetailOutTagsType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                tags_type_0 = UsageEventDetailOutTagsType0.from_dict(data)



                return tags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageEventDetailOutTagsType0, data)

        tags = _parse_tags(d.pop("tags", UNSET))


        def _parse_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_id = _parse_task_id(d.pop("task_id", UNSET))


        def _parse_units(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        units = _parse_units(d.pop("units", UNSET))


        _usage_metrics = d.pop("usage_metrics", UNSET)
        usage_metrics: UsageEventDetailOutUsageMetrics | Unset
        if isinstance(_usage_metrics,  Unset):
            usage_metrics = UNSET
        else:
            usage_metrics = UsageEventDetailOutUsageMetrics.from_dict(_usage_metrics)




        usage_event_detail_out = cls(
            billed_cost_micros=billed_cost_micros,
            created_at=created_at,
            effective_at=effective_at,
            id=id,
            idempotency_key=idempotency_key,
            provider_cost_micros=provider_cost_micros,
            request_id=request_id,
            agent_id=agent_id,
            currency=currency,
            event_type=event_type,
            metadata=metadata,
            pricing_provenance=pricing_provenance,
            product_id=product_id,
            provider=provider,
            service_id=service_id,
            stop_context=stop_context,
            tags=tags,
            task_id=task_id,
            units=units,
            usage_metrics=usage_metrics,
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
