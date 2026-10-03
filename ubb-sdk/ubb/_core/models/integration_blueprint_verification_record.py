from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.record_usage_response import RecordUsageResponse





T = TypeVar("T", bound="IntegrationBlueprintVerificationRecord")



@_attrs_define
class IntegrationBlueprintVerificationRecord:
    """ One recording, as it was acknowledged, and what the verification read
    off the acknowledgement.

    `replay` is the same recording sent a second time with the same
    idempotency key; it must name the same event. Its running totals are
    null by design, as on any replay.

    `missing_required_measurement_keys` names each Measurement the Event Type
    declares required for a complete cost and the recording did not carry.
    `complete` is true when the recording carried every one of them, its cost
    is not `unresolved`, and the replay named the same event.

        Attributes:
            complete (bool):
            event_type (str):
            missing_required_measurement_keys (list[str]):
            acknowledgement (None | RecordUsageResponse | Unset):
            replay (None | RecordUsageResponse | Unset):
            subtask_type (None | str | Unset):
     """

    complete: bool
    event_type: str
    missing_required_measurement_keys: list[str]
    acknowledgement: None | RecordUsageResponse | Unset = UNSET
    replay: None | RecordUsageResponse | Unset = UNSET
    subtask_type: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.record_usage_response import RecordUsageResponse
        complete = self.complete

        event_type = self.event_type

        missing_required_measurement_keys = self.missing_required_measurement_keys



        acknowledgement: dict[str, Any] | None | Unset
        if isinstance(self.acknowledgement, Unset):
            acknowledgement = UNSET
        elif isinstance(self.acknowledgement, RecordUsageResponse):
            acknowledgement = self.acknowledgement.to_dict()
        else:
            acknowledgement = self.acknowledgement

        replay: dict[str, Any] | None | Unset
        if isinstance(self.replay, Unset):
            replay = UNSET
        elif isinstance(self.replay, RecordUsageResponse):
            replay = self.replay.to_dict()
        else:
            replay = self.replay

        subtask_type: None | str | Unset
        if isinstance(self.subtask_type, Unset):
            subtask_type = UNSET
        else:
            subtask_type = self.subtask_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "complete": complete,
            "event_type": event_type,
            "missing_required_measurement_keys": missing_required_measurement_keys,
        })
        if acknowledgement is not UNSET:
            field_dict["acknowledgement"] = acknowledgement
        if replay is not UNSET:
            field_dict["replay"] = replay
        if subtask_type is not UNSET:
            field_dict["subtask_type"] = subtask_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.record_usage_response import RecordUsageResponse
        d = dict(src_dict)
        complete = d.pop("complete")

        event_type = d.pop("event_type")

        missing_required_measurement_keys = cast(list[str], d.pop("missing_required_measurement_keys"))


        def _parse_acknowledgement(data: object) -> None | RecordUsageResponse | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                acknowledgement_type_0 = RecordUsageResponse.from_dict(data)



                return acknowledgement_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponse | Unset, data)

        acknowledgement = _parse_acknowledgement(d.pop("acknowledgement", UNSET))


        def _parse_replay(data: object) -> None | RecordUsageResponse | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                replay_type_0 = RecordUsageResponse.from_dict(data)



                return replay_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RecordUsageResponse | Unset, data)

        replay = _parse_replay(d.pop("replay", UNSET))


        def _parse_subtask_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        subtask_type = _parse_subtask_type(d.pop("subtask_type", UNSET))


        integration_blueprint_verification_record = cls(
            complete=complete,
            event_type=event_type,
            missing_required_measurement_keys=missing_required_measurement_keys,
            acknowledgement=acknowledgement,
            replay=replay,
            subtask_type=subtask_type,
        )


        integration_blueprint_verification_record.additional_properties = d
        return integration_blueprint_verification_record

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
