from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.me_recorded_events_out_status import MeRecordedEventsOutStatus
from typing import cast






T = TypeVar("T", bound="MeRecordedEventsOut")



@_attrs_define
class MeRecordedEventsOut:
    """ How many metered usage events you recorded in the window.

    `status` is `known`, or `unavailable_outside_retention_horizon` where the
    window reaches back past what UBB still holds (`available_from` says
    from when it can start) — `count` is then null, never a zero.

        Attributes:
            available_from (None | str): The first day this count can be stated from, non-null exactly where `status` is
                `unavailable_outside_retention_horizon`.
            count (int | None): How many metered usage events the window holds, or null where no figure can be stated —
                never a zero standing in.
            status (MeRecordedEventsOutStatus):
     """

    available_from: None | str
    count: int | None
    status: MeRecordedEventsOutStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        available_from: None | str
        available_from = self.available_from

        count: int | None
        count = self.count

        status = self.status.value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "available_from": available_from,
            "count": count,
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_available_from(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        available_from = _parse_available_from(d.pop("available_from"))


        def _parse_count(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        count = _parse_count(d.pop("count"))


        status = MeRecordedEventsOutStatus(d.pop("status"))




        me_recorded_events_out = cls(
            available_from=available_from,
            count=count,
            status=status,
        )


        me_recorded_events_out.additional_properties = d
        return me_recorded_events_out

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
