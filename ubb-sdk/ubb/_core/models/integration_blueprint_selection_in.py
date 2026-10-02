from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.integration_blueprint_selection_in_target import IntegrationBlueprintSelectionInTarget
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="IntegrationBlueprintSelectionIn")



@_attrs_define
class IntegrationBlueprintSelectionIn:
    """ What an integration does, as far as it has to be said.

    Three things every integration states — the target it is written for, the
    kind of work it performs and the Event Types that happen inside it — and
    one it states only if it applies: the Subtask kinds it explicitly creates.
    Everything else is read from what you have already declared.

    `task_type` and `event_types` may be left out. The Blueprint is then a
    scaffold that shows the lifecycle's shape and says what is missing.

    Where an Event Type reads a supplier's response and declares no response
    shape, the Blueprint does not take a path here: it answers with a blocking
    diagnostic carrying the request that declares the shape.

        Attributes:
            target (IntegrationBlueprintSelectionInTarget):
            draft_preview (bool | Unset): Resolve from draft declarations instead of published ones. Requires the admin
                role. A draft preview is stored nowhere, carries no `configuration_fingerprint` and cannot be verified. Default:
                False.
            event_types (list[str] | Unset):
            subtask_types (list[str] | Unset):
            task_type (None | str | Unset):
     """

    target: IntegrationBlueprintSelectionInTarget
    draft_preview: bool | Unset = False
    event_types: list[str] | Unset = UNSET
    subtask_types: list[str] | Unset = UNSET
    task_type: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        target = self.target.value

        draft_preview = self.draft_preview

        event_types: list[str] | Unset = UNSET
        if not isinstance(self.event_types, Unset):
            event_types = self.event_types



        subtask_types: list[str] | Unset = UNSET
        if not isinstance(self.subtask_types, Unset):
            subtask_types = self.subtask_types



        task_type: None | str | Unset
        if isinstance(self.task_type, Unset):
            task_type = UNSET
        else:
            task_type = self.task_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "target": target,
        })
        if draft_preview is not UNSET:
            field_dict["draft_preview"] = draft_preview
        if event_types is not UNSET:
            field_dict["event_types"] = event_types
        if subtask_types is not UNSET:
            field_dict["subtask_types"] = subtask_types
        if task_type is not UNSET:
            field_dict["task_type"] = task_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        target = IntegrationBlueprintSelectionInTarget(d.pop("target"))




        draft_preview = d.pop("draft_preview", UNSET)

        event_types = cast(list[str], d.pop("event_types", UNSET))


        subtask_types = cast(list[str], d.pop("subtask_types", UNSET))


        def _parse_task_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_type = _parse_task_type(d.pop("task_type", UNSET))


        integration_blueprint_selection_in = cls(
            target=target,
            draft_preview=draft_preview,
            event_types=event_types,
            subtask_types=subtask_types,
            task_type=task_type,
        )


        integration_blueprint_selection_in.additional_properties = d
        return integration_blueprint_selection_in

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
