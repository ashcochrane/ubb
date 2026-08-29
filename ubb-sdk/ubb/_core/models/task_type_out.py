from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.task_type_out_kind import TaskTypeOutKind
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TaskTypeOut")



@_attrs_define
class TaskTypeOut:
    """ One declared kind of work, as UBB holds it.

    Each bound is echoed back exactly as declared. `null` means this kind
    declared none and inherits your workspace default for it.

        Attributes:
            key (str):
            kind (TaskTypeOutKind):
            required_dimensions (list[str]):
            retired (bool):
            absolute_deadline_seconds (int | None | Unset):
            default_provider_cost_limit_micros (int | None | Unset):
            silence_window_seconds (int | None | Unset):
     """

    key: str
    kind: TaskTypeOutKind
    required_dimensions: list[str]
    retired: bool
    absolute_deadline_seconds: int | None | Unset = UNSET
    default_provider_cost_limit_micros: int | None | Unset = UNSET
    silence_window_seconds: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        kind = self.kind.value

        required_dimensions = self.required_dimensions



        retired = self.retired

        absolute_deadline_seconds: int | None | Unset
        if isinstance(self.absolute_deadline_seconds, Unset):
            absolute_deadline_seconds = UNSET
        else:
            absolute_deadline_seconds = self.absolute_deadline_seconds

        default_provider_cost_limit_micros: int | None | Unset
        if isinstance(self.default_provider_cost_limit_micros, Unset):
            default_provider_cost_limit_micros = UNSET
        else:
            default_provider_cost_limit_micros = self.default_provider_cost_limit_micros

        silence_window_seconds: int | None | Unset
        if isinstance(self.silence_window_seconds, Unset):
            silence_window_seconds = UNSET
        else:
            silence_window_seconds = self.silence_window_seconds


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
            "kind": kind,
            "required_dimensions": required_dimensions,
            "retired": retired,
        })
        if absolute_deadline_seconds is not UNSET:
            field_dict["absolute_deadline_seconds"] = absolute_deadline_seconds
        if default_provider_cost_limit_micros is not UNSET:
            field_dict["default_provider_cost_limit_micros"] = default_provider_cost_limit_micros
        if silence_window_seconds is not UNSET:
            field_dict["silence_window_seconds"] = silence_window_seconds

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        kind = TaskTypeOutKind(d.pop("kind"))




        required_dimensions = cast(list[str], d.pop("required_dimensions"))


        retired = d.pop("retired")

        def _parse_absolute_deadline_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        absolute_deadline_seconds = _parse_absolute_deadline_seconds(d.pop("absolute_deadline_seconds", UNSET))


        def _parse_default_provider_cost_limit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        default_provider_cost_limit_micros = _parse_default_provider_cost_limit_micros(d.pop("default_provider_cost_limit_micros", UNSET))


        def _parse_silence_window_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        silence_window_seconds = _parse_silence_window_seconds(d.pop("silence_window_seconds", UNSET))


        task_type_out = cls(
            key=key,
            kind=kind,
            required_dimensions=required_dimensions,
            retired=retired,
            absolute_deadline_seconds=absolute_deadline_seconds,
            default_provider_cost_limit_micros=default_provider_cost_limit_micros,
            silence_window_seconds=silence_window_seconds,
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
