from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.economic_measure_out_measure import EconomicMeasureOutMeasure
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="EconomicMeasureOut")



@_attrs_define
class EconomicMeasureOut:
    """ One requested measure on one row: its amount, and what that amount is
    worth.

    ⚠ **THE STATE IS NOT DECORATION AND THE FIGURE IS NOT THE ANSWER ON ITS
    OWN.** A measure whose inputs are still resolving carries a bound and says
    so here; a measure that could not be attributed at the requested grain
    carries whatever part of itself could be placed — or, for a margin, nothing
    at all — and says so here. A reader that took the figure and dropped this
    field would publish a floor as a total, which is the defect the whole
    surface exists to end.

        Attributes:
            measure (EconomicMeasureOutMeasure):
            status (str): What this measure's figure is worth: 'known' where every input resolved; 'incomplete' where some
                input is still unresolved, so the figure is a bound rather than a total and the count beside it says how far off
                it can be; and 'unavailable_at_requested_grain' where a figure exists that cannot be attributed this finely.
                Under that last one a revenue figure is the part that COULD be placed and the rest is listed in 'context', while
                a margin is null outright — there is no such thing as a partial margin. ⚠ None of the three is ever a stand-in
                for a figure: a zero here is a measured zero, and where UBB has no figure at all the field is null.
            amount_micros (int | None | Unset):
            event_count (int | None | Unset):
            unpriced_event_count (int | None | Unset):
            unresolved_event_count (int | None | Unset):
     """

    measure: EconomicMeasureOutMeasure
    status: str
    amount_micros: int | None | Unset = UNSET
    event_count: int | None | Unset = UNSET
    unpriced_event_count: int | None | Unset = UNSET
    unresolved_event_count: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        measure = self.measure.value

        status = self.status

        amount_micros: int | None | Unset
        if isinstance(self.amount_micros, Unset):
            amount_micros = UNSET
        else:
            amount_micros = self.amount_micros

        event_count: int | None | Unset
        if isinstance(self.event_count, Unset):
            event_count = UNSET
        else:
            event_count = self.event_count

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
            "measure": measure,
            "status": status,
        })
        if amount_micros is not UNSET:
            field_dict["amount_micros"] = amount_micros
        if event_count is not UNSET:
            field_dict["event_count"] = event_count
        if unpriced_event_count is not UNSET:
            field_dict["unpriced_event_count"] = unpriced_event_count
        if unresolved_event_count is not UNSET:
            field_dict["unresolved_event_count"] = unresolved_event_count

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        measure = EconomicMeasureOutMeasure(d.pop("measure"))




        status = d.pop("status")

        def _parse_amount_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        amount_micros = _parse_amount_micros(d.pop("amount_micros", UNSET))


        def _parse_event_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        event_count = _parse_event_count(d.pop("event_count", UNSET))


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
            measure=measure,
            status=status,
            amount_micros=amount_micros,
            event_count=event_count,
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
