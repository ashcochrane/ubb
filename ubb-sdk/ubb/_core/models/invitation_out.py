from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="InvitationOut")



@_attrs_define
class InvitationOut:
    """ 
        Attributes:
            created_at (str):
            email (str):
            id (str):
            role (str):
            status (str):
     """

    created_at: str
    email: str
    id: str
    role: str
    status: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        email = self.email

        id = self.id

        role = self.role

        status = self.status


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "email": email,
            "id": id,
            "role": role,
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        email = d.pop("email")

        id = d.pop("id")

        role = d.pop("role")

        status = d.pop("status")

        invitation_out = cls(
            created_at=created_at,
            email=email,
            id=id,
            role=role,
            status=status,
        )


        invitation_out.additional_properties = d
        return invitation_out

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
