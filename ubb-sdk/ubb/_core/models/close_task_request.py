from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.close_task_request_outcome import CloseTaskRequestOutcome
from ..models.close_task_request_outcome_reason_type_0 import CloseTaskRequestOutcomeReasonType0
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="CloseTaskRequest")



@_attrs_define
class CloseTaskRequest:
    """ The declaration that ends a unit of work.

    ONE call and ONE mandatory field. Two endpoints (`/close` and `/fail`) was
    rejected as two of everything, and optional-with-a-delivered-default was
    rejected on the strongest rule available: THE FORGIVING PATH MUST NEVER BE
    THE MONEY-MOVING ONE. A dropped field, a stale example or an old client
    would otherwise bill a customer for work that failed.

        Attributes:
            outcome (CloseTaskRequestOutcome):
            outcome_reason (CloseTaskRequestOutcomeReasonType0 | None | Unset):
            reason_detail (None | str | Unset):
     """

    outcome: CloseTaskRequestOutcome
    outcome_reason: CloseTaskRequestOutcomeReasonType0 | None | Unset = UNSET
    reason_detail: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        outcome = self.outcome.value

        outcome_reason: None | str | Unset
        if isinstance(self.outcome_reason, Unset):
            outcome_reason = UNSET
        elif isinstance(self.outcome_reason, CloseTaskRequestOutcomeReasonType0):
            outcome_reason = self.outcome_reason.value
        else:
            outcome_reason = self.outcome_reason

        reason_detail: None | str | Unset
        if isinstance(self.reason_detail, Unset):
            reason_detail = UNSET
        else:
            reason_detail = self.reason_detail


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "outcome": outcome,
        })
        if outcome_reason is not UNSET:
            field_dict["outcome_reason"] = outcome_reason
        if reason_detail is not UNSET:
            field_dict["reason_detail"] = reason_detail

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        outcome = CloseTaskRequestOutcome(d.pop("outcome"))




        def _parse_outcome_reason(data: object) -> CloseTaskRequestOutcomeReasonType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                outcome_reason_type_0 = CloseTaskRequestOutcomeReasonType0(data)



                return outcome_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CloseTaskRequestOutcomeReasonType0 | None | Unset, data)

        outcome_reason = _parse_outcome_reason(d.pop("outcome_reason", UNSET))


        def _parse_reason_detail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason_detail = _parse_reason_detail(d.pop("reason_detail", UNSET))


        close_task_request = cls(
            outcome=outcome,
            outcome_reason=outcome_reason,
            reason_detail=reason_detail,
        )


        close_task_request.additional_properties = d
        return close_task_request

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
