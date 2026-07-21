from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.rate_change_in import RateChangeIn





T = TypeVar("T", bound="PublishIn")



@_attrs_define
class PublishIn:
    """ 
        Attributes:
            changes (list[RateChangeIn]):
     """

    changes: list[RateChangeIn]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.rate_change_in import RateChangeIn
        changes = []
        for changes_item_data in self.changes:
            changes_item = changes_item_data.to_dict()
            changes.append(changes_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "changes": changes,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rate_change_in import RateChangeIn
        d = dict(src_dict)
        changes = []
        _changes = d.pop("changes")
        for changes_item_data in (_changes):
            changes_item = RateChangeIn.from_dict(changes_item_data)



            changes.append(changes_item)


        publish_in = cls(
            changes=changes,
        )


        publish_in.additional_properties = d
        return publish_in

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
