from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.usage_event_detail_out_costing_status import UsageEventDetailOutCostingStatus
from ..models.usage_event_detail_out_measurements_status import UsageEventDetailOutMeasurementsStatus
from ..models.usage_event_detail_out_not_applicable_reason_type_0 import UsageEventDetailOutNotApplicableReasonType0
from ..models.usage_event_detail_out_pricing_method_type_0 import UsageEventDetailOutPricingMethodType0
from ..models.usage_event_detail_out_pricing_receipt_subject_type_type_0 import UsageEventDetailOutPricingReceiptSubjectTypeType0
from ..models.usage_event_detail_out_pricing_status import UsageEventDetailOutPricingStatus
from ..models.usage_event_detail_out_unresolved_reason_type_0 import UsageEventDetailOutUnresolvedReasonType0
from ..types import UNSET, Unset
from typing import cast
from uuid import UUID

if TYPE_CHECKING:
  from ..models.usage_event_detail_out_grouping_fields import UsageEventDetailOutGroupingFields
  from ..models.usage_event_detail_out_measurements import UsageEventDetailOutMeasurements
  from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
  from ..models.usage_event_detail_out_pricing_receipt import UsageEventDetailOutPricingReceipt





T = TypeVar("T", bound="UsageEventDetailOut")



@_attrs_define
class UsageEventDetailOut:
    """ 
        Attributes:
            costing_status (UsageEventDetailOutCostingStatus):
            created_at (str):
            effective_at (str):
            id (UUID):
            idempotency_key (str):
            measurements_status (UsageEventDetailOutMeasurementsStatus):
            pricing_status (UsageEventDetailOutPricingStatus):
            request_id (str):
            billed_cost_micros (int | None | Unset):
            claimed_provider_cost_micros (int | None | Unset): What the caller believes this call cost. Diagnostic only,
                recorded as stated and never COGS: it is never rated, never summed into a cost total, and never becomes the
                supplier cost beside it. `provider_cost_micros` is the supplier's own reported figure and the only one UBB
                treats as cost.
            currency (str | Unset):  Default: 'usd'.
            event_type (str | Unset):  Default: ''.
            grouping_fields (UsageEventDetailOutGroupingFields | Unset):
            measurements (UsageEventDetailOutMeasurements | Unset):
            metadata (UsageEventDetailOutMetadata | Unset):
            not_applicable_reason (None | Unset | UsageEventDetailOutNotApplicableReasonType0):
            pricing_method (None | Unset | UsageEventDetailOutPricingMethodType0):
            pricing_receipt (UsageEventDetailOutPricingReceipt | Unset): The Pricing Receipt: the authoritative record of
                the ECONOMIC RESOLUTION behind this event's amounts — what UBB resolved, how, and as of when. It is not a
                guarantee that customer revenue exists and it is not evidence a customer was charged: a metering-only tenant has
                a receipt for every event it records. The record carries its own shape version (receipt_schema_version) and the
                version of the engine that computed it (pricing_engine_version), the subject it explains, a costing and a
                pricing section holding their method, status and detail BY VALUE, the totals, and a provenance section of cross-
                reference ids that nothing reads to reconstruct an amount.
            pricing_receipt_subject_type (None | Unset | UsageEventDetailOutPricingReceiptSubjectTypeType0):
            provider (str | Unset):  Default: ''.
            provider_cost_micros (int | None | Unset):
            stop_context (list[Any] | None | Unset):
            task_id (None | str | Unset):
            unresolved_reason (None | Unset | UsageEventDetailOutUnresolvedReasonType0):
     """

    costing_status: UsageEventDetailOutCostingStatus
    created_at: str
    effective_at: str
    id: UUID
    idempotency_key: str
    measurements_status: UsageEventDetailOutMeasurementsStatus
    pricing_status: UsageEventDetailOutPricingStatus
    request_id: str
    billed_cost_micros: int | None | Unset = UNSET
    claimed_provider_cost_micros: int | None | Unset = UNSET
    currency: str | Unset = 'usd'
    event_type: str | Unset = ''
    grouping_fields: UsageEventDetailOutGroupingFields | Unset = UNSET
    measurements: UsageEventDetailOutMeasurements | Unset = UNSET
    metadata: UsageEventDetailOutMetadata | Unset = UNSET
    not_applicable_reason: None | Unset | UsageEventDetailOutNotApplicableReasonType0 = UNSET
    pricing_method: None | Unset | UsageEventDetailOutPricingMethodType0 = UNSET
    pricing_receipt: UsageEventDetailOutPricingReceipt | Unset = UNSET
    pricing_receipt_subject_type: None | Unset | UsageEventDetailOutPricingReceiptSubjectTypeType0 = UNSET
    provider: str | Unset = ''
    provider_cost_micros: int | None | Unset = UNSET
    stop_context: list[Any] | None | Unset = UNSET
    task_id: None | str | Unset = UNSET
    unresolved_reason: None | Unset | UsageEventDetailOutUnresolvedReasonType0 = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_event_detail_out_grouping_fields import UsageEventDetailOutGroupingFields
        from ..models.usage_event_detail_out_measurements import UsageEventDetailOutMeasurements
        from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
        from ..models.usage_event_detail_out_pricing_receipt import UsageEventDetailOutPricingReceipt
        costing_status = self.costing_status.value

        created_at = self.created_at

        effective_at = self.effective_at

        id = str(self.id)

        idempotency_key = self.idempotency_key

        measurements_status = self.measurements_status.value

        pricing_status = self.pricing_status.value

        request_id = self.request_id

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

        not_applicable_reason: None | str | Unset
        if isinstance(self.not_applicable_reason, Unset):
            not_applicable_reason = UNSET
        elif isinstance(self.not_applicable_reason, UsageEventDetailOutNotApplicableReasonType0):
            not_applicable_reason = self.not_applicable_reason.value
        else:
            not_applicable_reason = self.not_applicable_reason

        pricing_method: None | str | Unset
        if isinstance(self.pricing_method, Unset):
            pricing_method = UNSET
        elif isinstance(self.pricing_method, UsageEventDetailOutPricingMethodType0):
            pricing_method = self.pricing_method.value
        else:
            pricing_method = self.pricing_method

        pricing_receipt: dict[str, Any] | Unset = UNSET
        if not isinstance(self.pricing_receipt, Unset):
            pricing_receipt = self.pricing_receipt.to_dict()

        pricing_receipt_subject_type: None | str | Unset
        if isinstance(self.pricing_receipt_subject_type, Unset):
            pricing_receipt_subject_type = UNSET
        elif isinstance(self.pricing_receipt_subject_type, UsageEventDetailOutPricingReceiptSubjectTypeType0):
            pricing_receipt_subject_type = self.pricing_receipt_subject_type.value
        else:
            pricing_receipt_subject_type = self.pricing_receipt_subject_type

        provider = self.provider

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros

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

        unresolved_reason: None | str | Unset
        if isinstance(self.unresolved_reason, Unset):
            unresolved_reason = UNSET
        elif isinstance(self.unresolved_reason, UsageEventDetailOutUnresolvedReasonType0):
            unresolved_reason = self.unresolved_reason.value
        else:
            unresolved_reason = self.unresolved_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "costing_status": costing_status,
            "created_at": created_at,
            "effective_at": effective_at,
            "id": id,
            "idempotency_key": idempotency_key,
            "measurements_status": measurements_status,
            "pricing_status": pricing_status,
            "request_id": request_id,
        })
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if claimed_provider_cost_micros is not UNSET:
            field_dict["claimed_provider_cost_micros"] = claimed_provider_cost_micros
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
        if not_applicable_reason is not UNSET:
            field_dict["not_applicable_reason"] = not_applicable_reason
        if pricing_method is not UNSET:
            field_dict["pricing_method"] = pricing_method
        if pricing_receipt is not UNSET:
            field_dict["pricing_receipt"] = pricing_receipt
        if pricing_receipt_subject_type is not UNSET:
            field_dict["pricing_receipt_subject_type"] = pricing_receipt_subject_type
        if provider is not UNSET:
            field_dict["provider"] = provider
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
        if stop_context is not UNSET:
            field_dict["stop_context"] = stop_context
        if task_id is not UNSET:
            field_dict["task_id"] = task_id
        if unresolved_reason is not UNSET:
            field_dict["unresolved_reason"] = unresolved_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_event_detail_out_grouping_fields import UsageEventDetailOutGroupingFields
        from ..models.usage_event_detail_out_measurements import UsageEventDetailOutMeasurements
        from ..models.usage_event_detail_out_metadata import UsageEventDetailOutMetadata
        from ..models.usage_event_detail_out_pricing_receipt import UsageEventDetailOutPricingReceipt
        d = dict(src_dict)
        costing_status = UsageEventDetailOutCostingStatus(d.pop("costing_status"))




        created_at = d.pop("created_at")

        effective_at = d.pop("effective_at")

        id = UUID(d.pop("id"))




        idempotency_key = d.pop("idempotency_key")

        measurements_status = UsageEventDetailOutMeasurementsStatus(d.pop("measurements_status"))




        pricing_status = UsageEventDetailOutPricingStatus(d.pop("pricing_status"))




        request_id = d.pop("request_id")

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




        def _parse_not_applicable_reason(data: object) -> None | Unset | UsageEventDetailOutNotApplicableReasonType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                not_applicable_reason_type_0 = UsageEventDetailOutNotApplicableReasonType0(data)



                return not_applicable_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageEventDetailOutNotApplicableReasonType0, data)

        not_applicable_reason = _parse_not_applicable_reason(d.pop("not_applicable_reason", UNSET))


        def _parse_pricing_method(data: object) -> None | Unset | UsageEventDetailOutPricingMethodType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_method_type_0 = UsageEventDetailOutPricingMethodType0(data)



                return pricing_method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageEventDetailOutPricingMethodType0, data)

        pricing_method = _parse_pricing_method(d.pop("pricing_method", UNSET))


        _pricing_receipt = d.pop("pricing_receipt", UNSET)
        pricing_receipt: UsageEventDetailOutPricingReceipt | Unset
        if isinstance(_pricing_receipt,  Unset):
            pricing_receipt = UNSET
        else:
            pricing_receipt = UsageEventDetailOutPricingReceipt.from_dict(_pricing_receipt)




        def _parse_pricing_receipt_subject_type(data: object) -> None | Unset | UsageEventDetailOutPricingReceiptSubjectTypeType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_receipt_subject_type_type_0 = UsageEventDetailOutPricingReceiptSubjectTypeType0(data)



                return pricing_receipt_subject_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageEventDetailOutPricingReceiptSubjectTypeType0, data)

        pricing_receipt_subject_type = _parse_pricing_receipt_subject_type(d.pop("pricing_receipt_subject_type", UNSET))


        provider = d.pop("provider", UNSET)

        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


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


        def _parse_unresolved_reason(data: object) -> None | Unset | UsageEventDetailOutUnresolvedReasonType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                unresolved_reason_type_0 = UsageEventDetailOutUnresolvedReasonType0(data)



                return unresolved_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageEventDetailOutUnresolvedReasonType0, data)

        unresolved_reason = _parse_unresolved_reason(d.pop("unresolved_reason", UNSET))


        usage_event_detail_out = cls(
            costing_status=costing_status,
            created_at=created_at,
            effective_at=effective_at,
            id=id,
            idempotency_key=idempotency_key,
            measurements_status=measurements_status,
            pricing_status=pricing_status,
            request_id=request_id,
            billed_cost_micros=billed_cost_micros,
            claimed_provider_cost_micros=claimed_provider_cost_micros,
            currency=currency,
            event_type=event_type,
            grouping_fields=grouping_fields,
            measurements=measurements,
            metadata=metadata,
            not_applicable_reason=not_applicable_reason,
            pricing_method=pricing_method,
            pricing_receipt=pricing_receipt,
            pricing_receipt_subject_type=pricing_receipt_subject_type,
            provider=provider,
            provider_cost_micros=provider_cost_micros,
            stop_context=stop_context,
            task_id=task_id,
            unresolved_reason=unresolved_reason,
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
