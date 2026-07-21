from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="PreCheckResponse")



@_attrs_define
class PreCheckResponse:
    """ 
        Attributes:
            allowed (bool):
            balance_micros (int | None | Unset):
            floor_snapshot_micros (int | None | Unset):
            parent_task_id (None | str | Unset):
            provider_cost_limit_micros (int | None | Unset):
            reason (None | str | Unset):
            task_id (None | str | Unset):
     """

    allowed: bool
    balance_micros: int | None | Unset = UNSET
    floor_snapshot_micros: int | None | Unset = UNSET
    parent_task_id: None | str | Unset = UNSET
    provider_cost_limit_micros: int | None | Unset = UNSET
    reason: None | str | Unset = UNSET
    task_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        allowed = self.allowed

        balance_micros: int | None | Unset
        if isinstance(self.balance_micros, Unset):
            balance_micros = UNSET
        else:
            balance_micros = self.balance_micros

        floor_snapshot_micros: int | None | Unset
        if isinstance(self.floor_snapshot_micros, Unset):
            floor_snapshot_micros = UNSET
        else:
            floor_snapshot_micros = self.floor_snapshot_micros

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        else:
            parent_task_id = self.parent_task_id

        provider_cost_limit_micros: int | None | Unset
        if isinstance(self.provider_cost_limit_micros, Unset):
            provider_cost_limit_micros = UNSET
        else:
            provider_cost_limit_micros = self.provider_cost_limit_micros

        reason: None | str | Unset
        if isinstance(self.reason, Unset):
            reason = UNSET
        else:
            reason = self.reason

        task_id: None | str | Unset
        if isinstance(self.task_id, Unset):
            task_id = UNSET
        else:
            task_id = self.task_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "allowed": allowed,
        })
        if balance_micros is not UNSET:
            field_dict["balance_micros"] = balance_micros
        if floor_snapshot_micros is not UNSET:
            field_dict["floor_snapshot_micros"] = floor_snapshot_micros
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if provider_cost_limit_micros is not UNSET:
            field_dict["provider_cost_limit_micros"] = provider_cost_limit_micros
        if reason is not UNSET:
            field_dict["reason"] = reason
        if task_id is not UNSET:
            field_dict["task_id"] = task_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        allowed = d.pop("allowed")

        def _parse_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        balance_micros = _parse_balance_micros(d.pop("balance_micros", UNSET))


        def _parse_floor_snapshot_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        floor_snapshot_micros = _parse_floor_snapshot_micros(d.pop("floor_snapshot_micros", UNSET))


        def _parse_parent_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_provider_cost_limit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_limit_micros = _parse_provider_cost_limit_micros(d.pop("provider_cost_limit_micros", UNSET))


        def _parse_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason = _parse_reason(d.pop("reason", UNSET))


        def _parse_task_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_id = _parse_task_id(d.pop("task_id", UNSET))


        pre_check_response = cls(
            allowed=allowed,
            balance_micros=balance_micros,
            floor_snapshot_micros=floor_snapshot_micros,
            parent_task_id=parent_task_id,
            provider_cost_limit_micros=provider_cost_limit_micros,
            reason=reason,
            task_id=task_id,
        )


        pre_check_response.additional_properties = d
        return pre_check_response

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
