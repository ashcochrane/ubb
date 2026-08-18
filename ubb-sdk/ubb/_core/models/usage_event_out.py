from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.usage_event_out_costing_status import UsageEventOutCostingStatus
from ..models.usage_event_out_not_applicable_reason_type_0 import UsageEventOutNotApplicableReasonType0
from ..models.usage_event_out_pricing_status import UsageEventOutPricingStatus
from ..models.usage_event_out_unresolved_reason_type_0 import UsageEventOutUnresolvedReasonType0
from ..types import UNSET, Unset
from typing import cast
from uuid import UUID

if TYPE_CHECKING:
  from ..models.usage_event_out_metadata import UsageEventOutMetadata





T = TypeVar("T", bound="UsageEventOut")



@_attrs_define
class UsageEventOut:
    """ 
        Attributes:
            costing_status (UsageEventOutCostingStatus):
            effective_at (str):
            id (UUID):
            metadata (UsageEventOutMetadata):
            pricing_status (UsageEventOutPricingStatus):
            request_id (str):
            billed_cost_micros (int | None | Unset):
            claimed_provider_cost_micros (int | None | Unset): What the caller believes this call cost. Diagnostic only,
                recorded as stated and never COGS: it is never rated, never summed into a cost total, and never becomes the
                supplier cost beside it. `provider_cost_micros` is the supplier's own reported figure and the only one UBB
                treats as cost.
            event_type (str | Unset):  Default: ''.
            not_applicable_reason (None | Unset | UsageEventOutNotApplicableReasonType0):
            provider (str | Unset):  Default: ''.
            provider_cost_micros (int | None | Unset):
            stop_context (list[Any] | None | Unset):
            unresolved_reason (None | Unset | UsageEventOutUnresolvedReasonType0):
     """

    costing_status: UsageEventOutCostingStatus
    effective_at: str
    id: UUID
    metadata: UsageEventOutMetadata
    pricing_status: UsageEventOutPricingStatus
    request_id: str
    billed_cost_micros: int | None | Unset = UNSET
    claimed_provider_cost_micros: int | None | Unset = UNSET
    event_type: str | Unset = ''
    not_applicable_reason: None | Unset | UsageEventOutNotApplicableReasonType0 = UNSET
    provider: str | Unset = ''
    provider_cost_micros: int | None | Unset = UNSET
    stop_context: list[Any] | None | Unset = UNSET
    unresolved_reason: None | Unset | UsageEventOutUnresolvedReasonType0 = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_event_out_metadata import UsageEventOutMetadata
        costing_status = self.costing_status.value

        effective_at = self.effective_at

        id = str(self.id)

        metadata = self.metadata.to_dict()

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

        event_type = self.event_type

        not_applicable_reason: None | str | Unset
        if isinstance(self.not_applicable_reason, Unset):
            not_applicable_reason = UNSET
        elif isinstance(self.not_applicable_reason, UsageEventOutNotApplicableReasonType0):
            not_applicable_reason = self.not_applicable_reason.value
        else:
            not_applicable_reason = self.not_applicable_reason

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

        unresolved_reason: None | str | Unset
        if isinstance(self.unresolved_reason, Unset):
            unresolved_reason = UNSET
        elif isinstance(self.unresolved_reason, UsageEventOutUnresolvedReasonType0):
            unresolved_reason = self.unresolved_reason.value
        else:
            unresolved_reason = self.unresolved_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "costing_status": costing_status,
            "effective_at": effective_at,
            "id": id,
            "metadata": metadata,
            "pricing_status": pricing_status,
            "request_id": request_id,
        })
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if claimed_provider_cost_micros is not UNSET:
            field_dict["claimed_provider_cost_micros"] = claimed_provider_cost_micros
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if not_applicable_reason is not UNSET:
            field_dict["not_applicable_reason"] = not_applicable_reason
        if provider is not UNSET:
            field_dict["provider"] = provider
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
        if stop_context is not UNSET:
            field_dict["stop_context"] = stop_context
        if unresolved_reason is not UNSET:
            field_dict["unresolved_reason"] = unresolved_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_event_out_metadata import UsageEventOutMetadata
        d = dict(src_dict)
        costing_status = UsageEventOutCostingStatus(d.pop("costing_status"))




        effective_at = d.pop("effective_at")

        id = UUID(d.pop("id"))




        metadata = UsageEventOutMetadata.from_dict(d.pop("metadata"))




        pricing_status = UsageEventOutPricingStatus(d.pop("pricing_status"))




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


        event_type = d.pop("event_type", UNSET)

        def _parse_not_applicable_reason(data: object) -> None | Unset | UsageEventOutNotApplicableReasonType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                not_applicable_reason_type_0 = UsageEventOutNotApplicableReasonType0(data)



                return not_applicable_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageEventOutNotApplicableReasonType0, data)

        not_applicable_reason = _parse_not_applicable_reason(d.pop("not_applicable_reason", UNSET))


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


        def _parse_unresolved_reason(data: object) -> None | Unset | UsageEventOutUnresolvedReasonType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                unresolved_reason_type_0 = UsageEventOutUnresolvedReasonType0(data)



                return unresolved_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UsageEventOutUnresolvedReasonType0, data)

        unresolved_reason = _parse_unresolved_reason(d.pop("unresolved_reason", UNSET))


        usage_event_out = cls(
            costing_status=costing_status,
            effective_at=effective_at,
            id=id,
            metadata=metadata,
            pricing_status=pricing_status,
            request_id=request_id,
            billed_cost_micros=billed_cost_micros,
            claimed_provider_cost_micros=claimed_provider_cost_micros,
            event_type=event_type,
            not_applicable_reason=not_applicable_reason,
            provider=provider,
            provider_cost_micros=provider_cost_micros,
            stop_context=stop_context,
            unresolved_reason=unresolved_reason,
        )


        usage_event_out.additional_properties = d
        return usage_event_out

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
