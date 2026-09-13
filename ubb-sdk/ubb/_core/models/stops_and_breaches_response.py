from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.ceiling_episode_row import CeilingEpisodeRow
  from ..models.customer_spend_pool_episode_row import CustomerSpendPoolEpisodeRow
  from ..models.spend_control_family_totals_row import SpendControlFamilyTotalsRow
  from ..models.wallet_policy_episode_row import WalletPolicyEpisodeRow





T = TypeVar("T", bound="StopsAndBreachesResponse")



@_attrs_define
class StopsAndBreachesResponse:
    """ What was spent past a stop, and why (#153 §10): every control that
    fired and had an enforcement consequence, in the window, as typed rows
    discriminated by `control_family`. Expiries and admission control belong
    to neither report. `since`/`until` echo the window applied — a window
    the caller left open is bounded to 366 days ending now.

        Attributes:
            rows (list[CeilingEpisodeRow | CustomerSpendPoolEpisodeRow | WalletPolicyEpisodeRow]):
            since (datetime.datetime):
            totals (list[SpendControlFamilyTotalsRow]):
            until (datetime.datetime):
     """

    rows: list[CeilingEpisodeRow | CustomerSpendPoolEpisodeRow | WalletPolicyEpisodeRow]
    since: datetime.datetime
    totals: list[SpendControlFamilyTotalsRow]
    until: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.ceiling_episode_row import CeilingEpisodeRow
        from ..models.customer_spend_pool_episode_row import CustomerSpendPoolEpisodeRow
        from ..models.spend_control_family_totals_row import SpendControlFamilyTotalsRow
        from ..models.wallet_policy_episode_row import WalletPolicyEpisodeRow
        rows = []
        for rows_item_data in self.rows:
            rows_item: dict[str, Any]
            if isinstance(rows_item_data, CeilingEpisodeRow):
                rows_item = rows_item_data.to_dict()
            elif isinstance(rows_item_data, CustomerSpendPoolEpisodeRow):
                rows_item = rows_item_data.to_dict()
            else:
                rows_item = rows_item_data.to_dict()

            rows.append(rows_item)



        since = self.since.isoformat()

        totals = []
        for totals_item_data in self.totals:
            totals_item = totals_item_data.to_dict()
            totals.append(totals_item)



        until = self.until.isoformat()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "rows": rows,
            "since": since,
            "totals": totals,
            "until": until,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ceiling_episode_row import CeilingEpisodeRow
        from ..models.customer_spend_pool_episode_row import CustomerSpendPoolEpisodeRow
        from ..models.spend_control_family_totals_row import SpendControlFamilyTotalsRow
        from ..models.wallet_policy_episode_row import WalletPolicyEpisodeRow
        d = dict(src_dict)
        rows = []
        _rows = d.pop("rows")
        for rows_item_data in (_rows):
            def _parse_rows_item(data: object) -> CeilingEpisodeRow | CustomerSpendPoolEpisodeRow | WalletPolicyEpisodeRow:
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    rows_item_type_0 = CeilingEpisodeRow.from_dict(data)



                    return rows_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    rows_item_type_1 = CustomerSpendPoolEpisodeRow.from_dict(data)



                    return rows_item_type_1
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                if not isinstance(data, dict):
                    raise TypeError()
                rows_item_type_2 = WalletPolicyEpisodeRow.from_dict(data)



                return rows_item_type_2

            rows_item = _parse_rows_item(rows_item_data)

            rows.append(rows_item)


        since = datetime.datetime.fromisoformat(d.pop("since"))




        totals = []
        _totals = d.pop("totals")
        for totals_item_data in (_totals):
            totals_item = SpendControlFamilyTotalsRow.from_dict(totals_item_data)



            totals.append(totals_item)


        until = datetime.datetime.fromisoformat(d.pop("until"))




        stops_and_breaches_response = cls(
            rows=rows,
            since=since,
            totals=totals,
            until=until,
        )


        stops_and_breaches_response.additional_properties = d
        return stops_and_breaches_response

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
