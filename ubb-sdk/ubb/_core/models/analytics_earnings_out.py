from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.referrer_earnings_summary import ReferrerEarningsSummary





T = TypeVar("T", bound="AnalyticsEarningsOut")



@_attrs_define
class AnalyticsEarningsOut:
    """ 
        Attributes:
            period_end (str):
            period_start (str):
            referrers (list[ReferrerEarningsSummary]):
            total_earned_micros (int):
     """

    period_end: str
    period_start: str
    referrers: list[ReferrerEarningsSummary]
    total_earned_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.referrer_earnings_summary import ReferrerEarningsSummary
        period_end = self.period_end

        period_start = self.period_start

        referrers = []
        for referrers_item_data in self.referrers:
            referrers_item = referrers_item_data.to_dict()
            referrers.append(referrers_item)



        total_earned_micros = self.total_earned_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "period_end": period_end,
            "period_start": period_start,
            "referrers": referrers,
            "total_earned_micros": total_earned_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.referrer_earnings_summary import ReferrerEarningsSummary
        d = dict(src_dict)
        period_end = d.pop("period_end")

        period_start = d.pop("period_start")

        referrers = []
        _referrers = d.pop("referrers")
        for referrers_item_data in (_referrers):
            referrers_item = ReferrerEarningsSummary.from_dict(referrers_item_data)



            referrers.append(referrers_item)


        total_earned_micros = d.pop("total_earned_micros")

        analytics_earnings_out = cls(
            period_end=period_end,
            period_start=period_start,
            referrers=referrers,
            total_earned_micros=total_earned_micros,
        )


        analytics_earnings_out.additional_properties = d
        return analytics_earnings_out

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
