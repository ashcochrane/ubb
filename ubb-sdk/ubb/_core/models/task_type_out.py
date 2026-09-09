from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.task_type_out_kind import TaskTypeOutKind
from ..models.task_type_out_pricing_mode import TaskTypeOutPricingMode
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TaskTypeOut")



@_attrs_define
class TaskTypeOut:
    """ One declared kind of work, as UBB holds it.

    The ceiling is exactly what was declared: a `task_cogs_ceiling_micros`
    figure, or `uncapped: true` with the figure `null`. A kind of work never
    inherits a ceiling from your workspace — the workspace defaults apply to
    work started with no declared kind at all. Each window is echoed back as
    declared; `null` means this kind declared none and inherits your workspace
    default for it.

    `retired_at` is the instant this kind of work stopped being offered, or
    `null` while it is live.

        Attributes:
            key (str):
            kind (TaskTypeOutKind):
            pricing_mode (TaskTypeOutPricingMode):
            required_dimensions (list[str]):
            retired (bool):
            uncapped (bool):
            absolute_deadline_seconds (int | None | Unset):
            retired_at (None | str | Unset):
            silence_window_seconds (int | None | Unset):
            task_cogs_ceiling_micros (int | None | Unset):
     """

    key: str
    kind: TaskTypeOutKind
    pricing_mode: TaskTypeOutPricingMode
    required_dimensions: list[str]
    retired: bool
    uncapped: bool
    absolute_deadline_seconds: int | None | Unset = UNSET
    retired_at: None | str | Unset = UNSET
    silence_window_seconds: int | None | Unset = UNSET
    task_cogs_ceiling_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        kind = self.kind.value

        pricing_mode = self.pricing_mode.value

        required_dimensions = self.required_dimensions



        retired = self.retired

        uncapped = self.uncapped

        absolute_deadline_seconds: int | None | Unset
        if isinstance(self.absolute_deadline_seconds, Unset):
            absolute_deadline_seconds = UNSET
        else:
            absolute_deadline_seconds = self.absolute_deadline_seconds

        retired_at: None | str | Unset
        if isinstance(self.retired_at, Unset):
            retired_at = UNSET
        else:
            retired_at = self.retired_at

        silence_window_seconds: int | None | Unset
        if isinstance(self.silence_window_seconds, Unset):
            silence_window_seconds = UNSET
        else:
            silence_window_seconds = self.silence_window_seconds

        task_cogs_ceiling_micros: int | None | Unset
        if isinstance(self.task_cogs_ceiling_micros, Unset):
            task_cogs_ceiling_micros = UNSET
        else:
            task_cogs_ceiling_micros = self.task_cogs_ceiling_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
            "kind": kind,
            "pricing_mode": pricing_mode,
            "required_dimensions": required_dimensions,
            "retired": retired,
            "uncapped": uncapped,
        })
        if absolute_deadline_seconds is not UNSET:
            field_dict["absolute_deadline_seconds"] = absolute_deadline_seconds
        if retired_at is not UNSET:
            field_dict["retired_at"] = retired_at
        if silence_window_seconds is not UNSET:
            field_dict["silence_window_seconds"] = silence_window_seconds
        if task_cogs_ceiling_micros is not UNSET:
            field_dict["task_cogs_ceiling_micros"] = task_cogs_ceiling_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        kind = TaskTypeOutKind(d.pop("kind"))




        pricing_mode = TaskTypeOutPricingMode(d.pop("pricing_mode"))




        required_dimensions = cast(list[str], d.pop("required_dimensions"))


        retired = d.pop("retired")

        uncapped = d.pop("uncapped")

        def _parse_absolute_deadline_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        absolute_deadline_seconds = _parse_absolute_deadline_seconds(d.pop("absolute_deadline_seconds", UNSET))


        def _parse_retired_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        retired_at = _parse_retired_at(d.pop("retired_at", UNSET))


        def _parse_silence_window_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        silence_window_seconds = _parse_silence_window_seconds(d.pop("silence_window_seconds", UNSET))


        def _parse_task_cogs_ceiling_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        task_cogs_ceiling_micros = _parse_task_cogs_ceiling_micros(d.pop("task_cogs_ceiling_micros", UNSET))


        task_type_out = cls(
            key=key,
            kind=kind,
            pricing_mode=pricing_mode,
            required_dimensions=required_dimensions,
            retired=retired,
            uncapped=uncapped,
            absolute_deadline_seconds=absolute_deadline_seconds,
            retired_at=retired_at,
            silence_window_seconds=silence_window_seconds,
            task_cogs_ceiling_micros=task_cogs_ceiling_micros,
        )


        task_type_out.additional_properties = d
        return task_type_out

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
