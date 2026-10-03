from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.close_task_response import CloseTaskResponse
  from ..models.start_task_response import StartTaskResponse





T = TypeVar("T", bound="IntegrationBlueprintVerificationUnit")



@_attrs_define
class IntegrationBlueprintVerificationUnit:
    """ One unit of work the verification started, as its start and its close
    answered. Either is null where the run stopped before it.

        Attributes:
            task_type (str):
            close (CloseTaskResponse | None | Unset):
            start (None | StartTaskResponse | Unset):
     """

    task_type: str
    close: CloseTaskResponse | None | Unset = UNSET
    start: None | StartTaskResponse | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.close_task_response import CloseTaskResponse
        from ..models.start_task_response import StartTaskResponse
        task_type = self.task_type

        close: dict[str, Any] | None | Unset
        if isinstance(self.close, Unset):
            close = UNSET
        elif isinstance(self.close, CloseTaskResponse):
            close = self.close.to_dict()
        else:
            close = self.close

        start: dict[str, Any] | None | Unset
        if isinstance(self.start, Unset):
            start = UNSET
        elif isinstance(self.start, StartTaskResponse):
            start = self.start.to_dict()
        else:
            start = self.start


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "task_type": task_type,
        })
        if close is not UNSET:
            field_dict["close"] = close
        if start is not UNSET:
            field_dict["start"] = start

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.close_task_response import CloseTaskResponse
        from ..models.start_task_response import StartTaskResponse
        d = dict(src_dict)
        task_type = d.pop("task_type")

        def _parse_close(data: object) -> CloseTaskResponse | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                close_type_0 = CloseTaskResponse.from_dict(data)



                return close_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CloseTaskResponse | None | Unset, data)

        close = _parse_close(d.pop("close", UNSET))


        def _parse_start(data: object) -> None | StartTaskResponse | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                start_type_0 = StartTaskResponse.from_dict(data)



                return start_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | StartTaskResponse | Unset, data)

        start = _parse_start(d.pop("start", UNSET))


        integration_blueprint_verification_unit = cls(
            task_type=task_type,
            close=close,
            start=start,
        )


        integration_blueprint_verification_unit.additional_properties = d
        return integration_blueprint_verification_unit

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
