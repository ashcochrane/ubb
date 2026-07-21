from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="MemberOut")



@_attrs_define
class MemberOut:
    """ 
        Attributes:
            created_at (str):
            email (str):
            id (str):
            role (str):
            status (str):
            activated_at (None | str | Unset):
            clerk_user_id (str | Unset):  Default: ''.
     """

    created_at: str
    email: str
    id: str
    role: str
    status: str
    activated_at: None | str | Unset = UNSET
    clerk_user_id: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        email = self.email

        id = self.id

        role = self.role

        status = self.status

        activated_at: None | str | Unset
        if isinstance(self.activated_at, Unset):
            activated_at = UNSET
        else:
            activated_at = self.activated_at

        clerk_user_id = self.clerk_user_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "email": email,
            "id": id,
            "role": role,
            "status": status,
        })
        if activated_at is not UNSET:
            field_dict["activated_at"] = activated_at
        if clerk_user_id is not UNSET:
            field_dict["clerk_user_id"] = clerk_user_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        email = d.pop("email")

        id = d.pop("id")

        role = d.pop("role")

        status = d.pop("status")

        def _parse_activated_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        activated_at = _parse_activated_at(d.pop("activated_at", UNSET))


        clerk_user_id = d.pop("clerk_user_id", UNSET)

        member_out = cls(
            created_at=created_at,
            email=email,
            id=id,
            role=role,
            status=status,
            activated_at=activated_at,
            clerk_user_id=clerk_user_id,
        )


        member_out.additional_properties = d
        return member_out

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
