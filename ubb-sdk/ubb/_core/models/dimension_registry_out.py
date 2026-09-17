from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.dimension_def_out import DimensionDefOut





T = TypeVar("T", bound="DimensionRegistryOut")



@_attrs_define
class DimensionRegistryOut:
    """ 
        Attributes:
            grouping_fields (list[DimensionDefOut]):
     """

    grouping_fields: list[DimensionDefOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.dimension_def_out import DimensionDefOut
        grouping_fields = []
        for grouping_fields_item_data in self.grouping_fields:
            grouping_fields_item = grouping_fields_item_data.to_dict()
            grouping_fields.append(grouping_fields_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "grouping_fields": grouping_fields,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dimension_def_out import DimensionDefOut
        d = dict(src_dict)
        grouping_fields = []
        _grouping_fields = d.pop("grouping_fields")
        for grouping_fields_item_data in (_grouping_fields):
            grouping_fields_item = DimensionDefOut.from_dict(grouping_fields_item_data)



            grouping_fields.append(grouping_fields_item)


        dimension_registry_out = cls(
            grouping_fields=grouping_fields,
        )


        dimension_registry_out.additional_properties = d
        return dimension_registry_out

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
