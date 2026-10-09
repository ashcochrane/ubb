from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.usage_batch_item_response_ceiling_status_type_0 import UsageBatchItemResponseCeilingStatusType0
from ..models.usage_batch_item_response_costing_status_type_0 import UsageBatchItemResponseCostingStatusType0
from ..models.usage_batch_item_response_not_applicable_reason_type_0 import UsageBatchItemResponseNotApplicableReasonType0
from ..models.usage_batch_item_response_pricing_method_type_0 import UsageBatchItemResponsePricingMethodType0
from ..models.usage_batch_item_response_pricing_receipt_subject_type_type_0 import UsageBatchItemResponsePricingReceiptSubjectTypeType0
from ..models.usage_batch_item_response_pricing_status_type_0 import UsageBatchItemResponsePricingStatusType0
from ..models.usage_batch_item_response_unresolved_reason_type_0 import UsageBatchItemResponseUnresolvedReasonType0
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.usage_batch_item_response_grouping_fields import UsageBatchItemResponseGroupingFields
  from ..models.usage_batch_item_response_measurements_type_0 import UsageBatchItemResponseMeasurementsType0
  from ..models.usage_batch_item_response_pricing_receipt_type_0 import UsageBatchItemResponsePricingReceiptType0





T = TypeVar("T", bound="UsageBatchItemResponse")



@_attrs_define
class UsageBatchItemResponse:
    """ One batch item's verdict (#569, ADR-0019 §8) — the field set #78
    unified across the batch route and the async ingest route, which slice 1
    deleted; this is the surviving shape, TYPED. An accepted item (`accepted: true`) is the
    single route's acknowledgement, field for field and with the meaning
    `RecordUsageResponse` publishes for each. A rejected item was never
    recorded: it carries `accepted: false`, a registry `code` and a
    `detail`, `stop` false, every stop fact null and no acknowledgement
    field set.

        Attributes:
            accepted (bool):
            billed_cost_micros (int | None | Unset):
            ceiling_remaining_micros (int | None | Unset):
            ceiling_status (None | Unset | UsageBatchItemResponseCeilingStatusType0):
            ceiling_used_percentage (int | None | Unset):
            claimed_provider_cost_micros (int | None | Unset): What the caller believes this call cost. Diagnostic only,
                recorded as stated and never COGS: it is never rated, never summed into a cost total, and never becomes the
                supplier cost beside it. The supplier cost UBB treats as COGS is the one it resolves, published as
                `provider_cost_micros` on a response.
            code (None | str | Unset):
            costing_status (None | Unset | UsageBatchItemResponseCostingStatusType0):
            detail (None | str | Unset):
            event_id (None | str | Unset):
            grouping_fields (UsageBatchItemResponseGroupingFields | Unset):
            measurements (None | Unset | UsageBatchItemResponseMeasurementsType0):
            new_balance_micros (int | None | Unset):
            not_applicable_reason (None | Unset | UsageBatchItemResponseNotApplicableReasonType0):
            parent_task_id (None | str | Unset):
            pricing_method (None | Unset | UsageBatchItemResponsePricingMethodType0):
            pricing_receipt (None | Unset | UsageBatchItemResponsePricingReceiptType0): The Pricing Receipt: the
                authoritative record of the ECONOMIC RESOLUTION behind this event's amounts — what UBB resolved, how, and as of
                when. It is not a guarantee that customer revenue exists and it is not evidence a customer was charged: a
                metering-only tenant has a receipt for every event it records. The record carries its own shape version
                (receipt_schema_version) and the version of the engine that computed it (pricing_engine_version), the subject it
                explains, a costing and a pricing section holding their method, status and detail BY VALUE, the totals
                (`provider_cost_micros` and `billed_cost_micros`: the amount each section resolved, null where it is not
                settled), and a provenance section of cross-reference ids that nothing reads to reconstruct an amount.
            pricing_receipt_subject_type (None | Unset | UsageBatchItemResponsePricingReceiptSubjectTypeType0):
            pricing_status (None | Unset | UsageBatchItemResponsePricingStatusType0):
            provider_cost_micros (int | None | Unset): The supplier cost (COGS) UBB resolved for this event: the one
                canonical amount, whichever valid source supplied it — worked out from Cost Rates, or a reported figure that
                arrived on the transport the Event Type's publication admitted when the event was recorded
                (`provider_cost_micros` or `provider_response_cost_micros` on the recording request) — and zero on the posting
                that projects a Charge, which has no supplier behind it. `costing_status` beside it says whether it is settled:
                the amount is null wherever that status is not `known`.
            stop (bool | Unset):  Default: False.
            stop_bound_micros (int | None | Unset): The monetary bound the stop named in `stop_reason` was measured against,
                as it stood when that stop was established. For `task_cogs_ceiling`: the governing unit of work's pinned COGS
                ceiling — the unit `stop_scope` names, so scope `task` on contained work's report is its parent's. For
                `customer_spend_pool`: the Pool's stop line (its cap times its hard-stop percentage, over 100), for the customer
                whose Pool it is. For `hard_floor`: the wallet's floor as a balance — the negated minimum balance, 0 or below,
                where 0 is a real floor. Null when nothing stopped and for `task_not_active`, and never 0 for 'does not apply'.
                Later configuration does not move it, and on an idempotent replay it is the original acknowledgement's.
            stop_context (list[Any] | None | Unset):
            stop_measured_micros (int | None | Unset): The monetary amount assessed against `stop_bound_micros` when the
                stop was established. For `task_cogs_ceiling`: the governing unit of work's supplier cost (COGS) total, at or
                above the bound. For `customer_spend_pool`: that customer's month-to-date billed charges, at or above it. For
                `hard_floor`: the wallet balance, below it. For a customer-wide stop already standing when this report arrived,
                it is the figure the stop opened on, not where the counter stands now. Null when nothing stopped and for
                `task_not_active`. On an idempotent replay, the original acknowledgement's.
            stop_reason (None | str | Unset): Why UBB is asking you to stop: which bound was reached, in the registry's
                words (the values under `x-ubb-known-values`), or `task_not_active` — the one verdict that is not a bound, which
                UBB produces and the registry deliberately does not list: this report landed on a unit of work that had already
                ended, and it was still recorded and charged. Null when `stop` is false. Open: accept a reason not listed here.
            stop_scope (None | str | Unset):
            suspended (bool | None | Unset):
            task_id (None | str | Unset):
            task_total_billed_cost_micros (int | None | Unset):
            task_total_provider_cost_micros (int | None | Unset):
            task_total_unpriced_event_count (int | None | Unset):
            task_total_unresolved_event_count (int | None | Unset):
            trigger_source (None | str | Unset): The mechanism that applied the stop this acknowledgement names — never its
                cause, which is `stop_reason`. A unit of work's ceiling (`task_cogs_ceiling`) is crossed by this report:
                `usage_ingest`. A customer-wide stop (`customer_spend_pool`, `hard_floor`) names the mechanism that OPENED the
                stop episode this report fell in: `usage_ingest` (a usage report's recording or its drawdown),
                `enforcement_patrol` (the periodic reconcile) or `charge_projection` (the drawdown of a delivered fixed-price
                unit's Charge). Null when nothing stopped, and for `task_not_active`, where no mechanism applied a stop on this
                report. On an idempotent replay, the original acknowledgement's.
            uncosted_measurement_keys (list[str] | Unset):
            unresolved_reason (None | Unset | UsageBatchItemResponseUnresolvedReasonType0):
     """

    accepted: bool
    billed_cost_micros: int | None | Unset = UNSET
    ceiling_remaining_micros: int | None | Unset = UNSET
    ceiling_status: None | Unset | UsageBatchItemResponseCeilingStatusType0 = UNSET
    ceiling_used_percentage: int | None | Unset = UNSET
    claimed_provider_cost_micros: int | None | Unset = UNSET
    code: None | str | Unset = UNSET
    costing_status: None | Unset | UsageBatchItemResponseCostingStatusType0 = UNSET
    detail: None | str | Unset = UNSET
    event_id: None | str | Unset = UNSET
    grouping_fields: UsageBatchItemResponseGroupingFields | Unset = UNSET
    measurements: None | Unset | UsageBatchItemResponseMeasurementsType0 = UNSET
    new_balance_micros: int | None | Unset = UNSET
    not_applicable_reason: None | Unset | UsageBatchItemResponseNotApplicableReasonType0 = UNSET
    parent_task_id: None | str | Unset = UNSET
    pricing_method: None | Unset | UsageBatchItemResponsePricingMethodType0 = UNSET
    pricing_receipt: None | Unset | UsageBatchItemResponsePricingReceiptType0 = UNSET
    pricing_receipt_subject_type: None | Unset | UsageBatchItemResponsePricingReceiptSubjectTypeType0 = UNSET
    pricing_status: None | Unset | UsageBatchItemResponsePricingStatusType0 = UNSET
    provider_cost_micros: int | None | Unset = UNSET
    stop: bool | Unset = False
    stop_bound_micros: int | None | Unset = UNSET
    stop_context: list[Any] | None | Unset = UNSET
    stop_measured_micros: int | None | Unset = UNSET
    stop_reason: None | str | Unset = UNSET
    stop_scope: None | str | Unset = UNSET
    suspended: bool | None | Unset = UNSET
    task_id: None | str | Unset = UNSET
    task_total_billed_cost_micros: int | None | Unset = UNSET
    task_total_provider_cost_micros: int | None | Unset = UNSET
    task_total_unpriced_event_count: int | None | Unset = UNSET
    task_total_unresolved_event_count: int | None | Unset = UNSET
    trigger_source: None | str | Unset = UNSET
    uncosted_measurement_keys: list[str] | Unset = UNSET
    unresolved_reason: None | Unset | UsageBatchItemResponseUnresolvedReasonType0 = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_batch_item_response_grouping_fields import UsageBatchItemResponseGroupingFields
        from ..models.usage_batch_item_response_measurements_type_0 import UsageBatchItemResponseMeasurementsType0
        from ..models.usage_batch_item_response_pricing_receipt_type_0 import UsageBatchItemResponsePricingReceiptType0
        accepted = self.accepted

        billed_cost_micros: int | None | Unset
        if isinstance(self.billed_cost_micros, Unset):
            billed_cost_micros = UNSET
        else:
            billed_cost_micros = self.billed_cost_micros

        ceiling_remaining_micros: int | None | Unset
        if isinstance(self.ceiling_remaining_micros, Unset):
            ceiling_remaining_micros = UNSET
        else:
            ceiling_remaining_micros = self.ceiling_remaining_micros

        ceiling_status: None | str | Unset
        if isinstance(self.ceiling_status, Unset):
            ceiling_status = UNSET
        elif isinstance(self.ceiling_status, UsageBatchItemResponseCeilingStatusType0):
            ceiling_status = self.ceiling_status.value
        else:
            ceiling_status = self.ceiling_status

        ceiling_used_percentage: int | None | Unset
        if isinstance(self.ceiling_used_percentage, Unset):
            ceiling_used_percentage = UNSET
        else:
            ceiling_used_percentage = self.ceiling_used_percentage

        claimed_provider_cost_micros: int | None | Unset
        if isinstance(self.claimed_provider_cost_micros, Unset):
            claimed_provider_cost_micros = UNSET
        else:
            claimed_provider_cost_micros = self.claimed_provider_cost_micros

        code: None | str | Unset
        if isinstance(self.code, Unset):
            code = UNSET
        else:
            code = self.code

        costing_status: None | str | Unset
        if isinstance(self.costing_status, Unset):
            costing_status = UNSET
        elif isinstance(self.costing_status, UsageBatchItemResponseCostingStatusType0):
            costing_status = self.costing_status.value
        else:
            costing_status = self.costing_status

        detail: None | str | Unset
        if isinstance(self.detail, Unset):
            detail = UNSET
        else:
            detail = self.detail

        event_id: None | str | Unset
        if isinstance(self.event_id, Unset):
            event_id = UNSET
        else:
            event_id = self.event_id

        grouping_fields: dict[str, Any] | Unset = UNSET
        if not isinstance(self.grouping_fields, Unset):
            grouping_fields = self.grouping_fields.to_dict()

        measurements: dict[str, Any] | None | Unset
        if isinstance(self.measurements, Unset):
            measurements = UNSET
        elif isinstance(self.measurements, UsageBatchItemResponseMeasurementsType0):
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
        elif isinstance(self.not_applicable_reason, UsageBatchItemResponseNotApplicableReasonType0):
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
        elif isinstance(self.pricing_method, UsageBatchItemResponsePricingMethodType0):
            pricing_method = self.pricing_method.value
        else:
            pricing_method = self.pricing_method

        pricing_receipt: dict[str, Any] | None | Unset
        if isinstance(self.pricing_receipt, Unset):
            pricing_receipt = UNSET
        elif isinstance(self.pricing_receipt, UsageBatchItemResponsePricingReceiptType0):
            pricing_receipt = self.pricing_receipt.to_dict()
        else:
            pricing_receipt = self.pricing_receipt

        pricing_receipt_subject_type: None | str | Unset
        if isinstance(self.pricing_receipt_subject_type, Unset):
            pricing_receipt_subject_type = UNSET
        elif isinstance(self.pricing_receipt_subject_type, UsageBatchItemResponsePricingReceiptSubjectTypeType0):
            pricing_receipt_subject_type = self.pricing_receipt_subject_type.value
        else:
            pricing_receipt_subject_type = self.pricing_receipt_subject_type

        pricing_status: None | str | Unset
        if isinstance(self.pricing_status, Unset):
            pricing_status = UNSET
        elif isinstance(self.pricing_status, UsageBatchItemResponsePricingStatusType0):
            pricing_status = self.pricing_status.value
        else:
            pricing_status = self.pricing_status

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros

        stop = self.stop

        stop_bound_micros: int | None | Unset
        if isinstance(self.stop_bound_micros, Unset):
            stop_bound_micros = UNSET
        else:
            stop_bound_micros = self.stop_bound_micros

        stop_context: list[Any] | None | Unset
        if isinstance(self.stop_context, Unset):
            stop_context = UNSET
        elif isinstance(self.stop_context, list):
            stop_context = self.stop_context


        else:
            stop_context = self.stop_context

        stop_measured_micros: int | None | Unset
        if isinstance(self.stop_measured_micros, Unset):
            stop_measured_micros = UNSET
        else:
            stop_measured_micros = self.stop_measured_micros

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

        suspended: bool | None | Unset
        if isinstance(self.suspended, Unset):
            suspended = UNSET
        else:
            suspended = self.suspended

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

        trigger_source: None | str | Unset
        if isinstance(self.trigger_source, Unset):
            trigger_source = UNSET
        else:
            trigger_source = self.trigger_source

        uncosted_measurement_keys: list[str] | Unset = UNSET
        if not isinstance(self.uncosted_measurement_keys, Unset):
            uncosted_measurement_keys = self.uncosted_measurement_keys



        unresolved_reason: None | str | Unset
        if isinstance(self.unresolved_reason, Unset):
            unresolved_reason = UNSET
        elif isinstance(self.unresolved_reason, UsageBatchItemResponseUnresolvedReasonType0):
            unresolved_reason = self.unresolved_reason.value
        else:
            unresolved_reason = self.unresolved_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "accepted": accepted,
        })
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if ceiling_remaining_micros is not UNSET:
            field_dict["ceiling_remaining_micros"] = ceiling_remaining_micros
        if ceiling_status is not UNSET:
            field_dict["ceiling_status"] = ceiling_status
        if ceiling_used_percentage is not UNSET:
            field_dict["ceiling_used_percentage"] = ceiling_used_percentage
        if claimed_provider_cost_micros is not UNSET:
            field_dict["claimed_provider_cost_micros"] = claimed_provider_cost_micros
        if code is not UNSET:
            field_dict["code"] = code
        if costing_status is not UNSET:
            field_dict["costing_status"] = costing_status
        if detail is not UNSET:
            field_dict["detail"] = detail
        if event_id is not UNSET:
            field_dict["event_id"] = event_id
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
        if pricing_status is not UNSET:
            field_dict["pricing_status"] = pricing_status
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
        if stop is not UNSET:
            field_dict["stop"] = stop
        if stop_bound_micros is not UNSET:
            field_dict["stop_bound_micros"] = stop_bound_micros
        if stop_context is not UNSET:
            field_dict["stop_context"] = stop_context
        if stop_measured_micros is not UNSET:
            field_dict["stop_measured_micros"] = stop_measured_micros
        if stop_reason is not UNSET:
            field_dict["stop_reason"] = stop_reason
        if stop_scope is not UNSET:
            field_dict["stop_scope"] = stop_scope
        if suspended is not UNSET:
            field_dict["suspended"] = suspended
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
        if trigger_source is not UNSET:
            field_dict["trigger_source"] = trigger_source
        if uncosted_measurement_keys is not UNSET:
            field_dict["uncosted_measurement_keys"] = uncosted_measurement_keys
        if unresolved_reason is not UNSET:
            field_dict["unresolved_reason"] = unresolved_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_batch_item_response_grouping_fields import UsageBatchItemResponseGroupingFields
        from ..models.usage_batch_item_response_measurements_type_0 import UsageBatchItemResponseMeasurementsType0
        from ..models.usage_batch_item_response_pricing_receipt_type_0 import UsageBatchItemResponsePricingReceiptType0
        d = dict(src_dict)
        accepted = d.pop("accepted")

        def _parse_billed_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        billed_cost_micros = _parse_billed_cost_micros(d.pop("billed_cost_micros", UNSET))


        def _parse_ceiling_remaining_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ceiling_remaining_micros = _parse_ceiling_remaining_micros(d.pop("ceiling_remaining_micros", UNSET))


        def _parse_ceiling_status(data: object) -> None | Unset | UsageBatchItemResponseCeilingStatusType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ceiling_status_type_0 = UsageBatchItemResponseCeilingStatusType0(data)



                return ceiling_status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponseCeilingStatusType0, data)

        ceiling_status = _parse_ceiling_status(d.pop("ceiling_status", UNSET))


        def _parse_ceiling_used_percentage(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ceiling_used_percentage = _parse_ceiling_used_percentage(d.pop("ceiling_used_percentage", UNSET))


        def _parse_claimed_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        claimed_provider_cost_micros = _parse_claimed_provider_cost_micros(d.pop("claimed_provider_cost_micros", UNSET))


        def _parse_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        code = _parse_code(d.pop("code", UNSET))


        def _parse_costing_status(data: object) -> None | Unset | UsageBatchItemResponseCostingStatusType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                costing_status_type_0 = UsageBatchItemResponseCostingStatusType0(data)



                return costing_status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponseCostingStatusType0, data)

        costing_status = _parse_costing_status(d.pop("costing_status", UNSET))


        def _parse_detail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        detail = _parse_detail(d.pop("detail", UNSET))


        def _parse_event_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        event_id = _parse_event_id(d.pop("event_id", UNSET))


        _grouping_fields = d.pop("grouping_fields", UNSET)
        grouping_fields: UsageBatchItemResponseGroupingFields | Unset
        if isinstance(_grouping_fields,  Unset):
            grouping_fields = UNSET
        else:
            grouping_fields = UsageBatchItemResponseGroupingFields.from_dict(_grouping_fields)




        def _parse_measurements(data: object) -> None | Unset | UsageBatchItemResponseMeasurementsType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                measurements_type_0 = UsageBatchItemResponseMeasurementsType0.from_dict(data)



                return measurements_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponseMeasurementsType0, data)

        measurements = _parse_measurements(d.pop("measurements", UNSET))


        def _parse_new_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        new_balance_micros = _parse_new_balance_micros(d.pop("new_balance_micros", UNSET))


        def _parse_not_applicable_reason(data: object) -> None | Unset | UsageBatchItemResponseNotApplicableReasonType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                not_applicable_reason_type_0 = UsageBatchItemResponseNotApplicableReasonType0(data)



                return not_applicable_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponseNotApplicableReasonType0, data)

        not_applicable_reason = _parse_not_applicable_reason(d.pop("not_applicable_reason", UNSET))


        def _parse_parent_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_pricing_method(data: object) -> None | Unset | UsageBatchItemResponsePricingMethodType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_method_type_0 = UsageBatchItemResponsePricingMethodType0(data)



                return pricing_method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponsePricingMethodType0, data)

        pricing_method = _parse_pricing_method(d.pop("pricing_method", UNSET))


        def _parse_pricing_receipt(data: object) -> None | Unset | UsageBatchItemResponsePricingReceiptType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                pricing_receipt_type_0 = UsageBatchItemResponsePricingReceiptType0.from_dict(data)



                return pricing_receipt_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponsePricingReceiptType0, data)

        pricing_receipt = _parse_pricing_receipt(d.pop("pricing_receipt", UNSET))


        def _parse_pricing_receipt_subject_type(data: object) -> None | Unset | UsageBatchItemResponsePricingReceiptSubjectTypeType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_receipt_subject_type_type_0 = UsageBatchItemResponsePricingReceiptSubjectTypeType0(data)



                return pricing_receipt_subject_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponsePricingReceiptSubjectTypeType0, data)

        pricing_receipt_subject_type = _parse_pricing_receipt_subject_type(d.pop("pricing_receipt_subject_type", UNSET))


        def _parse_pricing_status(data: object) -> None | Unset | UsageBatchItemResponsePricingStatusType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_status_type_0 = UsageBatchItemResponsePricingStatusType0(data)



                return pricing_status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponsePricingStatusType0, data)

        pricing_status = _parse_pricing_status(d.pop("pricing_status", UNSET))


        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


        stop = d.pop("stop", UNSET)

        def _parse_stop_bound_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        stop_bound_micros = _parse_stop_bound_micros(d.pop("stop_bound_micros", UNSET))


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


        def _parse_stop_measured_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        stop_measured_micros = _parse_stop_measured_micros(d.pop("stop_measured_micros", UNSET))


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


        def _parse_suspended(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        suspended = _parse_suspended(d.pop("suspended", UNSET))


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


        def _parse_trigger_source(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trigger_source = _parse_trigger_source(d.pop("trigger_source", UNSET))


        uncosted_measurement_keys = cast(list[str], d.pop("uncosted_measurement_keys", UNSET))


        def _parse_unresolved_reason(data: object) -> None | Unset | UsageBatchItemResponseUnresolvedReasonType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                unresolved_reason_type_0 = UsageBatchItemResponseUnresolvedReasonType0(data)



                return unresolved_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageBatchItemResponseUnresolvedReasonType0, data)

        unresolved_reason = _parse_unresolved_reason(d.pop("unresolved_reason", UNSET))


        usage_batch_item_response = cls(
            accepted=accepted,
            billed_cost_micros=billed_cost_micros,
            ceiling_remaining_micros=ceiling_remaining_micros,
            ceiling_status=ceiling_status,
            ceiling_used_percentage=ceiling_used_percentage,
            claimed_provider_cost_micros=claimed_provider_cost_micros,
            code=code,
            costing_status=costing_status,
            detail=detail,
            event_id=event_id,
            grouping_fields=grouping_fields,
            measurements=measurements,
            new_balance_micros=new_balance_micros,
            not_applicable_reason=not_applicable_reason,
            parent_task_id=parent_task_id,
            pricing_method=pricing_method,
            pricing_receipt=pricing_receipt,
            pricing_receipt_subject_type=pricing_receipt_subject_type,
            pricing_status=pricing_status,
            provider_cost_micros=provider_cost_micros,
            stop=stop,
            stop_bound_micros=stop_bound_micros,
            stop_context=stop_context,
            stop_measured_micros=stop_measured_micros,
            stop_reason=stop_reason,
            stop_scope=stop_scope,
            suspended=suspended,
            task_id=task_id,
            task_total_billed_cost_micros=task_total_billed_cost_micros,
            task_total_provider_cost_micros=task_total_provider_cost_micros,
            task_total_unpriced_event_count=task_total_unpriced_event_count,
            task_total_unresolved_event_count=task_total_unresolved_event_count,
            trigger_source=trigger_source,
            uncosted_measurement_keys=uncosted_measurement_keys,
            unresolved_reason=unresolved_reason,
        )


        usage_batch_item_response.additional_properties = d
        return usage_batch_item_response

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
