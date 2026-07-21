from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.past_limit_report_response_episodes_item import PastLimitReportResponseEpisodesItem
  from ..models.past_limit_report_response_totals_per_limit import PastLimitReportResponseTotalsPerLimit





T = TypeVar("T", bound="PastLimitReportResponse")



@_attrs_define
class PastLimitReportResponse:
    """ 
        Attributes:
            billing_owner_id (str):
            customer_id (str):
            episodes (list[PastLimitReportResponseEpisodesItem]):
            totals_per_limit (PastLimitReportResponseTotalsPerLimit):
            since (None | str | Unset):
            until (None | str | Unset):
     """

    billing_owner_id: str
    customer_id: str
    episodes: list[PastLimitReportResponseEpisodesItem]
    totals_per_limit: PastLimitReportResponseTotalsPerLimit
    since: None | str | Unset = UNSET
    until: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.past_limit_report_response_episodes_item import PastLimitReportResponseEpisodesItem
        from ..models.past_limit_report_response_totals_per_limit import PastLimitReportResponseTotalsPerLimit
        billing_owner_id = self.billing_owner_id

        customer_id = self.customer_id

        episodes = []
        for episodes_item_data in self.episodes:
            episodes_item = episodes_item_data.to_dict()
            episodes.append(episodes_item)



        totals_per_limit = self.totals_per_limit.to_dict()

        since: None | str | Unset
        if isinstance(self.since, Unset):
            since = UNSET
        else:
            since = self.since

        until: None | str | Unset
        if isinstance(self.until, Unset):
            until = UNSET
        else:
            until = self.until


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "billing_owner_id": billing_owner_id,
            "customer_id": customer_id,
            "episodes": episodes,
            "totals_per_limit": totals_per_limit,
        })
        if since is not UNSET:
            field_dict["since"] = since
        if until is not UNSET:
            field_dict["until"] = until

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.past_limit_report_response_episodes_item import PastLimitReportResponseEpisodesItem
        from ..models.past_limit_report_response_totals_per_limit import PastLimitReportResponseTotalsPerLimit
        d = dict(src_dict)
        billing_owner_id = d.pop("billing_owner_id")

        customer_id = d.pop("customer_id")

        episodes = []
        _episodes = d.pop("episodes")
        for episodes_item_data in (_episodes):
            episodes_item = PastLimitReportResponseEpisodesItem.from_dict(episodes_item_data)



            episodes.append(episodes_item)


        totals_per_limit = PastLimitReportResponseTotalsPerLimit.from_dict(d.pop("totals_per_limit"))




        def _parse_since(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        since = _parse_since(d.pop("since", UNSET))


        def _parse_until(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        until = _parse_until(d.pop("until", UNSET))


        past_limit_report_response = cls(
            billing_owner_id=billing_owner_id,
            customer_id=customer_id,
            episodes=episodes,
            totals_per_limit=totals_per_limit,
            since=since,
            until=until,
        )


        past_limit_report_response.additional_properties = d
        return past_limit_report_response

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
