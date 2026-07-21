from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.record_usage_response_pricing_provenance_type_0 import RecordUsageResponsePricingProvenanceType0
  from ..models.record_usage_response_usage_metrics_type_0 import RecordUsageResponseUsageMetricsType0





T = TypeVar("T", bound="RecordUsageResponse")



@_attrs_define
class RecordUsageResponse:
    """ 
        Attributes:
            event_id (str):
            suspended (bool):
            agent_id (str | Unset):  Default: ''.
            billed_cost_micros (int | None | Unset):
            new_balance_micros (int | None | Unset):
            parent_task_id (None | str | Unset):
            pricing_provenance (None | RecordUsageResponsePricingProvenanceType0 | Unset):
            provider_cost_micros (int | None | Unset):
            service_id (str | Unset):  Default: ''.
            stop (bool | Unset):  Default: False.
            stop_context (list[Any] | None | Unset):
            stop_reason (None | str | Unset):
            stop_scope (None | str | Unset):
            task_id (None | str | Unset):
            task_total_billed_cost_micros (int | None | Unset):
            task_total_provider_cost_micros (int | None | Unset):
            uncosted_metrics (list[str] | Unset):
            units (int | None | Unset):
            usage_metrics (None | RecordUsageResponseUsageMetricsType0 | Unset):
     """

    event_id: str
    suspended: bool
    agent_id: str | Unset = ''
    billed_cost_micros: int | None | Unset = UNSET
    new_balance_micros: int | None | Unset = UNSET
    parent_task_id: None | str | Unset = UNSET
    pricing_provenance: None | RecordUsageResponsePricingProvenanceType0 | Unset = UNSET
    provider_cost_micros: int | None | Unset = UNSET
    service_id: str | Unset = ''
    stop: bool | Unset = False
    stop_context: list[Any] | None | Unset = UNSET
    stop_reason: None | str | Unset = UNSET
    stop_scope: None | str | Unset = UNSET
    task_id: None | str | Unset = UNSET
    task_total_billed_cost_micros: int | None | Unset = UNSET
    task_total_provider_cost_micros: int | None | Unset = UNSET
    uncosted_metrics: list[str] | Unset = UNSET
    units: int | None | Unset = UNSET
    usage_metrics: None | RecordUsageResponseUsageMetricsType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.record_usage_response_pricing_provenance_type_0 import RecordUsageResponsePricingProvenanceType0
        from ..models.record_usage_response_usage_metrics_type_0 import RecordUsageResponseUsageMetricsType0
        event_id = self.event_id

        suspended = self.suspended

        agent_id = self.agent_id

        billed_cost_micros: int | None | Unset
        if isinstance(self.billed_cost_micros, Unset):
            billed_cost_micros = UNSET
        else:
            billed_cost_micros = self.billed_cost_micros

        new_balance_micros: int | None | Unset
        if isinstance(self.new_balance_micros, Unset):
            new_balance_micros = UNSET
        else:
            new_balance_micros = self.new_balance_micros

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        else:
            parent_task_id = self.parent_task_id

        pricing_provenance: dict[str, Any] | None | Unset
        if isinstance(self.pricing_provenance, Unset):
            pricing_provenance = UNSET
        elif isinstance(self.pricing_provenance, RecordUsageResponsePricingProvenanceType0):
            pricing_provenance = self.pricing_provenance.to_dict()
        else:
            pricing_provenance = self.pricing_provenance

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros

        service_id = self.service_id

        stop = self.stop

        stop_context: list[Any] | None | Unset
        if isinstance(self.stop_context, Unset):
            stop_context = UNSET
        elif isinstance(self.stop_context, list):
            stop_context = self.stop_context


        else:
            stop_context = self.stop_context

        stop_reason: None | str | Unset
        if isinstance(self.stop_reason, Unset):
            stop_reason = UNSET
        else:
            stop_reason = self.stop_reason

        stop_scope: None | str | Unset
        if isinstance(self.stop_scope, Unset):
            stop_scope = UNSET
        else:
            stop_scope = self.stop_scope

        task_id: None | str | Unset
        if isinstance(self.task_id, Unset):
            task_id = UNSET
        else:
            task_id = self.task_id

        task_total_billed_cost_micros: int | None | Unset
        if isinstance(self.task_total_billed_cost_micros, Unset):
            task_total_billed_cost_micros = UNSET
        else:
            task_total_billed_cost_micros = self.task_total_billed_cost_micros

        task_total_provider_cost_micros: int | None | Unset
        if isinstance(self.task_total_provider_cost_micros, Unset):
            task_total_provider_cost_micros = UNSET
        else:
            task_total_provider_cost_micros = self.task_total_provider_cost_micros

        uncosted_metrics: list[str] | Unset = UNSET
        if not isinstance(self.uncosted_metrics, Unset):
            uncosted_metrics = self.uncosted_metrics



        units: int | None | Unset
        if isinstance(self.units, Unset):
            units = UNSET
        else:
            units = self.units

        usage_metrics: dict[str, Any] | None | Unset
        if isinstance(self.usage_metrics, Unset):
            usage_metrics = UNSET
        elif isinstance(self.usage_metrics, RecordUsageResponseUsageMetricsType0):
            usage_metrics = self.usage_metrics.to_dict()
        else:
            usage_metrics = self.usage_metrics


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event_id": event_id,
            "suspended": suspended,
        })
        if agent_id is not UNSET:
            field_dict["agent_id"] = agent_id
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if new_balance_micros is not UNSET:
            field_dict["new_balance_micros"] = new_balance_micros
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if pricing_provenance is not UNSET:
            field_dict["pricing_provenance"] = pricing_provenance
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
        if service_id is not UNSET:
            field_dict["service_id"] = service_id
        if stop is not UNSET:
            field_dict["stop"] = stop
        if stop_context is not UNSET:
            field_dict["stop_context"] = stop_context
        if stop_reason is not UNSET:
            field_dict["stop_reason"] = stop_reason
        if stop_scope is not UNSET:
            field_dict["stop_scope"] = stop_scope
        if task_id is not UNSET:
            field_dict["task_id"] = task_id
        if task_total_billed_cost_micros is not UNSET:
            field_dict["task_total_billed_cost_micros"] = task_total_billed_cost_micros
        if task_total_provider_cost_micros is not UNSET:
            field_dict["task_total_provider_cost_micros"] = task_total_provider_cost_micros
        if uncosted_metrics is not UNSET:
            field_dict["uncosted_metrics"] = uncosted_metrics
        if units is not UNSET:
            field_dict["units"] = units
        if usage_metrics is not UNSET:
            field_dict["usage_metrics"] = usage_metrics

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.record_usage_response_pricing_provenance_type_0 import RecordUsageResponsePricingProvenanceType0
        from ..models.record_usage_response_usage_metrics_type_0 import RecordUsageResponseUsageMetricsType0
        d = dict(src_dict)
        event_id = d.pop("event_id")

        suspended = d.pop("suspended")

        agent_id = d.pop("agent_id", UNSET)

        def _parse_billed_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        billed_cost_micros = _parse_billed_cost_micros(d.pop("billed_cost_micros", UNSET))


        def _parse_new_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        new_balance_micros = _parse_new_balance_micros(d.pop("new_balance_micros", UNSET))


        def _parse_parent_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_pricing_provenance(data: object) -> None | RecordUsageResponsePricingProvenanceType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                pricing_provenance_type_0 = RecordUsageResponsePricingProvenanceType0.from_dict(data)



                return pricing_provenance_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponsePricingProvenanceType0 | Unset, data)

        pricing_provenance = _parse_pricing_provenance(d.pop("pricing_provenance", UNSET))


        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


        service_id = d.pop("service_id", UNSET)

        stop = d.pop("stop", UNSET)

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


        def _parse_stop_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        stop_reason = _parse_stop_reason(d.pop("stop_reason", UNSET))


        def _parse_stop_scope(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        stop_scope = _parse_stop_scope(d.pop("stop_scope", UNSET))


        def _parse_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_id = _parse_task_id(d.pop("task_id", UNSET))


        def _parse_task_total_billed_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        task_total_billed_cost_micros = _parse_task_total_billed_cost_micros(d.pop("task_total_billed_cost_micros", UNSET))


        def _parse_task_total_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        task_total_provider_cost_micros = _parse_task_total_provider_cost_micros(d.pop("task_total_provider_cost_micros", UNSET))


        uncosted_metrics = cast(list[str], d.pop("uncosted_metrics", UNSET))


        def _parse_units(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        units = _parse_units(d.pop("units", UNSET))


        def _parse_usage_metrics(data: object) -> None | RecordUsageResponseUsageMetricsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                usage_metrics_type_0 = RecordUsageResponseUsageMetricsType0.from_dict(data)



                return usage_metrics_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponseUsageMetricsType0 | Unset, data)

        usage_metrics = _parse_usage_metrics(d.pop("usage_metrics", UNSET))


        record_usage_response = cls(
            event_id=event_id,
            suspended=suspended,
            agent_id=agent_id,
            billed_cost_micros=billed_cost_micros,
            new_balance_micros=new_balance_micros,
            parent_task_id=parent_task_id,
            pricing_provenance=pricing_provenance,
            provider_cost_micros=provider_cost_micros,
            service_id=service_id,
            stop=stop,
            stop_context=stop_context,
            stop_reason=stop_reason,
            stop_scope=stop_scope,
            task_id=task_id,
            task_total_billed_cost_micros=task_total_billed_cost_micros,
            task_total_provider_cost_micros=task_total_provider_cost_micros,
            uncosted_metrics=uncosted_metrics,
            units=units,
            usage_metrics=usage_metrics,
        )


        record_usage_response.additional_properties = d
        return record_usage_response

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
