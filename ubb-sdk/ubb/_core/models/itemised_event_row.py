from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.itemised_event_row_costing_status import ItemisedEventRowCostingStatus
from ..models.itemised_event_row_pricing_status import ItemisedEventRowPricingStatus
from ..types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime






T = TypeVar("T", bound="ItemisedEventRow")



@_attrs_define
class ItemisedEventRow:
    """ One event itemised under an episode: the tipping event
    (`arrived_after` false) and every event that landed after the stop. Both
    amount/status pairs travel together (#328, #351): an absent amount is
    read through its status — unresolved is missing, waived or not
    applicable is a genuine zero — and never coalesced.

        Attributes:
            arrived_after (bool):
            costing_status (ItemisedEventRowCostingStatus):
            customer_id (UUID):
            effective_at (datetime.datetime):
            event_id (UUID):
            pricing_status (ItemisedEventRowPricingStatus):
            billed_cost_micros (int | None | Unset):
            charge_id (None | Unset | UUID):
            provider_cost_micros (int | None | Unset):
     """

    arrived_after: bool
    costing_status: ItemisedEventRowCostingStatus
    customer_id: UUID
    effective_at: datetime.datetime
    event_id: UUID
    pricing_status: ItemisedEventRowPricingStatus
    billed_cost_micros: int | None | Unset = UNSET
    charge_id: None | Unset | UUID = UNSET
    provider_cost_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        arrived_after = self.arrived_after

        costing_status = self.costing_status.value

        customer_id = str(self.customer_id)

        effective_at = self.effective_at.isoformat()

        event_id = str(self.event_id)

        pricing_status = self.pricing_status.value

        billed_cost_micros: int | None | Unset
        if isinstance(self.billed_cost_micros, Unset):
            billed_cost_micros = UNSET
        else:
            billed_cost_micros = self.billed_cost_micros

        charge_id: None | str | Unset
        if isinstance(self.charge_id, Unset):
            charge_id = UNSET
        elif isinstance(self.charge_id, UUID):
            charge_id = str(self.charge_id)
        else:
            charge_id = self.charge_id

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "arrived_after": arrived_after,
            "costing_status": costing_status,
            "customer_id": customer_id,
            "effective_at": effective_at,
            "event_id": event_id,
            "pricing_status": pricing_status,
        })
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if charge_id is not UNSET:
            field_dict["charge_id"] = charge_id
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        arrived_after = d.pop("arrived_after")

        costing_status = ItemisedEventRowCostingStatus(d.pop("costing_status"))




        customer_id = UUID(d.pop("customer_id"))




        effective_at = datetime.datetime.fromisoformat(d.pop("effective_at"))




        event_id = UUID(d.pop("event_id"))




        pricing_status = ItemisedEventRowPricingStatus(d.pop("pricing_status"))




        def _parse_billed_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        billed_cost_micros = _parse_billed_cost_micros(d.pop("billed_cost_micros", UNSET))


        def _parse_charge_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                charge_id_type_0 = UUID(data)



                return charge_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        charge_id = _parse_charge_id(d.pop("charge_id", UNSET))


        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


        itemised_event_row = cls(
            arrived_after=arrived_after,
            costing_status=costing_status,
            customer_id=customer_id,
            effective_at=effective_at,
            event_id=event_id,
            pricing_status=pricing_status,
            billed_cost_micros=billed_cost_micros,
            charge_id=charge_id,
            provider_cost_micros=provider_cost_micros,
        )


        itemised_event_row.additional_properties = d
        return itemised_event_row

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
