from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.audit_record_out_metadata import AuditRecordOutMetadata





T = TypeVar("T", bound="AuditRecordOut")



@_attrs_define
class AuditRecordOut:
    """ 
        Attributes:
            action (str):
            actor_display (str):
            actor_id (str):
            actor_kind (str):
            correlation_id (str):
            created_at (str):
            id (str):
            metadata (AuditRecordOutMetadata):
            resource_id (str):
            resource_type (str):
     """

    action: str
    actor_display: str
    actor_id: str
    actor_kind: str
    correlation_id: str
    created_at: str
    id: str
    metadata: AuditRecordOutMetadata
    resource_id: str
    resource_type: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.audit_record_out_metadata import AuditRecordOutMetadata
        action = self.action

        actor_display = self.actor_display

        actor_id = self.actor_id

        actor_kind = self.actor_kind

        correlation_id = self.correlation_id

        created_at = self.created_at

        id = self.id

        metadata = self.metadata.to_dict()

        resource_id = self.resource_id

        resource_type = self.resource_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "action": action,
            "actor_display": actor_display,
            "actor_id": actor_id,
            "actor_kind": actor_kind,
            "correlation_id": correlation_id,
            "created_at": created_at,
            "id": id,
            "metadata": metadata,
            "resource_id": resource_id,
            "resource_type": resource_type,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.audit_record_out_metadata import AuditRecordOutMetadata
        d = dict(src_dict)
        action = d.pop("action")

        actor_display = d.pop("actor_display")

        actor_id = d.pop("actor_id")

        actor_kind = d.pop("actor_kind")

        correlation_id = d.pop("correlation_id")

        created_at = d.pop("created_at")

        id = d.pop("id")

        metadata = AuditRecordOutMetadata.from_dict(d.pop("metadata"))




        resource_id = d.pop("resource_id")

        resource_type = d.pop("resource_type")

        audit_record_out = cls(
            action=action,
            actor_display=actor_display,
            actor_id=actor_id,
            actor_kind=actor_kind,
            correlation_id=correlation_id,
            created_at=created_at,
            id=id,
            metadata=metadata,
            resource_id=resource_id,
            resource_type=resource_type,
        )


        audit_record_out.additional_properties = d
        return audit_record_out

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
