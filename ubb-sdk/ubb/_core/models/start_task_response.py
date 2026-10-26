from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.start_task_response_status import StartTaskResponseStatus
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="StartTaskResponse")



@_attrs_define
class StartTaskResponse:
    """ What a start registered, or what its key already claimed.

    ⚠ THE REGISTRATION, NOT THE READ. A start answers *which unit of work is
    this, and did I just create it* — the identity, the altitude, and the facts
    the unit pinned. What it deliberately does NOT carry is the cost
    rollups: they are a read's answer, they are all zero on the call that
    creates the row, and `GET /api/v1/tasks/{task_id}` is one call away for a
    caller replaying an attempt that has since run up cost.

    ⚠ AND THE DECLARED GROUPING VALUES ARE NOT ECHOED. You just sent them,
    and a start that pinned something else says so by REFUSING rather than by
    handing back a corrected bag — so an echo could only ever repeat your own
    request back to you. The unit read one call away carries them as UBB holds
    them, keyed by your own declared key.

        Attributes:
            absolute_deadline_at (str): This unit of work's absolute deadline under the expiry policy resolved when it was
                started: its registration plus how long its kind of work could then run at all — the declared kind's own
                deadline, else the workspace default, else UBB's backstop of six hours. A replay of the start answers this same
                value. It is a snapshot, not a promise: UBB enforces the policy as it stands when it checks, so a later change
                to the declaration or the workspace default can expire the unit earlier or later than this. Two further rules
                can end it sooner: work that has never reported usage is expired once it is an hour old, and where the workspace
                does not enforce, UBB's hourly safety net does the expiring and never before the unit is an hour old. Never
                null: the absolute deadline cannot be switched off.
            created_at (str):
            replayed (bool):
            silence_window_seconds (int | None): How long this unit of work could go without a usage report, counted from
                its last one, before UBB expires it — under the expiry policy resolved when it was started, on the same ladder
                as `absolute_deadline_at` (UBB's backstop is fifteen minutes). A replay of the start answers this same value;
                UBB enforces the policy as it stands when it checks, so a later change can move it. Null where no silence window
                applied when the unit was started. Silence is counted from the last report, so work that has never reported is
                not measured on it — it is expired once it is an hour old instead.
            status (StartTaskResponseStatus):
            task_id (str):
            agreed_price_micros (int | None | Unset):
            external_task_id (str | Unset):  Default: ''.
            parent_task_id (None | str | Unset):
            task_cogs_ceiling_micros (int | None | Unset):
            task_type (str | Unset):  Default: ''.
     """

    absolute_deadline_at: str
    created_at: str
    replayed: bool
    silence_window_seconds: int | None
    status: StartTaskResponseStatus
    task_id: str
    agreed_price_micros: int | None | Unset = UNSET
    external_task_id: str | Unset = ''
    parent_task_id: None | str | Unset = UNSET
    task_cogs_ceiling_micros: int | None | Unset = UNSET
    task_type: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        absolute_deadline_at = self.absolute_deadline_at

        created_at = self.created_at

        replayed = self.replayed

        silence_window_seconds: int | None
        silence_window_seconds = self.silence_window_seconds

        status = self.status.value

        task_id = self.task_id

        agreed_price_micros: int | None | Unset
        if isinstance(self.agreed_price_micros, Unset):
            agreed_price_micros = UNSET
        else:
            agreed_price_micros = self.agreed_price_micros

        external_task_id = self.external_task_id

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        else:
            parent_task_id = self.parent_task_id

        task_cogs_ceiling_micros: int | None | Unset
        if isinstance(self.task_cogs_ceiling_micros, Unset):
            task_cogs_ceiling_micros = UNSET
        else:
            task_cogs_ceiling_micros = self.task_cogs_ceiling_micros

        task_type = self.task_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "absolute_deadline_at": absolute_deadline_at,
            "created_at": created_at,
            "replayed": replayed,
            "silence_window_seconds": silence_window_seconds,
            "status": status,
            "task_id": task_id,
        })
        if agreed_price_micros is not UNSET:
            field_dict["agreed_price_micros"] = agreed_price_micros
        if external_task_id is not UNSET:
            field_dict["external_task_id"] = external_task_id
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if task_cogs_ceiling_micros is not UNSET:
            field_dict["task_cogs_ceiling_micros"] = task_cogs_ceiling_micros
        if task_type is not UNSET:
            field_dict["task_type"] = task_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        absolute_deadline_at = d.pop("absolute_deadline_at")

        created_at = d.pop("created_at")

        replayed = d.pop("replayed")

        def _parse_silence_window_seconds(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        silence_window_seconds = _parse_silence_window_seconds(d.pop("silence_window_seconds"))


        status = StartTaskResponseStatus(d.pop("status"))




        task_id = d.pop("task_id")

        def _parse_agreed_price_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        agreed_price_micros = _parse_agreed_price_micros(d.pop("agreed_price_micros", UNSET))


        external_task_id = d.pop("external_task_id", UNSET)

        def _parse_parent_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_task_cogs_ceiling_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        task_cogs_ceiling_micros = _parse_task_cogs_ceiling_micros(d.pop("task_cogs_ceiling_micros", UNSET))


        task_type = d.pop("task_type", UNSET)

        start_task_response = cls(
            absolute_deadline_at=absolute_deadline_at,
            created_at=created_at,
            replayed=replayed,
            silence_window_seconds=silence_window_seconds,
            status=status,
            task_id=task_id,
            agreed_price_micros=agreed_price_micros,
            external_task_id=external_task_id,
            parent_task_id=parent_task_id,
            task_cogs_ceiling_micros=task_cogs_ceiling_micros,
            task_type=task_type,
        )


        start_task_response.additional_properties = d
        return start_task_response

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
