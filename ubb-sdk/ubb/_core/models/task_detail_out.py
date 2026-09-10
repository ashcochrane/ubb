from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.task_detail_out_ceiling_status import TaskDetailOutCeilingStatus
from ..models.task_detail_out_outcome_reason_type_0 import TaskDetailOutOutcomeReasonType0
from ..models.task_detail_out_status import TaskDetailOutStatus
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.task_detail_out_dimensions import TaskDetailOutDimensions
  from ..models.task_out import TaskOut





T = TypeVar("T", bound="TaskDetailOut")



@_attrs_define
class TaskDetailOut:
    """ 
        Attributes:
            ceiling_status (TaskDetailOutCeilingStatus):
            created_at (str):
            event_count (int):
            status (TaskDetailOutStatus):
            task_id (str):
            total_billed_cost_micros (int):
            total_provider_cost_micros (int):
            unpriced_event_count (int):
            unresolved_event_count (int):
            agreed_price_micros (int | None | Unset):
            ceiling_remaining_micros (int | None | Unset):
            ceiling_used_percentage (int | None | Unset):
            completed_at (None | str | Unset):
            dimensions (TaskDetailOutDimensions | Unset):
            outcome_reason (None | TaskDetailOutOutcomeReasonType0 | Unset):
            parent_task_id (None | str | Unset):
            reason_detail (None | str | Unset):
            subtasks (list[TaskOut] | Unset):
            task_cogs_ceiling_micros (int | None | Unset):
            task_type (str | Unset):  Default: ''.
     """

    ceiling_status: TaskDetailOutCeilingStatus
    created_at: str
    event_count: int
    status: TaskDetailOutStatus
    task_id: str
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    unpriced_event_count: int
    unresolved_event_count: int
    agreed_price_micros: int | None | Unset = UNSET
    ceiling_remaining_micros: int | None | Unset = UNSET
    ceiling_used_percentage: int | None | Unset = UNSET
    completed_at: None | str | Unset = UNSET
    dimensions: TaskDetailOutDimensions | Unset = UNSET
    outcome_reason: None | TaskDetailOutOutcomeReasonType0 | Unset = UNSET
    parent_task_id: None | str | Unset = UNSET
    reason_detail: None | str | Unset = UNSET
    subtasks: list[TaskOut] | Unset = UNSET
    task_cogs_ceiling_micros: int | None | Unset = UNSET
    task_type: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.task_detail_out_dimensions import TaskDetailOutDimensions
        from ..models.task_out import TaskOut
        ceiling_status = self.ceiling_status.value

        created_at = self.created_at

        event_count = self.event_count

        status = self.status.value

        task_id = self.task_id

        total_billed_cost_micros = self.total_billed_cost_micros

        total_provider_cost_micros = self.total_provider_cost_micros

        unpriced_event_count = self.unpriced_event_count

        unresolved_event_count = self.unresolved_event_count

        agreed_price_micros: int | None | Unset
        if isinstance(self.agreed_price_micros, Unset):
            agreed_price_micros = UNSET
        else:
            agreed_price_micros = self.agreed_price_micros

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

        completed_at: None | str | Unset
        if isinstance(self.completed_at, Unset):
            completed_at = UNSET
        else:
            completed_at = self.completed_at

        dimensions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.dimensions, Unset):
            dimensions = self.dimensions.to_dict()

        outcome_reason: None | str | Unset
        if isinstance(self.outcome_reason, Unset):
            outcome_reason = UNSET
        elif isinstance(self.outcome_reason, TaskDetailOutOutcomeReasonType0):
            outcome_reason = self.outcome_reason.value
        else:
            outcome_reason = self.outcome_reason

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        else:
            parent_task_id = self.parent_task_id

        reason_detail: None | str | Unset
        if isinstance(self.reason_detail, Unset):
            reason_detail = UNSET
        else:
            reason_detail = self.reason_detail

        subtasks: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.subtasks, Unset):
            subtasks = []
            for subtasks_item_data in self.subtasks:
                subtasks_item = subtasks_item_data.to_dict()
                subtasks.append(subtasks_item)



        task_cogs_ceiling_micros: int | None | Unset
        if isinstance(self.task_cogs_ceiling_micros, Unset):
            task_cogs_ceiling_micros = UNSET
        else:
            task_cogs_ceiling_micros = self.task_cogs_ceiling_micros

        task_type = self.task_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "ceiling_status": ceiling_status,
            "created_at": created_at,
            "event_count": event_count,
            "status": status,
            "task_id": task_id,
            "total_billed_cost_micros": total_billed_cost_micros,
            "total_provider_cost_micros": total_provider_cost_micros,
            "unpriced_event_count": unpriced_event_count,
            "unresolved_event_count": unresolved_event_count,
        })
        if agreed_price_micros is not UNSET:
            field_dict["agreed_price_micros"] = agreed_price_micros
        if ceiling_remaining_micros is not UNSET:
            field_dict["ceiling_remaining_micros"] = ceiling_remaining_micros
        if ceiling_used_percentage is not UNSET:
            field_dict["ceiling_used_percentage"] = ceiling_used_percentage
        if completed_at is not UNSET:
            field_dict["completed_at"] = completed_at
        if dimensions is not UNSET:
            field_dict["dimensions"] = dimensions
        if outcome_reason is not UNSET:
            field_dict["outcome_reason"] = outcome_reason
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if reason_detail is not UNSET:
            field_dict["reason_detail"] = reason_detail
        if subtasks is not UNSET:
            field_dict["subtasks"] = subtasks
        if task_cogs_ceiling_micros is not UNSET:
            field_dict["task_cogs_ceiling_micros"] = task_cogs_ceiling_micros
        if task_type is not UNSET:
            field_dict["task_type"] = task_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_detail_out_dimensions import TaskDetailOutDimensions
        from ..models.task_out import TaskOut
        d = dict(src_dict)
        ceiling_status = TaskDetailOutCeilingStatus(d.pop("ceiling_status"))




        created_at = d.pop("created_at")

        event_count = d.pop("event_count")

        status = TaskDetailOutStatus(d.pop("status"))




        task_id = d.pop("task_id")

        total_billed_cost_micros = d.pop("total_billed_cost_micros")

        total_provider_cost_micros = d.pop("total_provider_cost_micros")

        unpriced_event_count = d.pop("unpriced_event_count")

        unresolved_event_count = d.pop("unresolved_event_count")

        def _parse_agreed_price_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        agreed_price_micros = _parse_agreed_price_micros(d.pop("agreed_price_micros", UNSET))


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


        def _parse_completed_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        completed_at = _parse_completed_at(d.pop("completed_at", UNSET))


        _dimensions = d.pop("dimensions", UNSET)
        dimensions: TaskDetailOutDimensions | Unset
        if isinstance(_dimensions,  Unset):
            dimensions = UNSET
        else:
            dimensions = TaskDetailOutDimensions.from_dict(_dimensions)




        def _parse_outcome_reason(data: object) -> None | TaskDetailOutOutcomeReasonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                outcome_reason_type_0 = TaskDetailOutOutcomeReasonType0(data)



                return outcome_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TaskDetailOutOutcomeReasonType0 | Unset, data)

        outcome_reason = _parse_outcome_reason(d.pop("outcome_reason", UNSET))


        def _parse_parent_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_reason_detail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason_detail = _parse_reason_detail(d.pop("reason_detail", UNSET))


        _subtasks = d.pop("subtasks", UNSET)
        subtasks: list[TaskOut] | Unset = UNSET
        if _subtasks is not UNSET:
            subtasks = []
            for subtasks_item_data in _subtasks:
                subtasks_item = TaskOut.from_dict(subtasks_item_data)



                subtasks.append(subtasks_item)


        def _parse_task_cogs_ceiling_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        task_cogs_ceiling_micros = _parse_task_cogs_ceiling_micros(d.pop("task_cogs_ceiling_micros", UNSET))


        task_type = d.pop("task_type", UNSET)

        task_detail_out = cls(
            ceiling_status=ceiling_status,
            created_at=created_at,
            event_count=event_count,
            status=status,
            task_id=task_id,
            total_billed_cost_micros=total_billed_cost_micros,
            total_provider_cost_micros=total_provider_cost_micros,
            unpriced_event_count=unpriced_event_count,
            unresolved_event_count=unresolved_event_count,
            agreed_price_micros=agreed_price_micros,
            ceiling_remaining_micros=ceiling_remaining_micros,
            ceiling_used_percentage=ceiling_used_percentage,
            completed_at=completed_at,
            dimensions=dimensions,
            outcome_reason=outcome_reason,
            parent_task_id=parent_task_id,
            reason_detail=reason_detail,
            subtasks=subtasks,
            task_cogs_ceiling_micros=task_cogs_ceiling_micros,
            task_type=task_type,
        )


        task_detail_out.additional_properties = d
        return task_detail_out

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
