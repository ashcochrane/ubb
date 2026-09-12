from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.ceiling_episode_row_ceiling_basis import CeilingEpisodeRowCeilingBasis
from ..models.ceiling_episode_row_control_family import CeilingEpisodeRowControlFamily
from ..types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime

if TYPE_CHECKING:
  from ..models.itemised_events_out import ItemisedEventsOut





T = TypeVar("T", bound="CeilingEpisodeRow")



@_attrs_define
class CeilingEpisodeRow:
    """ A unit UBB stopped on its own cost ceiling: the unit and its kind, the
    control that fired (family, id, basis) and the mechanism that applied
    it, the ceiling the unit pinned at start, the known supplier cost when
    the ceiling fired and where the unit ended — each as a pair with the
    count it could not include — and the itemised events that landed after
    the stop. A kill never resumes, so there is no close. An indeterminate
    unit is never here (its ceiling never fired), nor is an expiry, nor
    contained work stopped by its parent's cascade.

        Attributes:
            ceiling_basis (CeilingEpisodeRowCeilingBasis):
            control_family (CeilingEpisodeRowControlFamily):
            customer_id (UUID):
            final_provider_cost_micros (int):
            final_unresolved_event_count (int):
            itemised (ItemisedEventsOut): The events an episode itemises and their totals in both denominations
                — each total adding what is resolved and counting what is not, so a row
                can never read complete while its own events read partial.
            opened_at (datetime.datetime):
            reason_code (str):
            stop_scope (str):
            task_cogs_ceiling_micros (int):
            task_id (UUID):
            task_type (str):
            control_id (None | str | Unset):
            crossed_provider_cost_micros (int | None | Unset):
            crossed_unresolved_event_count (int | None | Unset):
            parent_task_id (None | Unset | UUID):
            trigger_source (None | str | Unset):
     """

    ceiling_basis: CeilingEpisodeRowCeilingBasis
    control_family: CeilingEpisodeRowControlFamily
    customer_id: UUID
    final_provider_cost_micros: int
    final_unresolved_event_count: int
    itemised: ItemisedEventsOut
    opened_at: datetime.datetime
    reason_code: str
    stop_scope: str
    task_cogs_ceiling_micros: int
    task_id: UUID
    task_type: str
    control_id: None | str | Unset = UNSET
    crossed_provider_cost_micros: int | None | Unset = UNSET
    crossed_unresolved_event_count: int | None | Unset = UNSET
    parent_task_id: None | Unset | UUID = UNSET
    trigger_source: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.itemised_events_out import ItemisedEventsOut
        ceiling_basis = self.ceiling_basis.value

        control_family = self.control_family.value

        customer_id = str(self.customer_id)

        final_provider_cost_micros = self.final_provider_cost_micros

        final_unresolved_event_count = self.final_unresolved_event_count

        itemised = self.itemised.to_dict()

        opened_at = self.opened_at.isoformat()

        reason_code = self.reason_code

        stop_scope = self.stop_scope

        task_cogs_ceiling_micros = self.task_cogs_ceiling_micros

        task_id = str(self.task_id)

        task_type = self.task_type

        control_id: None | str | Unset
        if isinstance(self.control_id, Unset):
            control_id = UNSET
        else:
            control_id = self.control_id

        crossed_provider_cost_micros: int | None | Unset
        if isinstance(self.crossed_provider_cost_micros, Unset):
            crossed_provider_cost_micros = UNSET
        else:
            crossed_provider_cost_micros = self.crossed_provider_cost_micros

        crossed_unresolved_event_count: int | None | Unset
        if isinstance(self.crossed_unresolved_event_count, Unset):
            crossed_unresolved_event_count = UNSET
        else:
            crossed_unresolved_event_count = self.crossed_unresolved_event_count

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        elif isinstance(self.parent_task_id, UUID):
            parent_task_id = str(self.parent_task_id)
        else:
            parent_task_id = self.parent_task_id

        trigger_source: None | str | Unset
        if isinstance(self.trigger_source, Unset):
            trigger_source = UNSET
        else:
            trigger_source = self.trigger_source


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "ceiling_basis": ceiling_basis,
            "control_family": control_family,
            "customer_id": customer_id,
            "final_provider_cost_micros": final_provider_cost_micros,
            "final_unresolved_event_count": final_unresolved_event_count,
            "itemised": itemised,
            "opened_at": opened_at,
            "reason_code": reason_code,
            "stop_scope": stop_scope,
            "task_cogs_ceiling_micros": task_cogs_ceiling_micros,
            "task_id": task_id,
            "task_type": task_type,
        })
        if control_id is not UNSET:
            field_dict["control_id"] = control_id
        if crossed_provider_cost_micros is not UNSET:
            field_dict["crossed_provider_cost_micros"] = crossed_provider_cost_micros
        if crossed_unresolved_event_count is not UNSET:
            field_dict["crossed_unresolved_event_count"] = crossed_unresolved_event_count
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if trigger_source is not UNSET:
            field_dict["trigger_source"] = trigger_source

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.itemised_events_out import ItemisedEventsOut
        d = dict(src_dict)
        ceiling_basis = CeilingEpisodeRowCeilingBasis(d.pop("ceiling_basis"))




        control_family = CeilingEpisodeRowControlFamily(d.pop("control_family"))




        customer_id = UUID(d.pop("customer_id"))




        final_provider_cost_micros = d.pop("final_provider_cost_micros")

        final_unresolved_event_count = d.pop("final_unresolved_event_count")

        itemised = ItemisedEventsOut.from_dict(d.pop("itemised"))




        opened_at = datetime.datetime.fromisoformat(d.pop("opened_at"))




        reason_code = d.pop("reason_code")

        stop_scope = d.pop("stop_scope")

        task_cogs_ceiling_micros = d.pop("task_cogs_ceiling_micros")

        task_id = UUID(d.pop("task_id"))




        task_type = d.pop("task_type")

        def _parse_control_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        control_id = _parse_control_id(d.pop("control_id", UNSET))


        def _parse_crossed_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        crossed_provider_cost_micros = _parse_crossed_provider_cost_micros(d.pop("crossed_provider_cost_micros", UNSET))


        def _parse_crossed_unresolved_event_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        crossed_unresolved_event_count = _parse_crossed_unresolved_event_count(d.pop("crossed_unresolved_event_count", UNSET))


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


        def _parse_trigger_source(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trigger_source = _parse_trigger_source(d.pop("trigger_source", UNSET))


        ceiling_episode_row = cls(
            ceiling_basis=ceiling_basis,
            control_family=control_family,
            customer_id=customer_id,
            final_provider_cost_micros=final_provider_cost_micros,
            final_unresolved_event_count=final_unresolved_event_count,
            itemised=itemised,
            opened_at=opened_at,
            reason_code=reason_code,
            stop_scope=stop_scope,
            task_cogs_ceiling_micros=task_cogs_ceiling_micros,
            task_id=task_id,
            task_type=task_type,
            control_id=control_id,
            crossed_provider_cost_micros=crossed_provider_cost_micros,
            crossed_unresolved_event_count=crossed_unresolved_event_count,
            parent_task_id=parent_task_id,
            trigger_source=trigger_source,
        )


        ceiling_episode_row.additional_properties = d
        return ceiling_episode_row

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
