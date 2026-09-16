from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.economic_measure_out import EconomicMeasureOut





T = TypeVar("T", bound="EconomicRowOut")



@_attrs_define
class EconomicRowOut:
    """ One bucket of the answer: what it groups, and each measure asked for.

    ⚠ **THE GROUPED VALUES ARE POSITIONAL, ALIGNED WITH THE REQUEST'S OWN
    `group_by`**, which the response echoes so the alignment is readable from
    the answer alone. The request already named the axes; repeating them once
    per row would say the same thing over and over, and the row key itself is
    settled vocabulary (`docs/adr/0005-declared-grouping-fields.md:191`).

        Attributes:
            grouping_field_value (list[None | str]):
            grouping_field_value_status (list[str]): Why this row has no value on the axis in the same position, where it
                has none: 'recorded' means the value beside it is the axis's value, 'not_recorded' means these events could have
                carried one and did not, and 'not_applicable' means this kind of row never carries one — a charge raised for a
                delivered piece of work names no supplier and no event type. The two absences are different facts and only one
                of them has a remedy.
            measures (list[EconomicMeasureOut]):
            bucket_start (None | str | Unset):
     """

    grouping_field_value: list[None | str]
    grouping_field_value_status: list[str]
    measures: list[EconomicMeasureOut]
    bucket_start: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.economic_measure_out import EconomicMeasureOut
        grouping_field_value = []
        for grouping_field_value_item_data in self.grouping_field_value:
            grouping_field_value_item: None | str
            grouping_field_value_item = grouping_field_value_item_data
            grouping_field_value.append(grouping_field_value_item)



        grouping_field_value_status = self.grouping_field_value_status



        measures = []
        for measures_item_data in self.measures:
            measures_item = measures_item_data.to_dict()
            measures.append(measures_item)



        bucket_start: None | str | Unset
        if isinstance(self.bucket_start, Unset):
            bucket_start = UNSET
        else:
            bucket_start = self.bucket_start


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "grouping_field_value": grouping_field_value,
            "grouping_field_value_status": grouping_field_value_status,
            "measures": measures,
        })
        if bucket_start is not UNSET:
            field_dict["bucket_start"] = bucket_start

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.economic_measure_out import EconomicMeasureOut
        d = dict(src_dict)
        grouping_field_value = []
        _grouping_field_value = d.pop("grouping_field_value")
        for grouping_field_value_item_data in (_grouping_field_value):
            def _parse_grouping_field_value_item(data: object) -> None | str:
                if data is None:
                    return data
                return cast(None | str, data)

            grouping_field_value_item = _parse_grouping_field_value_item(grouping_field_value_item_data)

            grouping_field_value.append(grouping_field_value_item)


        grouping_field_value_status = cast(list[str], d.pop("grouping_field_value_status"))


        measures = []
        _measures = d.pop("measures")
        for measures_item_data in (_measures):
            measures_item = EconomicMeasureOut.from_dict(measures_item_data)



            measures.append(measures_item)


        def _parse_bucket_start(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bucket_start = _parse_bucket_start(d.pop("bucket_start", UNSET))


        economic_row_out = cls(
            grouping_field_value=grouping_field_value,
            grouping_field_value_status=grouping_field_value_status,
            measures=measures,
            bucket_start=bucket_start,
        )


        economic_row_out.additional_properties = d
        return economic_row_out

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
