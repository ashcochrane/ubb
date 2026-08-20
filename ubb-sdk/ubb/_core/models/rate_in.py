from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.rate_in_rate_structure import RateInRateStructure
from ..types import UNSET, Unset






T = TypeVar("T", bound="RateIn")



@_attrs_define
class RateIn:
    """ A single Rate added under a book. card_type and currency are inherited
    from the book, so they are NOT accepted here (the book owns them).

    The rule is pinned by the quantity it prices plus its selectors: the four
    reserved axes and **all ten** grouping slots. An omitted selector means the
    rule leaves it unpinned, which is what an empty selector means everywhere on
    this surface.

        Attributes:
            measurement_key (str):
            event_type (str | Unset):  Default: ''.
            fixed_micros (int | Unset):  Default: 0.
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
            rate_per_unit_micros (int | Unset):  Default: 0.
            rate_structure (RateInRateStructure | Unset):  Default: RateInRateStructure.PER_UNIT.
            subtask_type (str | Unset):  Default: ''.
            task_type (str | Unset):  Default: ''.
            unit_quantity (int | Unset):  Default: 1000000.
     """

    measurement_key: str
    event_type: str | Unset = ''
    fixed_micros: int | Unset = 0
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
    rate_per_unit_micros: int | Unset = 0
    rate_structure: RateInRateStructure | Unset = RateInRateStructure.PER_UNIT
    subtask_type: str | Unset = ''
    task_type: str | Unset = ''
    unit_quantity: int | Unset = 1000000
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        measurement_key = self.measurement_key

        event_type = self.event_type

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

        rate_per_unit_micros = self.rate_per_unit_micros

        rate_structure: str | Unset = UNSET
        if not isinstance(self.rate_structure, Unset):
            rate_structure = self.rate_structure.value


        subtask_type = self.subtask_type

        task_type = self.task_type

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

        fixed_micros = d.pop("fixed_micros", UNSET)

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

        rate_per_unit_micros = d.pop("rate_per_unit_micros", UNSET)

        _rate_structure = d.pop("rate_structure", UNSET)
        rate_structure: RateInRateStructure | Unset
        if isinstance(_rate_structure,  Unset):
            rate_structure = UNSET
        else:
            rate_structure = RateInRateStructure(_rate_structure)




        subtask_type = d.pop("subtask_type", UNSET)

        task_type = d.pop("task_type", UNSET)

        unit_quantity = d.pop("unit_quantity", UNSET)

        rate_in = cls(
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


        rate_in.additional_properties = d
        return rate_in

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
