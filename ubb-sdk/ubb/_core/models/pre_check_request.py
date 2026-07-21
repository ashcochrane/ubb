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
  from ..models.pre_check_request_task_metadata_type_0 import PreCheckRequestTaskMetadataType0





T = TypeVar("T", bound="PreCheckRequest")



@_attrs_define
class PreCheckRequest:
    """ 
        Attributes:
            customer_id (UUID):
            external_task_id (str | Unset):  Default: ''.
            parent_task_id (None | Unset | UUID):
            provider_cost_limit_micros (int | None | Unset):
            start_task (bool | Unset):  Default: False.
            task_metadata (None | PreCheckRequestTaskMetadataType0 | Unset):
     """

    customer_id: UUID
    external_task_id: str | Unset = ''
    parent_task_id: None | Unset | UUID = UNSET
    provider_cost_limit_micros: int | None | Unset = UNSET
    start_task: bool | Unset = False
    task_metadata: None | PreCheckRequestTaskMetadataType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pre_check_request_task_metadata_type_0 import PreCheckRequestTaskMetadataType0
        customer_id = str(self.customer_id)

        external_task_id = self.external_task_id

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        elif isinstance(self.parent_task_id, UUID):
            parent_task_id = str(self.parent_task_id)
        else:
            parent_task_id = self.parent_task_id

        provider_cost_limit_micros: int | None | Unset
        if isinstance(self.provider_cost_limit_micros, Unset):
            provider_cost_limit_micros = UNSET
        else:
            provider_cost_limit_micros = self.provider_cost_limit_micros

        start_task = self.start_task

        task_metadata: dict[str, Any] | None | Unset
        if isinstance(self.task_metadata, Unset):
            task_metadata = UNSET
        elif isinstance(self.task_metadata, PreCheckRequestTaskMetadataType0):
            task_metadata = self.task_metadata.to_dict()
        else:
            task_metadata = self.task_metadata


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_id": customer_id,
        })
        if external_task_id is not UNSET:
            field_dict["external_task_id"] = external_task_id
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id
        if provider_cost_limit_micros is not UNSET:
            field_dict["provider_cost_limit_micros"] = provider_cost_limit_micros
        if start_task is not UNSET:
            field_dict["start_task"] = start_task
        if task_metadata is not UNSET:
            field_dict["task_metadata"] = task_metadata

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pre_check_request_task_metadata_type_0 import PreCheckRequestTaskMetadataType0
        d = dict(src_dict)
        customer_id = UUID(d.pop("customer_id"))




        external_task_id = d.pop("external_task_id", UNSET)

        def _parse_parent_task_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                parent_task_id_type_0 = UUID(data)



                return parent_task_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        def _parse_provider_cost_limit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        provider_cost_limit_micros = _parse_provider_cost_limit_micros(d.pop("provider_cost_limit_micros", UNSET))


        start_task = d.pop("start_task", UNSET)

        def _parse_task_metadata(data: object) -> None | PreCheckRequestTaskMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                task_metadata_type_0 = PreCheckRequestTaskMetadataType0.from_dict(data)



                return task_metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PreCheckRequestTaskMetadataType0 | Unset, data)

        task_metadata = _parse_task_metadata(d.pop("task_metadata", UNSET))


        pre_check_request = cls(
            customer_id=customer_id,
            external_task_id=external_task_id,
            parent_task_id=parent_task_id,
            provider_cost_limit_micros=provider_cost_limit_micros,
            start_task=start_task,
            task_metadata=task_metadata,
        )


        pre_check_request.additional_properties = d
        return pre_check_request

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
