from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.rate_change_in_rate_structure_type_0 import RateChangeInRateStructureType0
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RateChangeIn")



@_attrs_define
class RateChangeIn:
    """ One reprice in a publish. Match keys (measurement_key plus the fourteen
    selectors below — provider/event_type/task_type/subtask_type and the ten
    grouping-field slots) locate the active rate; the remaining (nullable)
    fields, when present, override it in the new version.

    **These are the whole selector set a rate can pin.** A rate is pinned on the
    four reserved axes and on any of the ten grouping slots, and every one of
    them can be stated here — so a rule pinned on any slot is reachable. A
    selector left empty matches a rule that leaves that slot unpinned, which is
    what an empty selector means everywhere on this surface, so omitting one is
    a statement about the rule rather than a gap in the body.

        Attributes:
            measurement_key (str):
            event_type (str | Unset):  Default: ''.
            fixed_micros (int | None | Unset):
            grouping_field_1 (str | Unset):  Default: ''.
            grouping_field_10 (str | Unset):  Default: ''.
            grouping_field_2 (str | Unset):  Default: ''.
            grouping_field_3 (str | Unset):  Default: ''.
            grouping_field_4 (str | Unset):  Default: ''.
            grouping_field_5 (str | Unset):  Default: ''.
            grouping_field_6 (str | Unset):  Default: ''.
            grouping_field_7 (str | Unset):  Default: ''.
            grouping_field_8 (str | Unset):  Default: ''.
            grouping_field_9 (str | Unset):  Default: ''.
            provider (str | Unset):  Default: ''.
            rate_per_unit_micros (int | None | Unset):
            rate_structure (None | RateChangeInRateStructureType0 | Unset):
            subtask_type (str | Unset):  Default: ''.
            task_type (str | Unset):  Default: ''.
            unit_quantity (int | None | Unset):
     """

    measurement_key: str
    event_type: str | Unset = ''
    fixed_micros: int | None | Unset = UNSET
    grouping_field_1: str | Unset = ''
    grouping_field_10: str | Unset = ''
    grouping_field_2: str | Unset = ''
    grouping_field_3: str | Unset = ''
    grouping_field_4: str | Unset = ''
    grouping_field_5: str | Unset = ''
    grouping_field_6: str | Unset = ''
    grouping_field_7: str | Unset = ''
    grouping_field_8: str | Unset = ''
    grouping_field_9: str | Unset = ''
    provider: str | Unset = ''
    rate_per_unit_micros: int | None | Unset = UNSET
    rate_structure: None | RateChangeInRateStructureType0 | Unset = UNSET
    subtask_type: str | Unset = ''
    task_type: str | Unset = ''
    unit_quantity: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        measurement_key = self.measurement_key

        event_type = self.event_type

        fixed_micros: int | None | Unset
        if isinstance(self.fixed_micros, Unset):
            fixed_micros = UNSET
        else:
            fixed_micros = self.fixed_micros

        grouping_field_1 = self.grouping_field_1

        grouping_field_10 = self.grouping_field_10

        grouping_field_2 = self.grouping_field_2

        grouping_field_3 = self.grouping_field_3

        grouping_field_4 = self.grouping_field_4

        grouping_field_5 = self.grouping_field_5

        grouping_field_6 = self.grouping_field_6

        grouping_field_7 = self.grouping_field_7

        grouping_field_8 = self.grouping_field_8

        grouping_field_9 = self.grouping_field_9

        provider = self.provider

        rate_per_unit_micros: int | None | Unset
        if isinstance(self.rate_per_unit_micros, Unset):
            rate_per_unit_micros = UNSET
        else:
            rate_per_unit_micros = self.rate_per_unit_micros

        rate_structure: None | str | Unset
        if isinstance(self.rate_structure, Unset):
            rate_structure = UNSET
        elif isinstance(self.rate_structure, RateChangeInRateStructureType0):
            rate_structure = self.rate_structure.value
        else:
            rate_structure = self.rate_structure

        subtask_type = self.subtask_type

        task_type = self.task_type

        unit_quantity: int | None | Unset
        if isinstance(self.unit_quantity, Unset):
            unit_quantity = UNSET
        else:
            unit_quantity = self.unit_quantity


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "measurement_key": measurement_key,
        })
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if fixed_micros is not UNSET:
            field_dict["fixed_micros"] = fixed_micros
        if grouping_field_1 is not UNSET:
            field_dict["grouping_field_1"] = grouping_field_1
        if grouping_field_10 is not UNSET:
            field_dict["grouping_field_10"] = grouping_field_10
        if grouping_field_2 is not UNSET:
            field_dict["grouping_field_2"] = grouping_field_2
        if grouping_field_3 is not UNSET:
            field_dict["grouping_field_3"] = grouping_field_3
        if grouping_field_4 is not UNSET:
            field_dict["grouping_field_4"] = grouping_field_4
        if grouping_field_5 is not UNSET:
            field_dict["grouping_field_5"] = grouping_field_5
        if grouping_field_6 is not UNSET:
            field_dict["grouping_field_6"] = grouping_field_6
        if grouping_field_7 is not UNSET:
            field_dict["grouping_field_7"] = grouping_field_7
        if grouping_field_8 is not UNSET:
            field_dict["grouping_field_8"] = grouping_field_8
        if grouping_field_9 is not UNSET:
            field_dict["grouping_field_9"] = grouping_field_9
        if provider is not UNSET:
            field_dict["provider"] = provider
        if rate_per_unit_micros is not UNSET:
            field_dict["rate_per_unit_micros"] = rate_per_unit_micros
        if rate_structure is not UNSET:
            field_dict["rate_structure"] = rate_structure
        if subtask_type is not UNSET:
            field_dict["subtask_type"] = subtask_type
        if task_type is not UNSET:
            field_dict["task_type"] = task_type
        if unit_quantity is not UNSET:
            field_dict["unit_quantity"] = unit_quantity

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        measurement_key = d.pop("measurement_key")

        event_type = d.pop("event_type", UNSET)

        def _parse_fixed_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fixed_micros = _parse_fixed_micros(d.pop("fixed_micros", UNSET))


        grouping_field_1 = d.pop("grouping_field_1", UNSET)

        grouping_field_10 = d.pop("grouping_field_10", UNSET)

        grouping_field_2 = d.pop("grouping_field_2", UNSET)

        grouping_field_3 = d.pop("grouping_field_3", UNSET)

        grouping_field_4 = d.pop("grouping_field_4", UNSET)

        grouping_field_5 = d.pop("grouping_field_5", UNSET)

        grouping_field_6 = d.pop("grouping_field_6", UNSET)

        grouping_field_7 = d.pop("grouping_field_7", UNSET)

        grouping_field_8 = d.pop("grouping_field_8", UNSET)

        grouping_field_9 = d.pop("grouping_field_9", UNSET)

        provider = d.pop("provider", UNSET)

        def _parse_rate_per_unit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rate_per_unit_micros = _parse_rate_per_unit_micros(d.pop("rate_per_unit_micros", UNSET))


        def _parse_rate_structure(data: object) -> None | RateChangeInRateStructureType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                rate_structure_type_0 = RateChangeInRateStructureType0(data)



                return rate_structure_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RateChangeInRateStructureType0 | Unset, data)

        rate_structure = _parse_rate_structure(d.pop("rate_structure", UNSET))


        subtask_type = d.pop("subtask_type", UNSET)

        task_type = d.pop("task_type", UNSET)

        def _parse_unit_quantity(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        unit_quantity = _parse_unit_quantity(d.pop("unit_quantity", UNSET))


        rate_change_in = cls(
            measurement_key=measurement_key,
            event_type=event_type,
            fixed_micros=fixed_micros,
            grouping_field_1=grouping_field_1,
            grouping_field_10=grouping_field_10,
            grouping_field_2=grouping_field_2,
            grouping_field_3=grouping_field_3,
            grouping_field_4=grouping_field_4,
            grouping_field_5=grouping_field_5,
            grouping_field_6=grouping_field_6,
            grouping_field_7=grouping_field_7,
            grouping_field_8=grouping_field_8,
            grouping_field_9=grouping_field_9,
            provider=provider,
            rate_per_unit_micros=rate_per_unit_micros,
            rate_structure=rate_structure,
            subtask_type=subtask_type,
            task_type=task_type,
            unit_quantity=unit_quantity,
        )


        rate_change_in.additional_properties = d
        return rate_change_in

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
