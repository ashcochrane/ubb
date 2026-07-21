from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID

if TYPE_CHECKING:
  from ..models.usage_event_out_metadata import UsageEventOutMetadata





T = TypeVar("T", bound="UsageEventOut")



@_attrs_define
class UsageEventOut:
    """ 
        Attributes:
            effective_at (str):
            id (UUID):
            metadata (UsageEventOutMetadata):
            request_id (str):
            billed_cost_micros (int | None | Unset):
            event_type (str | Unset):  Default: ''.
            provider (str | Unset):  Default: ''.
            provider_cost_micros (int | None | Unset):
            stop_context (list[Any] | None | Unset):
            units (int | None | Unset):
     """

    effective_at: str
    id: UUID
    metadata: UsageEventOutMetadata
    request_id: str
    billed_cost_micros: int | None | Unset = UNSET
    event_type: str | Unset = ''
    provider: str | Unset = ''
    provider_cost_micros: int | None | Unset = UNSET
    stop_context: list[Any] | None | Unset = UNSET
    units: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_event_out_metadata import UsageEventOutMetadata
        effective_at = self.effective_at

        id = str(self.id)

        metadata = self.metadata.to_dict()

        request_id = self.request_id

        billed_cost_micros: int | None | Unset
        if isinstance(self.billed_cost_micros, Unset):
            billed_cost_micros = UNSET
        else:
            billed_cost_micros = self.billed_cost_micros

        event_type = self.event_type

        provider = self.provider

        provider_cost_micros: int | None | Unset
        if isinstance(self.provider_cost_micros, Unset):
            provider_cost_micros = UNSET
        else:
            provider_cost_micros = self.provider_cost_micros

        stop_context: list[Any] | None | Unset
        if isinstance(self.stop_context, Unset):
            stop_context = UNSET
        elif isinstance(self.stop_context, list):
            stop_context = self.stop_context


        else:
            stop_context = self.stop_context

        units: int | None | Unset
        if isinstance(self.units, Unset):
            units = UNSET
        else:
            units = self.units


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "effective_at": effective_at,
            "id": id,
            "metadata": metadata,
            "request_id": request_id,
        })
        if billed_cost_micros is not UNSET:
            field_dict["billed_cost_micros"] = billed_cost_micros
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if provider is not UNSET:
            field_dict["provider"] = provider
        if provider_cost_micros is not UNSET:
            field_dict["provider_cost_micros"] = provider_cost_micros
        if stop_context is not UNSET:
            field_dict["stop_context"] = stop_context
        if units is not UNSET:
            field_dict["units"] = units

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_event_out_metadata import UsageEventOutMetadata
        d = dict(src_dict)
        effective_at = d.pop("effective_at")

        id = UUID(d.pop("id"))




        metadata = UsageEventOutMetadata.from_dict(d.pop("metadata"))




        request_id = d.pop("request_id")

        def _parse_billed_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        billed_cost_micros = _parse_billed_cost_micros(d.pop("billed_cost_micros", UNSET))


        event_type = d.pop("event_type", UNSET)

        provider = d.pop("provider", UNSET)

        def _parse_provider_cost_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_micros = _parse_provider_cost_micros(d.pop("provider_cost_micros", UNSET))


        def _parse_stop_context(data: object) -> list[Any] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                stop_context_type_0 = cast(list[Any], data)

                return stop_context_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None | Unset, data)

        stop_context = _parse_stop_context(d.pop("stop_context", UNSET))


        def _parse_units(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        units = _parse_units(d.pop("units", UNSET))


        usage_event_out = cls(
            effective_at=effective_at,
            id=id,
            metadata=metadata,
            request_id=request_id,
            billed_cost_micros=billed_cost_micros,
            event_type=event_type,
            provider=provider,
            provider_cost_micros=provider_cost_micros,
            stop_context=stop_context,
            units=units,
        )


        usage_event_out.additional_properties = d
        return usage_event_out

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
