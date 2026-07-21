from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime

if TYPE_CHECKING:
  from ..models.record_usage_request_metadata import RecordUsageRequestMetadata
  from ..models.record_usage_request_tags_type_0 import RecordUsageRequestTagsType0
  from ..models.record_usage_request_usage_metrics_type_0 import RecordUsageRequestUsageMetricsType0





T = TypeVar("T", bound="RecordUsageRequest")



@_attrs_define
class RecordUsageRequest:
    """ 
        Attributes:
            customer_id (UUID):
            idempotency_key (str):
            request_id (str):
            billed_cost_micros (int | None | Unset):
            currency (None | str | Unset):
            effective_at (datetime.datetime | None | Unset):
            event_type (None | str | Unset):
            metadata (RecordUsageRequestMetadata | Unset):
            product_id (None | str | Unset):
            provider (None | str | Unset):
            provider_cost_micros (int | None | Unset):
            tags (None | RecordUsageRequestTagsType0 | Unset):
            task_id (None | Unset | UUID):
            units (int | None | Unset):
            usage_metrics (None | RecordUsageRequestUsageMetricsType0 | Unset):
     """

    customer_id: UUID
    idempotency_key: str
    request_id: str
    billed_cost_micros: int | None | Unset = UNSET
    currency: None | str | Unset = UNSET
    effective_at: datetime.datetime | None | Unset = UNSET
    event_type: None | str | Unset = UNSET
    metadata: RecordUsageRequestMetadata | Unset = UNSET
    product_id: None | str | Unset = UNSET
    provider: None | str | Unset = UNSET
    provider_cost_micros: int | None | Unset = UNSET
    tags: None | RecordUsageRequestTagsType0 | Unset = UNSET
    task_id: None | Unset | UUID = UNSET
    units: int | None | Unset = UNSET
    usage_metrics: None | RecordUsageRequestUsageMetricsType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.record_usage_request_metadata import RecordUsageRequestMetadata
        from ..models.record_usage_request_tags_type_0 import RecordUsageRequestTagsType0
        from ..models.record_usage_request_usage_metrics_type_0 import RecordUsageRequestUsageMetricsType0
        customer_id = str(self.customer_id)

        idempotency_key = self.idempotency_key

        request_id = self.request_id

        billed_cost_micros: int | None | Unset
        if isinstance(self.billed_cost_micros, Unset):
            billed_cost_micros = UNSET
        else:
            billed_cost_micros = self.billed_cost_micros

        currency: None | str | Unset
        if isinstance(self.currency, Unset):
            currency = UNSET
        else:
            currency = self.currency

        effective_at: None | str | Unset
        if isinstance(self.effective_at, Unset):
            effective_at = UNSET
        elif isinstance(self.effective_at, datetime.datetime):
            effective_at = self.effective_at.isoformat()
        else:
            effective_at = self.effective_at

        event_type: None | str | Unset
        if isinstance(self.event_type, Unset):
            event_type = UNSET
        else:
            event_type = self.event_type

        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        product_id: None | str | Unset
        if isinstance(self.product_id, Unset):
            product_id = UNSET
        else:
            product_id = self.product_id

        provider: None | str | Unset
        if isinstance(self.provider, Unset):
            provider = UNSET
        else:
            provider = self.provider

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros

        tags: dict[str, Any] | None | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, RecordUsageRequestTagsType0):
            tags = self.tags.to_dict()
        else:
            tags = self.tags

        task_id: None | str | Unset
        if isinstance(self.task_id, Unset):
            task_id = UNSET
        elif isinstance(self.task_id, UUID):
            task_id = str(self.task_id)
        else:
            task_id = self.task_id

        units: int | None | Unset
        if isinstance(self.units, Unset):
            units = UNSET
        else:
            units = self.units

        usage_metrics: dict[str, Any] | None | Unset
        if isinstance(self.usage_metrics, Unset):
            usage_metrics = UNSET
        elif isinstance(self.usage_metrics, RecordUsageRequestUsageMetricsType0):
            usage_metrics = self.usage_metrics.to_dict()
        else:
            usage_metrics = self.usage_metrics


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_id": customer_id,
            "idempotency_key": idempotency_key,
            "request_id": request_id,
        })
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if currency is not UNSET:
            field_dict["currency"] = currency
        if effective_at is not UNSET:
            field_dict["effective_at"] = effective_at
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if product_id is not UNSET:
            field_dict["product_id"] = product_id
        if provider is not UNSET:
            field_dict["provider"] = provider
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
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
        from ..models.record_usage_request_metadata import RecordUsageRequestMetadata
        from ..models.record_usage_request_tags_type_0 import RecordUsageRequestTagsType0
        from ..models.record_usage_request_usage_metrics_type_0 import RecordUsageRequestUsageMetricsType0
        d = dict(src_dict)
        customer_id = UUID(d.pop("customer_id"))




        idempotency_key = d.pop("idempotency_key")

        request_id = d.pop("request_id")

        def _parse_billed_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        billed_cost_micros = _parse_billed_cost_micros(d.pop("billed_cost_micros", UNSET))


        def _parse_currency(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        currency = _parse_currency(d.pop("currency", UNSET))


        def _parse_effective_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                effective_at_type_0 = datetime.datetime.fromisoformat(data)



                return effective_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        effective_at = _parse_effective_at(d.pop("effective_at", UNSET))


        def _parse_event_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        event_type = _parse_event_type(d.pop("event_type", UNSET))


        _metadata = d.pop("metadata", UNSET)
        metadata: RecordUsageRequestMetadata | Unset
        if isinstance(_metadata,  Unset):
            metadata = UNSET
        else:
            metadata = RecordUsageRequestMetadata.from_dict(_metadata)




        def _parse_product_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        product_id = _parse_product_id(d.pop("product_id", UNSET))


        def _parse_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider = _parse_provider(d.pop("provider", UNSET))


        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


        def _parse_tags(data: object) -> None | RecordUsageRequestTagsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                tags_type_0 = RecordUsageRequestTagsType0.from_dict(data)



                return tags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageRequestTagsType0 | Unset, data)

        tags = _parse_tags(d.pop("tags", UNSET))


        def _parse_task_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                task_id_type_0 = UUID(data)



                return task_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        task_id = _parse_task_id(d.pop("task_id", UNSET))


        def _parse_units(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        units = _parse_units(d.pop("units", UNSET))


        def _parse_usage_metrics(data: object) -> None | RecordUsageRequestUsageMetricsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                usage_metrics_type_0 = RecordUsageRequestUsageMetricsType0.from_dict(data)



                return usage_metrics_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageRequestUsageMetricsType0 | Unset, data)

        usage_metrics = _parse_usage_metrics(d.pop("usage_metrics", UNSET))


        record_usage_request = cls(
            customer_id=customer_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
            billed_cost_micros=billed_cost_micros,
            currency=currency,
            effective_at=effective_at,
            event_type=event_type,
            metadata=metadata,
            product_id=product_id,
            provider=provider,
            provider_cost_micros=provider_cost_micros,
            tags=tags,
            task_id=task_id,
            units=units,
            usage_metrics=usage_metrics,
        )


        record_usage_request.additional_properties = d
        return record_usage_request

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
