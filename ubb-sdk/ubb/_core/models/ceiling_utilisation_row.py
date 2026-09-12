from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.ceiling_utilisation_row_ceiling_status import CeilingUtilisationRowCeilingStatus
from ..types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime






T = TypeVar("T", bound="CeilingUtilisationRow")



@_attrs_define
class CeilingUtilisationRow:
    """ One completed unit's ceiling as it stands at completion: the status
    (the reading rule is written once, on `RecordUsageResponse.ceiling_status`
    — under `indeterminate` the percentage is a floor and the headroom a
    ceiling), the final utilisation over the known total, the headroom, and
    the pair the figures are computed over. Under `not_applicable` both
    figures are null, never zero.

        Attributes:
            ceiling_status (CeilingUtilisationRowCeilingStatus):
            completed_at (datetime.datetime):
            customer_id (UUID):
            final_provider_cost_micros (int):
            final_unresolved_event_count (int):
            task_id (UUID):
            task_type (str):
            ceiling_remaining_micros (int | None | Unset):
            ceiling_used_percentage (int | None | Unset):
            parent_task_id (None | Unset | UUID):
            task_cogs_ceiling_micros (int | None | Unset):
     """

    ceiling_status: CeilingUtilisationRowCeilingStatus
    completed_at: datetime.datetime
    customer_id: UUID
    final_provider_cost_micros: int
    final_unresolved_event_count: int
    task_id: UUID
    task_type: str
    ceiling_remaining_micros: int | None | Unset = UNSET
    ceiling_used_percentage: int | None | Unset = UNSET
    parent_task_id: None | Unset | UUID = UNSET
    task_cogs_ceiling_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        ceiling_status = self.ceiling_status.value

        completed_at = self.completed_at.isoformat()

        customer_id = str(self.customer_id)

        final_provider_cost_micros = self.final_provider_cost_micros

        final_unresolved_event_count = self.final_unresolved_event_count

        task_id = str(self.task_id)

        task_type = self.task_type

        ceiling_remaining_micros: int | None | Unset
        if isinstance(self.ceiling_remaining_micros, Unset):
            ceiling_remaining_micros = UNSET
        else:
            ceiling_remaining_micros = self.ceiling_remaining_micros

        ceiling_used_percentage: int | None | Unset
        if isinstance(self.ceiling_used_percentage, Unset):
            ceiling_used_percentage = UNSET
        else:
            ceiling_used_percentage = self.ceiling_used_percentage

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        elif isinstance(self.parent_task_id, UUID):
            parent_task_id = str(self.parent_task_id)
        else:
            parent_task_id = self.parent_task_id

        task_cogs_ceiling_micros: int | None | Unset
        if isinstance(self.task_cogs_ceiling_micros, Unset):
            task_cogs_ceiling_micros = UNSET
        else:
            task_cogs_ceiling_micros = self.task_cogs_ceiling_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "ceiling_status": ceiling_status,
            "completed_at": completed_at,
            "customer_id": customer_id,
            "final_provider_cost_micros": final_provider_cost_micros,
            "final_unresolved_event_count": final_unresolved_event_count,
            "task_id": task_id,
            "task_type": task_type,
        })
        if ceiling_remaining_micros is not UNSET:
            field_dict["ceiling_remaining_micros"] = ceiling_remaining_micros
        if ceiling_used_percentage is not UNSET:
            field_dict["ceiling_used_percentage"] = ceiling_used_percentage
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if task_cogs_ceiling_micros is not UNSET:
            field_dict["task_cogs_ceiling_micros"] = task_cogs_ceiling_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ceiling_status = CeilingUtilisationRowCeilingStatus(d.pop("ceiling_status"))




        completed_at = datetime.datetime.fromisoformat(d.pop("completed_at"))




        customer_id = UUID(d.pop("customer_id"))




        final_provider_cost_micros = d.pop("final_provider_cost_micros")

        final_unresolved_event_count = d.pop("final_unresolved_event_count")

        task_id = UUID(d.pop("task_id"))




        task_type = d.pop("task_type")

        def _parse_ceiling_remaining_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ceiling_remaining_micros = _parse_ceiling_remaining_micros(d.pop("ceiling_remaining_micros", UNSET))


        def _parse_ceiling_used_percentage(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ceiling_used_percentage = _parse_ceiling_used_percentage(d.pop("ceiling_used_percentage", UNSET))


        def _parse_parent_task_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                parent_task_id_type_0 = UUID(data)



                return parent_task_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_task_cogs_ceiling_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        task_cogs_ceiling_micros = _parse_task_cogs_ceiling_micros(d.pop("task_cogs_ceiling_micros", UNSET))


        ceiling_utilisation_row = cls(
            ceiling_status=ceiling_status,
            completed_at=completed_at,
            customer_id=customer_id,
            final_provider_cost_micros=final_provider_cost_micros,
            final_unresolved_event_count=final_unresolved_event_count,
            task_id=task_id,
            task_type=task_type,
            ceiling_remaining_micros=ceiling_remaining_micros,
            ceiling_used_percentage=ceiling_used_percentage,
            parent_task_id=parent_task_id,
            task_cogs_ceiling_micros=task_cogs_ceiling_micros,
        )


        ceiling_utilisation_row.additional_properties = d
        return ceiling_utilisation_row

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
