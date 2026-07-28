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
            dimensions (list[DimensionDefOut]):
     """

    dimensions: list[DimensionDefOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.dimension_def_out import DimensionDefOut
        dimensions = []
        for dimensions_item_data in self.dimensions:
            dimensions_item = dimensions_item_data.to_dict()
            dimensions.append(dimensions_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "dimensions": dimensions,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dimension_def_out import DimensionDefOut
        d = dict(src_dict)
        dimensions = []
        _dimensions = d.pop("dimensions")
        for dimensions_item_data in (_dimensions):
            dimensions_item = DimensionDefOut.from_dict(dimensions_item_data)



            dimensions.append(dimensions_item)


        dimension_registry_out = cls(
            dimensions=dimensions,
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
