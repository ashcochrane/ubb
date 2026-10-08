from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.integration_blueprint_verification_record_in_measurements import IntegrationBlueprintVerificationRecordInMeasurements





T = TypeVar("T", bound="IntegrationBlueprintVerificationRecordIn")



@_attrs_define
class IntegrationBlueprintVerificationRecordIn:
    """ One recording the verification makes: the Event Type it claims, and
    the sample values a tenant's code would send for it.

    `measurements`, `provider_cost_micros` and `provider_response_cost_micros`
    are the same fields, with the same rules, as on a recording.
    `subtask_type` records this event under a Subtask of that kind, which must
    be one the Blueprint selected; left out, the event is recorded under the
    Task itself.

        Attributes:
            event_type (str):
            measurements (IntegrationBlueprintVerificationRecordInMeasurements | Unset):
            provider_cost_micros (int | None | Unset): The supplier cost of this call (COGS), supplied directly by the
                caller. Admissible only where the Event Type's last publication declares costing_method `reported` with a
                reported-cost mapping whose source_kind is `caller_supplied`, and refused anywhere else rather than dropped. A
                figure obtained from the provider's response is sent as `provider_response_cost_micros` instead, never here.
            provider_response_cost_micros (int | None | Unset): The supplier cost of this call (COGS), as the caller
                obtained it from the provider's response. Admissible only where the Event Type's last publication declares
                costing_method `reported` with a reported-cost mapping whose source_kind is `provider_response`, and refused
                anywhere else rather than dropped; never sent together with `provider_cost_micros`. UBB cannot verify how the
                figure was obtained: it admits it because the declared source says that is where it comes from. It is a
                transport, not a second cost: the figure is recorded as the event's supplier cost and read back as
                `provider_cost_micros`, and is not echoed under its own name.
            subtask_type (None | str | Unset):
     """

    event_type: str
    measurements: IntegrationBlueprintVerificationRecordInMeasurements | Unset = UNSET
    provider_cost_micros: int | None | Unset = UNSET
    provider_response_cost_micros: int | None | Unset = UNSET
    subtask_type: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_blueprint_verification_record_in_measurements import IntegrationBlueprintVerificationRecordInMeasurements
        event_type = self.event_type

        measurements: dict[str, Any] | Unset = UNSET
        if not isinstance(self.measurements, Unset):
            measurements = self.measurements.to_dict()

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros

        provider_response_cost_micros: int | None | Unset
        if isinstance(self.provider_response_cost_micros, Unset):
            provider_response_cost_micros = UNSET
        else:
            provider_response_cost_micros = self.provider_response_cost_micros

        subtask_type: None | str | Unset
        if isinstance(self.subtask_type, Unset):
            subtask_type = UNSET
        else:
            subtask_type = self.subtask_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event_type": event_type,
        })
        if measurements is not UNSET:
            field_dict["measurements"] = measurements
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
        if provider_response_cost_micros is not UNSET:
            field_dict["provider_response_cost_micros"] = provider_response_cost_micros
        if subtask_type is not UNSET:
            field_dict["subtask_type"] = subtask_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_blueprint_verification_record_in_measurements import IntegrationBlueprintVerificationRecordInMeasurements
        d = dict(src_dict)
        event_type = d.pop("event_type")

        _measurements = d.pop("measurements", UNSET)
        measurements: IntegrationBlueprintVerificationRecordInMeasurements | Unset
        if isinstance(_measurements,  Unset):
            measurements = UNSET
        else:
            measurements = IntegrationBlueprintVerificationRecordInMeasurements.from_dict(_measurements)




        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


        def _parse_provider_response_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_response_cost_micros = _parse_provider_response_cost_micros(d.pop("provider_response_cost_micros", UNSET))


        def _parse_subtask_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        subtask_type = _parse_subtask_type(d.pop("subtask_type", UNSET))


        integration_blueprint_verification_record_in = cls(
            event_type=event_type,
            measurements=measurements,
            provider_cost_micros=provider_cost_micros,
            provider_response_cost_micros=provider_response_cost_micros,
            subtask_type=subtask_type,
        )


        integration_blueprint_verification_record_in.additional_properties = d
        return integration_blueprint_verification_record_in

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
