from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.economic_measure_out_measure import EconomicMeasureOutMeasure
from ..models.economic_measure_out_status import EconomicMeasureOutStatus
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="EconomicMeasureOut")



@_attrs_define
class EconomicMeasureOut:
    """ One requested measure on one row: its amount, and what that amount is
    worth.

    ⚠ **THE STATE IS NOT DECORATION AND THE FIGURE IS NOT THE ANSWER ON ITS
    OWN.** A measure whose inputs are still resolving carries a bound and says
    so in `status`; a measure that could not be attributed at the requested
    grain carries whatever part of itself could be placed — or, for a margin,
    nothing at all — and says so there too. A reader that took the figure and
    dropped that field would publish a partial sum as a total, which is the
    defect the whole surface exists to end.

    **What each state says about the fields beside it**, which is what the state
    is for:

    * `known` — every input resolved. Inside a period a tenant-supplied revenue
      figure covers, that figure is the revenue and resolves it whole.
    * `incomplete` — some input is still unresolved, so the figure is the sum
      of what resolved rather than a total, and the count beside it says how
      many amounts it leaves out; no direction is promised for them (#603).
      Where no piece of a row's revenue resolved at all there is nothing to
      bound, and the revenue and the margin over it carry no figure.
    * `unavailable_at_requested_grain` — a figure exists and cannot be
      attributed this finely. A REVENUE figure here is the part that COULD be
      placed, with the rest in the answer's `context`; a MARGIN is null
      outright, because there is no such thing as a partial margin.
    * `unavailable_outside_retention_horizon` — the stretch this row covers
      reaches back past the horizon UBB publishes for the records the figure
      would be read from, so there is no figure and no count: `available_from`
      says the day this measure's series can start. The two unavailable states
      are separate because their remedies are: ask a coarser question, against
      that data is gone.
    * `not_applicable` — the measure does not apply. This surface refuses such a
      combination against `/metering/analytics/grouping-options` before building
      a row, so an answer from THIS query never carries it; the value is the
      concept's and a later surface may.

    ⚠ **NO STATE IS EVER A STAND-IN FOR A FIGURE.** A zero here is a measured
    zero, and where UBB has no figure at all the field is null.

        Attributes:
            count (int | None): The count measure's figure: under `recorded_events`, how many metered usage events this row
                covers, never a Task Charge. Present on every measure; null on the three measures denominated in money, and
                wherever no figure can be stated — never a zero standing in.
            measure (EconomicMeasureOutMeasure):
            status (EconomicMeasureOutStatus):
            amount_micros (int | None | Unset): The figure of a money measure, in micros; null on the count measure, which
                is not money. Where it is null on a money measure, no figure can be stated: under
                'unavailable_outside_retention_horizon', under 'not_applicable', on a margin under
                'unavailable_at_requested_grain', and under 'incomplete' where no piece of the row's revenue resolved — on the
                revenue and on the margin over it. An amount under 'incomplete' is the sum of what resolved, never the whole:
                what it leaves out may move it either way; under 'unavailable_at_requested_grain' a revenue amount is the part
                that could be placed, with the rest in the answer's context. A revenue figure the tenant supplied is the revenue
                for the customer and period it covers and supersedes the revenue derived from priced usage there — the two are
                never added together. Never a zero standing in for any of these.
            available_from (None | str | Unset):
            unpriced_event_count (int | None | Unset): How many of this row's postings carry a customer price UBB could not
                resolve, on the revenue measure only. Outside any period a tenant-supplied revenue figure covers, they are what
                makes the revenue 'incomplete'. Inside one they are counted here as information and make nothing incomplete —
                the supplied figure is the revenue there — so this count can stand beside a 'known' revenue.
            unresolved_event_count (int | None | Unset):
     """

    count: int | None
    measure: EconomicMeasureOutMeasure
    status: EconomicMeasureOutStatus
    amount_micros: int | None | Unset = UNSET
    available_from: None | str | Unset = UNSET
    unpriced_event_count: int | None | Unset = UNSET
    unresolved_event_count: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        count: int | None
        count = self.count

        measure = self.measure.value

        status = self.status.value

        amount_micros: int | None | Unset
        if isinstance(self.amount_micros, Unset):
            amount_micros = UNSET
        else:
            amount_micros = self.amount_micros

        available_from: None | str | Unset
        if isinstance(self.available_from, Unset):
            available_from = UNSET
        else:
            available_from = self.available_from

        unpriced_event_count: int | None | Unset
        if isinstance(self.unpriced_event_count, Unset):
            unpriced_event_count = UNSET
        else:
            unpriced_event_count = self.unpriced_event_count

        unresolved_event_count: int | None | Unset
        if isinstance(self.unresolved_event_count, Unset):
            unresolved_event_count = UNSET
        else:
            unresolved_event_count = self.unresolved_event_count


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "count": count,
            "measure": measure,
            "status": status,
        })
        if amount_micros is not UNSET:
            field_dict["amount_micros"] = amount_micros
        if available_from is not UNSET:
            field_dict["available_from"] = available_from
        if unpriced_event_count is not UNSET:
            field_dict["unpriced_event_count"] = unpriced_event_count
        if unresolved_event_count is not UNSET:
            field_dict["unresolved_event_count"] = unresolved_event_count

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_count(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        count = _parse_count(d.pop("count"))


        measure = EconomicMeasureOutMeasure(d.pop("measure"))




        status = EconomicMeasureOutStatus(d.pop("status"))




        def _parse_amount_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        amount_micros = _parse_amount_micros(d.pop("amount_micros", UNSET))


        def _parse_available_from(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        available_from = _parse_available_from(d.pop("available_from", UNSET))


        def _parse_unpriced_event_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        unpriced_event_count = _parse_unpriced_event_count(d.pop("unpriced_event_count", UNSET))


        def _parse_unresolved_event_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        unresolved_event_count = _parse_unresolved_event_count(d.pop("unresolved_event_count", UNSET))


        economic_measure_out = cls(
            count=count,
            measure=measure,
            status=status,
            amount_micros=amount_micros,
            available_from=available_from,
            unpriced_event_count=unpriced_event_count,
            unresolved_event_count=unresolved_event_count,
        )


        economic_measure_out.additional_properties = d
        return economic_measure_out

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
