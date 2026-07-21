from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.invitation_out import InvitationOut





T = TypeVar("T", bound="InvitationListResponse")



@_attrs_define
class InvitationListResponse:
    """ 
        Attributes:
            data (list[InvitationOut]):
            has_more (bool):
            next_cursor (None | str | Unset):
     """

    data: list[InvitationOut]
    has_more: bool
    next_cursor: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.invitation_out import InvitationOut
        data = []
        for data_item_data in self.data:
            data_item = data_item_data.to_dict()
            data.append(data_item)



        has_more = self.has_more

        next_cursor: None | str | Unset
        if isinstance(self.next_cursor, Unset):
            next_cursor = UNSET
        else:
            next_cursor = self.next_cursor


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "data": data,
            "has_more": has_more,
        })
        if next_cursor is not UNSET:
            field_dict["next_cursor"] = next_cursor

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.invitation_out import InvitationOut
        d = dict(src_dict)
        data = []
        _data = d.pop("data")
        for data_item_data in (_data):
            data_item = InvitationOut.from_dict(data_item_data)



            data.append(data_item)


        has_more = d.pop("has_more")

        def _parse_next_cursor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        next_cursor = _parse_next_cursor(d.pop("next_cursor", UNSET))


        invitation_list_response = cls(
            data=data,
            has_more=has_more,
            next_cursor=next_cursor,
        )


        invitation_list_response.additional_properties = d
        return invitation_list_response

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
