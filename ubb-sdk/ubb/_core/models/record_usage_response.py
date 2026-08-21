from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.record_usage_response_costing_status import RecordUsageResponseCostingStatus
from ..models.record_usage_response_not_applicable_reason_type_0 import RecordUsageResponseNotApplicableReasonType0
from ..models.record_usage_response_pricing_method_type_0 import RecordUsageResponsePricingMethodType0
from ..models.record_usage_response_pricing_receipt_subject_type_type_0 import RecordUsageResponsePricingReceiptSubjectTypeType0
from ..models.record_usage_response_pricing_status import RecordUsageResponsePricingStatus
from ..models.record_usage_response_unresolved_reason_type_0 import RecordUsageResponseUnresolvedReasonType0
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.record_usage_response_grouping_fields import RecordUsageResponseGroupingFields
  from ..models.record_usage_response_measurements_type_0 import RecordUsageResponseMeasurementsType0
  from ..models.record_usage_response_pricing_receipt_type_0 import RecordUsageResponsePricingReceiptType0





T = TypeVar("T", bound="RecordUsageResponse")



@_attrs_define
class RecordUsageResponse:
    """ 
        Attributes:
            costing_status (RecordUsageResponseCostingStatus):
            event_id (str):
            pricing_status (RecordUsageResponsePricingStatus):
            suspended (bool):
            billed_cost_micros (int | None | Unset):
            claimed_provider_cost_micros (int | None | Unset): What the caller believes this call cost. Diagnostic only,
                recorded as stated and never COGS: it is never rated, never summed into a cost total, and never becomes the
                supplier cost beside it. `provider_cost_micros` is the supplier's own reported figure and the only one UBB
                treats as cost.
            grouping_fields (RecordUsageResponseGroupingFields | Unset):
            measurements (None | RecordUsageResponseMeasurementsType0 | Unset):
            new_balance_micros (int | None | Unset):
            not_applicable_reason (None | RecordUsageResponseNotApplicableReasonType0 | Unset):
            parent_task_id (None | str | Unset):
            pricing_method (None | RecordUsageResponsePricingMethodType0 | Unset):
            pricing_receipt (None | RecordUsageResponsePricingReceiptType0 | Unset): The Pricing Receipt: the authoritative
                record of the ECONOMIC RESOLUTION behind this event's amounts — what UBB resolved, how, and as of when. It is
                not a guarantee that customer revenue exists and it is not evidence a customer was charged: a metering-only
                tenant has a receipt for every event it records. The record carries its own shape version
                (receipt_schema_version) and the version of the engine that computed it (pricing_engine_version), the subject it
                explains, a costing and a pricing section holding their method, status and detail BY VALUE, the totals, and a
                provenance section of cross-reference ids that nothing reads to reconstruct an amount.
            pricing_receipt_subject_type (None | RecordUsageResponsePricingReceiptSubjectTypeType0 | Unset):
            provider_cost_micros (int | None | Unset):
            stop (bool | Unset):  Default: False.
            stop_context (list[Any] | None | Unset):
            stop_reason (None | str | Unset):
            stop_scope (None | str | Unset):
            task_id (None | str | Unset):
            task_total_billed_cost_micros (int | None | Unset):
            task_total_provider_cost_micros (int | None | Unset):
            task_total_unpriced_event_count (int | None | Unset):
            task_total_unresolved_event_count (int | None | Unset):
            uncosted_measurement_keys (list[str] | Unset):
            unresolved_reason (None | RecordUsageResponseUnresolvedReasonType0 | Unset):
     """

    costing_status: RecordUsageResponseCostingStatus
    event_id: str
    pricing_status: RecordUsageResponsePricingStatus
    suspended: bool
    billed_cost_micros: int | None | Unset = UNSET
    claimed_provider_cost_micros: int | None | Unset = UNSET
    grouping_fields: RecordUsageResponseGroupingFields | Unset = UNSET
    measurements: None | RecordUsageResponseMeasurementsType0 | Unset = UNSET
    new_balance_micros: int | None | Unset = UNSET
    not_applicable_reason: None | RecordUsageResponseNotApplicableReasonType0 | Unset = UNSET
    parent_task_id: None | str | Unset = UNSET
    pricing_method: None | RecordUsageResponsePricingMethodType0 | Unset = UNSET
    pricing_receipt: None | RecordUsageResponsePricingReceiptType0 | Unset = UNSET
    pricing_receipt_subject_type: None | RecordUsageResponsePricingReceiptSubjectTypeType0 | Unset = UNSET
    provider_cost_micros: int | None | Unset = UNSET
    stop: bool | Unset = False
    stop_context: list[Any] | None | Unset = UNSET
    stop_reason: None | str | Unset = UNSET
    stop_scope: None | str | Unset = UNSET
    task_id: None | str | Unset = UNSET
    task_total_billed_cost_micros: int | None | Unset = UNSET
    task_total_provider_cost_micros: int | None | Unset = UNSET
    task_total_unpriced_event_count: int | None | Unset = UNSET
    task_total_unresolved_event_count: int | None | Unset = UNSET
    uncosted_measurement_keys: list[str] | Unset = UNSET
    unresolved_reason: None | RecordUsageResponseUnresolvedReasonType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.record_usage_response_grouping_fields import RecordUsageResponseGroupingFields
        from ..models.record_usage_response_measurements_type_0 import RecordUsageResponseMeasurementsType0
        from ..models.record_usage_response_pricing_receipt_type_0 import RecordUsageResponsePricingReceiptType0
        costing_status = self.costing_status.value

        event_id = self.event_id

        pricing_status = self.pricing_status.value

        suspended = self.suspended

        billed_cost_micros: int | None | Unset
        if isinstance(self.billed_cost_micros, Unset):
            billed_cost_micros = UNSET
        else:
            billed_cost_micros = self.billed_cost_micros

        claimed_provider_cost_micros: int | None | Unset
        if isinstance(self.claimed_provider_cost_micros, Unset):
            claimed_provider_cost_micros = UNSET
        else:
            claimed_provider_cost_micros = self.claimed_provider_cost_micros

        grouping_fields: dict[str, Any] | Unset = UNSET
        if not isinstance(self.grouping_fields, Unset):
            grouping_fields = self.grouping_fields.to_dict()

        measurements: dict[str, Any] | None | Unset
        if isinstance(self.measurements, Unset):
            measurements = UNSET
        elif isinstance(self.measurements, RecordUsageResponseMeasurementsType0):
            measurements = self.measurements.to_dict()
        else:
            measurements = self.measurements

        new_balance_micros: int | None | Unset
        if isinstance(self.new_balance_micros, Unset):
            new_balance_micros = UNSET
        else:
            new_balance_micros = self.new_balance_micros

        not_applicable_reason: None | str | Unset
        if isinstance(self.not_applicable_reason, Unset):
            not_applicable_reason = UNSET
        elif isinstance(self.not_applicable_reason, RecordUsageResponseNotApplicableReasonType0):
            not_applicable_reason = self.not_applicable_reason.value
        else:
            not_applicable_reason = self.not_applicable_reason

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        else:
            parent_task_id = self.parent_task_id

        pricing_method: None | str | Unset
        if isinstance(self.pricing_method, Unset):
            pricing_method = UNSET
        elif isinstance(self.pricing_method, RecordUsageResponsePricingMethodType0):
            pricing_method = self.pricing_method.value
        else:
            pricing_method = self.pricing_method

        pricing_receipt: dict[str, Any] | None | Unset
        if isinstance(self.pricing_receipt, Unset):
            pricing_receipt = UNSET
        elif isinstance(self.pricing_receipt, RecordUsageResponsePricingReceiptType0):
            pricing_receipt = self.pricing_receipt.to_dict()
        else:
            pricing_receipt = self.pricing_receipt

        pricing_receipt_subject_type: None | str | Unset
        if isinstance(self.pricing_receipt_subject_type, Unset):
            pricing_receipt_subject_type = UNSET
        elif isinstance(self.pricing_receipt_subject_type, RecordUsageResponsePricingReceiptSubjectTypeType0):
            pricing_receipt_subject_type = self.pricing_receipt_subject_type.value
        else:
            pricing_receipt_subject_type = self.pricing_receipt_subject_type

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros

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

        task_total_unpriced_event_count: int | None | Unset
        if isinstance(self.task_total_unpriced_event_count, Unset):
            task_total_unpriced_event_count = UNSET
        else:
            task_total_unpriced_event_count = self.task_total_unpriced_event_count

        task_total_unresolved_event_count: int | None | Unset
        if isinstance(self.task_total_unresolved_event_count, Unset):
            task_total_unresolved_event_count = UNSET
        else:
            task_total_unresolved_event_count = self.task_total_unresolved_event_count

        uncosted_measurement_keys: list[str] | Unset = UNSET
        if not isinstance(self.uncosted_measurement_keys, Unset):
            uncosted_measurement_keys = self.uncosted_measurement_keys



        unresolved_reason: None | str | Unset
        if isinstance(self.unresolved_reason, Unset):
            unresolved_reason = UNSET
        elif isinstance(self.unresolved_reason, RecordUsageResponseUnresolvedReasonType0):
            unresolved_reason = self.unresolved_reason.value
        else:
            unresolved_reason = self.unresolved_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "costing_status": costing_status,
            "event_id": event_id,
            "pricing_status": pricing_status,
            "suspended": suspended,
        })
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if claimed_provider_cost_micros is not UNSET:
            field_dict["claimed_provider_cost_micros"] = claimed_provider_cost_micros
        if grouping_fields is not UNSET:
            field_dict["grouping_fields"] = grouping_fields
        if measurements is not UNSET:
            field_dict["measurements"] = measurements
        if new_balance_micros is not UNSET:
            field_dict["new_balance_micros"] = new_balance_micros
        if not_applicable_reason is not UNSET:
            field_dict["not_applicable_reason"] = not_applicable_reason
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if pricing_method is not UNSET:
            field_dict["pricing_method"] = pricing_method
        if pricing_receipt is not UNSET:
            field_dict["pricing_receipt"] = pricing_receipt
        if pricing_receipt_subject_type is not UNSET:
            field_dict["pricing_receipt_subject_type"] = pricing_receipt_subject_type
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
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
        if task_total_unpriced_event_count is not UNSET:
            field_dict["task_total_unpriced_event_count"] = task_total_unpriced_event_count
        if task_total_unresolved_event_count is not UNSET:
            field_dict["task_total_unresolved_event_count"] = task_total_unresolved_event_count
        if uncosted_measurement_keys is not UNSET:
            field_dict["uncosted_measurement_keys"] = uncosted_measurement_keys
        if unresolved_reason is not UNSET:
            field_dict["unresolved_reason"] = unresolved_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.record_usage_response_grouping_fields import RecordUsageResponseGroupingFields
        from ..models.record_usage_response_measurements_type_0 import RecordUsageResponseMeasurementsType0
        from ..models.record_usage_response_pricing_receipt_type_0 import RecordUsageResponsePricingReceiptType0
        d = dict(src_dict)
        costing_status = RecordUsageResponseCostingStatus(d.pop("costing_status"))




        event_id = d.pop("event_id")

        pricing_status = RecordUsageResponsePricingStatus(d.pop("pricing_status"))




        suspended = d.pop("suspended")

        def _parse_billed_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        billed_cost_micros = _parse_billed_cost_micros(d.pop("billed_cost_micros", UNSET))


        def _parse_claimed_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        claimed_provider_cost_micros = _parse_claimed_provider_cost_micros(d.pop("claimed_provider_cost_micros", UNSET))


        _grouping_fields = d.pop("grouping_fields", UNSET)
        grouping_fields: RecordUsageResponseGroupingFields | Unset
        if isinstance(_grouping_fields,  Unset):
            grouping_fields = UNSET
        else:
            grouping_fields = RecordUsageResponseGroupingFields.from_dict(_grouping_fields)




        def _parse_measurements(data: object) -> None | RecordUsageResponseMeasurementsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                measurements_type_0 = RecordUsageResponseMeasurementsType0.from_dict(data)



                return measurements_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponseMeasurementsType0 | Unset, data)

        measurements = _parse_measurements(d.pop("measurements", UNSET))


        def _parse_new_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        new_balance_micros = _parse_new_balance_micros(d.pop("new_balance_micros", UNSET))


        def _parse_not_applicable_reason(data: object) -> None | RecordUsageResponseNotApplicableReasonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                not_applicable_reason_type_0 = RecordUsageResponseNotApplicableReasonType0(data)



                return not_applicable_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponseNotApplicableReasonType0 | Unset, data)

        not_applicable_reason = _parse_not_applicable_reason(d.pop("not_applicable_reason", UNSET))


        def _parse_parent_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_pricing_method(data: object) -> None | RecordUsageResponsePricingMethodType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_method_type_0 = RecordUsageResponsePricingMethodType0(data)



                return pricing_method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponsePricingMethodType0 | Unset, data)

        pricing_method = _parse_pricing_method(d.pop("pricing_method", UNSET))


        def _parse_pricing_receipt(data: object) -> None | RecordUsageResponsePricingReceiptType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                pricing_receipt_type_0 = RecordUsageResponsePricingReceiptType0.from_dict(data)



                return pricing_receipt_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponsePricingReceiptType0 | Unset, data)

        pricing_receipt = _parse_pricing_receipt(d.pop("pricing_receipt", UNSET))


        def _parse_pricing_receipt_subject_type(data: object) -> None | RecordUsageResponsePricingReceiptSubjectTypeType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_receipt_subject_type_type_0 = RecordUsageResponsePricingReceiptSubjectTypeType0(data)



                return pricing_receipt_subject_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponsePricingReceiptSubjectTypeType0 | Unset, data)

        pricing_receipt_subject_type = _parse_pricing_receipt_subject_type(d.pop("pricing_receipt_subject_type", UNSET))


        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


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


        def _parse_task_total_unpriced_event_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        task_total_unpriced_event_count = _parse_task_total_unpriced_event_count(d.pop("task_total_unpriced_event_count", UNSET))


        def _parse_task_total_unresolved_event_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        task_total_unresolved_event_count = _parse_task_total_unresolved_event_count(d.pop("task_total_unresolved_event_count", UNSET))


        uncosted_measurement_keys = cast(list[str], d.pop("uncosted_measurement_keys", UNSET))


        def _parse_unresolved_reason(data: object) -> None | RecordUsageResponseUnresolvedReasonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                unresolved_reason_type_0 = RecordUsageResponseUnresolvedReasonType0(data)



                return unresolved_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponseUnresolvedReasonType0 | Unset, data)

        unresolved_reason = _parse_unresolved_reason(d.pop("unresolved_reason", UNSET))


        record_usage_response = cls(
            costing_status=costing_status,
            event_id=event_id,
            pricing_status=pricing_status,
            suspended=suspended,
            billed_cost_micros=billed_cost_micros,
            claimed_provider_cost_micros=claimed_provider_cost_micros,
            grouping_fields=grouping_fields,
            measurements=measurements,
            new_balance_micros=new_balance_micros,
            not_applicable_reason=not_applicable_reason,
            parent_task_id=parent_task_id,
            pricing_method=pricing_method,
            pricing_receipt=pricing_receipt,
            pricing_receipt_subject_type=pricing_receipt_subject_type,
            provider_cost_micros=provider_cost_micros,
            stop=stop,
            stop_context=stop_context,
            stop_reason=stop_reason,
            stop_scope=stop_scope,
            task_id=task_id,
            task_total_billed_cost_micros=task_total_billed_cost_micros,
            task_total_provider_cost_micros=task_total_provider_cost_micros,
            task_total_unpriced_event_count=task_total_unpriced_event_count,
            task_total_unresolved_event_count=task_total_unresolved_event_count,
            uncosted_measurement_keys=uncosted_measurement_keys,
            unresolved_reason=unresolved_reason,
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
