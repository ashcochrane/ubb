from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.ceiling_utilisation_row import CeilingUtilisationRow
  from ..models.customer_spend_pool_status_out import CustomerSpendPoolStatusOut





T = TypeVar("T", bound="UtilisationAndHeadroomResponse")



@_attrs_define
class UtilisationAndHeadroomResponse:
    """ How much of each ceiling was used, and how often it could not be
    evaluated (#150 §9.3). The average utilisation is computed per unit and
    then across every unit that had a ceiling, so one chatty unit never
    dominates; peak utilisation equals the final figure by construction (the
    pinned ceiling never moves and the known total never falls) and is not
    published twice. Shares are whole percentages of `unit_count`, rounded
    down; every average is null where no unit contributes — never zero. An
    `indeterminate` unit contributes its own floor, so the average
    utilisation is itself a floor and the average headroom a ceiling
    wherever `indeterminate_count` is not zero — the same reading rule each
    row's status states for its own figures, and the count beside the
    average is what says so. `customer_spend_pool` is the status pair for
    the customer the filter names, null tenant-wide or where no pool
    applies.

        Attributes:
            ceiling_reached_count (int):
            evaluated_count (int):
            indeterminate_count (int):
            not_applicable_count (int):
            rows (list[CeilingUtilisationRow]):
            since (datetime.datetime):
            unit_count (int):
            until (datetime.datetime):
            within_ceiling_count (int):
            average_final_utilisation_percentage (int | None | Unset):
            average_unused_headroom_micros (int | None | Unset):
            ceiling_reached_share_percentage (int | None | Unset):
            customer_spend_pool (CustomerSpendPoolStatusOut | None | Unset):
            indeterminate_share_percentage (int | None | Unset):
     """

    ceiling_reached_count: int
    evaluated_count: int
    indeterminate_count: int
    not_applicable_count: int
    rows: list[CeilingUtilisationRow]
    since: datetime.datetime
    unit_count: int
    until: datetime.datetime
    within_ceiling_count: int
    average_final_utilisation_percentage: int | None | Unset = UNSET
    average_unused_headroom_micros: int | None | Unset = UNSET
    ceiling_reached_share_percentage: int | None | Unset = UNSET
    customer_spend_pool: CustomerSpendPoolStatusOut | None | Unset = UNSET
    indeterminate_share_percentage: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.ceiling_utilisation_row import CeilingUtilisationRow
        from ..models.customer_spend_pool_status_out import CustomerSpendPoolStatusOut
        ceiling_reached_count = self.ceiling_reached_count

        evaluated_count = self.evaluated_count

        indeterminate_count = self.indeterminate_count

        not_applicable_count = self.not_applicable_count

        rows = []
        for rows_item_data in self.rows:
            rows_item = rows_item_data.to_dict()
            rows.append(rows_item)



        since = self.since.isoformat()

        unit_count = self.unit_count

        until = self.until.isoformat()

        within_ceiling_count = self.within_ceiling_count

        average_final_utilisation_percentage: int | None | Unset
        if isinstance(self.average_final_utilisation_percentage, Unset):
            average_final_utilisation_percentage = UNSET
        else:
            average_final_utilisation_percentage = self.average_final_utilisation_percentage

        average_unused_headroom_micros: int | None | Unset
        if isinstance(self.average_unused_headroom_micros, Unset):
            average_unused_headroom_micros = UNSET
        else:
            average_unused_headroom_micros = self.average_unused_headroom_micros

        ceiling_reached_share_percentage: int | None | Unset
        if isinstance(self.ceiling_reached_share_percentage, Unset):
            ceiling_reached_share_percentage = UNSET
        else:
            ceiling_reached_share_percentage = self.ceiling_reached_share_percentage

        customer_spend_pool: dict[str, Any] | None | Unset
        if isinstance(self.customer_spend_pool, Unset):
            customer_spend_pool = UNSET
        elif isinstance(self.customer_spend_pool, CustomerSpendPoolStatusOut):
            customer_spend_pool = self.customer_spend_pool.to_dict()
        else:
            customer_spend_pool = self.customer_spend_pool

        indeterminate_share_percentage: int | None | Unset
        if isinstance(self.indeterminate_share_percentage, Unset):
            indeterminate_share_percentage = UNSET
        else:
            indeterminate_share_percentage = self.indeterminate_share_percentage


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "ceiling_reached_count": ceiling_reached_count,
            "evaluated_count": evaluated_count,
            "indeterminate_count": indeterminate_count,
            "not_applicable_count": not_applicable_count,
            "rows": rows,
            "since": since,
            "unit_count": unit_count,
            "until": until,
            "within_ceiling_count": within_ceiling_count,
        })
        if average_final_utilisation_percentage is not UNSET:
            field_dict["average_final_utilisation_percentage"] = average_final_utilisation_percentage
        if average_unused_headroom_micros is not UNSET:
            field_dict["average_unused_headroom_micros"] = average_unused_headroom_micros
        if ceiling_reached_share_percentage is not UNSET:
            field_dict["ceiling_reached_share_percentage"] = ceiling_reached_share_percentage
        if customer_spend_pool is not UNSET:
            field_dict["customer_spend_pool"] = customer_spend_pool
        if indeterminate_share_percentage is not UNSET:
            field_dict["indeterminate_share_percentage"] = indeterminate_share_percentage

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ceiling_utilisation_row import CeilingUtilisationRow
        from ..models.customer_spend_pool_status_out import CustomerSpendPoolStatusOut
        d = dict(src_dict)
        ceiling_reached_count = d.pop("ceiling_reached_count")

        evaluated_count = d.pop("evaluated_count")

        indeterminate_count = d.pop("indeterminate_count")

        not_applicable_count = d.pop("not_applicable_count")

        rows = []
        _rows = d.pop("rows")
        for rows_item_data in (_rows):
            rows_item = CeilingUtilisationRow.from_dict(rows_item_data)



            rows.append(rows_item)


        since = datetime.datetime.fromisoformat(d.pop("since"))




        unit_count = d.pop("unit_count")

        until = datetime.datetime.fromisoformat(d.pop("until"))




        within_ceiling_count = d.pop("within_ceiling_count")

        def _parse_average_final_utilisation_percentage(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        average_final_utilisation_percentage = _parse_average_final_utilisation_percentage(d.pop("average_final_utilisation_percentage", UNSET))


        def _parse_average_unused_headroom_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        average_unused_headroom_micros = _parse_average_unused_headroom_micros(d.pop("average_unused_headroom_micros", UNSET))


        def _parse_ceiling_reached_share_percentage(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ceiling_reached_share_percentage = _parse_ceiling_reached_share_percentage(d.pop("ceiling_reached_share_percentage", UNSET))


        def _parse_customer_spend_pool(data: object) -> CustomerSpendPoolStatusOut | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                customer_spend_pool_type_0 = CustomerSpendPoolStatusOut.from_dict(data)



                return customer_spend_pool_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CustomerSpendPoolStatusOut | None | Unset, data)

        customer_spend_pool = _parse_customer_spend_pool(d.pop("customer_spend_pool", UNSET))


        def _parse_indeterminate_share_percentage(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        indeterminate_share_percentage = _parse_indeterminate_share_percentage(d.pop("indeterminate_share_percentage", UNSET))


        utilisation_and_headroom_response = cls(
            ceiling_reached_count=ceiling_reached_count,
            evaluated_count=evaluated_count,
            indeterminate_count=indeterminate_count,
            not_applicable_count=not_applicable_count,
            rows=rows,
            since=since,
            unit_count=unit_count,
            until=until,
            within_ceiling_count=within_ceiling_count,
            average_final_utilisation_percentage=average_final_utilisation_percentage,
            average_unused_headroom_micros=average_unused_headroom_micros,
            ceiling_reached_share_percentage=ceiling_reached_share_percentage,
            customer_spend_pool=customer_spend_pool,
            indeterminate_share_percentage=indeterminate_share_percentage,
        )


        utilisation_and_headroom_response.additional_properties = d
        return utilisation_and_headroom_response

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
