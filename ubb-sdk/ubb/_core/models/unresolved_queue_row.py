from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.unresolved_queue_row_costing_status import UnresolvedQueueRowCostingStatus
from ..models.unresolved_queue_row_pricing_status import UnresolvedQueueRowPricingStatus
from ..models.unresolved_queue_row_unresolved_reason_type_0 import UnresolvedQueueRowUnresolvedReasonType0
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="UnresolvedQueueRow")



@_attrs_define
class UnresolvedQueueRow:
    """ One posting UBB could not resolve, and what says why.

    The amounts are the columns as they stand: `null` where UBB has no figure,
    never a zero and never a word. Which of the two readings a `null` takes is
    the status beside it — that is the whole of what the nullable columns and
    their statuses were built for, and a queue is exactly where a reader would
    otherwise total a column of blanks by eye.

        Attributes:
            costing_status (UnresolvedQueueRowCostingStatus):
            currency (str):
            customer_id (str):
            effective_at (str):
            pricing_status (UnresolvedQueueRowPricingStatus):
            usage_event_id (str):
            billed_cost_micros (int | None | Unset):
            event_type (str | Unset):  Default: ''.
            provider (str | Unset):  Default: ''.
            provider_cost_micros (int | None | Unset):
            unresolved_reason (None | UnresolvedQueueRowUnresolvedReasonType0 | Unset):
     """

    costing_status: UnresolvedQueueRowCostingStatus
    currency: str
    customer_id: str
    effective_at: str
    pricing_status: UnresolvedQueueRowPricingStatus
    usage_event_id: str
    billed_cost_micros: int | None | Unset = UNSET
    event_type: str | Unset = ''
    provider: str | Unset = ''
    provider_cost_micros: int | None | Unset = UNSET
    unresolved_reason: None | UnresolvedQueueRowUnresolvedReasonType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        costing_status = self.costing_status.value

        currency = self.currency

        customer_id = self.customer_id

        effective_at = self.effective_at

        pricing_status = self.pricing_status.value

        usage_event_id = self.usage_event_id

        billed_cost_micros: int | None | Unset
        if isinstance(self.billed_cost_micros, Unset):
            billed_cost_micros = UNSET
        else:
            billed_cost_micros = self.billed_cost_micros

        event_type = self.event_type

        provider = self.provider

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros

        unresolved_reason: None | str | Unset
        if isinstance(self.unresolved_reason, Unset):
            unresolved_reason = UNSET
        elif isinstance(self.unresolved_reason, UnresolvedQueueRowUnresolvedReasonType0):
            unresolved_reason = self.unresolved_reason.value
        else:
            unresolved_reason = self.unresolved_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "costing_status": costing_status,
            "currency": currency,
            "customer_id": customer_id,
            "effective_at": effective_at,
            "pricing_status": pricing_status,
            "usage_event_id": usage_event_id,
        })
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if provider is not UNSET:
            field_dict["provider"] = provider
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
        if unresolved_reason is not UNSET:
            field_dict["unresolved_reason"] = unresolved_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        costing_status = UnresolvedQueueRowCostingStatus(d.pop("costing_status"))




        currency = d.pop("currency")

        customer_id = d.pop("customer_id")

        effective_at = d.pop("effective_at")

        pricing_status = UnresolvedQueueRowPricingStatus(d.pop("pricing_status"))




        usage_event_id = d.pop("usage_event_id")

        def _parse_billed_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        billed_cost_micros = _parse_billed_cost_micros(d.pop("billed_cost_micros", UNSET))


        event_type = d.pop("event_type", UNSET)

        provider = d.pop("provider", UNSET)

        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


        def _parse_unresolved_reason(data: object) -> None | UnresolvedQueueRowUnresolvedReasonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                unresolved_reason_type_0 = UnresolvedQueueRowUnresolvedReasonType0(data)



                return unresolved_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UnresolvedQueueRowUnresolvedReasonType0 | Unset, data)

        unresolved_reason = _parse_unresolved_reason(d.pop("unresolved_reason", UNSET))


        unresolved_queue_row = cls(
            costing_status=costing_status,
            currency=currency,
            customer_id=customer_id,
            effective_at=effective_at,
            pricing_status=pricing_status,
            usage_event_id=usage_event_id,
            billed_cost_micros=billed_cost_micros,
            event_type=event_type,
            provider=provider,
            provider_cost_micros=provider_cost_micros,
            unresolved_reason=unresolved_reason,
        )


        unresolved_queue_row.additional_properties = d
        return unresolved_queue_row

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
