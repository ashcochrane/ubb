from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.measurement_out import MeasurementOut





T = TypeVar("T", bound="MeasurementListOut")



@_attrs_define
class MeasurementListOut:
    """ 
        Attributes:
            measurements (list[MeasurementOut]):
     """

    measurements: list[MeasurementOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.measurement_out import MeasurementOut
        measurements = []
        for measurements_item_data in self.measurements:
            measurements_item = measurements_item_data.to_dict()
            measurements.append(measurements_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "measurements": measurements,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.measurement_out import MeasurementOut
        d = dict(src_dict)
        measurements = []
        _measurements = d.pop("measurements")
        for measurements_item_data in (_measurements):
            measurements_item = MeasurementOut.from_dict(measurements_item_data)



            measurements.append(measurements_item)


        measurement_list_out = cls(
            measurements=measurements,
        )


        measurement_list_out.additional_properties = d
        return measurement_list_out

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
