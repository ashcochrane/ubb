from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.usage_timeseries_response_series_item import UsageTimeseriesResponseSeriesItem





T = TypeVar("T", bound="UsageTimeseriesResponse")



@_attrs_define
class UsageTimeseriesResponse:
    """ 
        Attributes:
            granularity (str):
            series (list[UsageTimeseriesResponseSeriesItem]):
            group_by (str | Unset):  Default: ''.
     """

    granularity: str
    series: list[UsageTimeseriesResponseSeriesItem]
    group_by: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_timeseries_response_series_item import UsageTimeseriesResponseSeriesItem
        granularity = self.granularity

        series = []
        for series_item_data in self.series:
            series_item = series_item_data.to_dict()
            series.append(series_item)



        group_by = self.group_by


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "granularity": granularity,
            "series": series,
        })
        if group_by is not UNSET:
            field_dict["group_by"] = group_by

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_timeseries_response_series_item import UsageTimeseriesResponseSeriesItem
        d = dict(src_dict)
        granularity = d.pop("granularity")

        series = []
        _series = d.pop("series")
        for series_item_data in (_series):
            series_item = UsageTimeseriesResponseSeriesItem.from_dict(series_item_data)



            series.append(series_item)


        group_by = d.pop("group_by", UNSET)

        usage_timeseries_response = cls(
            granularity=granularity,
            series=series,
            group_by=group_by,
        )


        usage_timeseries_response.additional_properties = d
        return usage_timeseries_response

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
