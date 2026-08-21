from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.rate_out_rate_structure import RateOutRateStructure
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RateOut")



@_attrs_define
class RateOut:
    """ 
        Attributes:
            book_id (None | str):
            currency (str):
            event_type (str):
            fixed_micros (int):
            grouping_field_1 (str):
            grouping_field_10 (str):
            grouping_field_2 (str):
            grouping_field_3 (str):
            grouping_field_4 (str):
            grouping_field_5 (str):
            grouping_field_6 (str):
            grouping_field_7 (str):
            grouping_field_8 (str):
            grouping_field_9 (str):
            id (str):
            lineage_id (str):
            measurement_key (str):
            provider (str):
            rate_per_unit_micros (int):
            rate_structure (RateOutRateStructure):
            subtask_type (str):
            task_type (str):
            unit_quantity (int):
            valid_from (str):
            valid_to (None | str | Unset):
     """

    book_id: None | str
    currency: str
    event_type: str
    fixed_micros: int
    grouping_field_1: str
    grouping_field_10: str
    grouping_field_2: str
    grouping_field_3: str
    grouping_field_4: str
    grouping_field_5: str
    grouping_field_6: str
    grouping_field_7: str
    grouping_field_8: str
    grouping_field_9: str
    id: str
    lineage_id: str
    measurement_key: str
    provider: str
    rate_per_unit_micros: int
    rate_structure: RateOutRateStructure
    subtask_type: str
    task_type: str
    unit_quantity: int
    valid_from: str
    valid_to: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        book_id: None | str
        book_id = self.book_id

        currency = self.currency

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

        id = self.id

        lineage_id = self.lineage_id

        measurement_key = self.measurement_key

        provider = self.provider

        rate_per_unit_micros = self.rate_per_unit_micros

        rate_structure = self.rate_structure.value

        subtask_type = self.subtask_type

        task_type = self.task_type

        unit_quantity = self.unit_quantity

        valid_from = self.valid_from

        valid_to: None | str | Unset
        if isinstance(self.valid_to, Unset):
            valid_to = UNSET
        else:
            valid_to = self.valid_to


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "book_id": book_id,
            "currency": currency,
            "event_type": event_type,
            "fixed_micros": fixed_micros,
            "grouping_field_1": grouping_field_1,
            "grouping_field_10": grouping_field_10,
            "grouping_field_2": grouping_field_2,
            "grouping_field_3": grouping_field_3,
            "grouping_field_4": grouping_field_4,
            "grouping_field_5": grouping_field_5,
            "grouping_field_6": grouping_field_6,
            "grouping_field_7": grouping_field_7,
            "grouping_field_8": grouping_field_8,
            "grouping_field_9": grouping_field_9,
            "id": id,
            "lineage_id": lineage_id,
            "measurement_key": measurement_key,
            "provider": provider,
            "rate_per_unit_micros": rate_per_unit_micros,
            "rate_structure": rate_structure,
            "subtask_type": subtask_type,
            "task_type": task_type,
            "unit_quantity": unit_quantity,
            "valid_from": valid_from,
        })
        if valid_to is not UNSET:
            field_dict["valid_to"] = valid_to

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_book_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        book_id = _parse_book_id(d.pop("book_id"))


        currency = d.pop("currency")

        event_type = d.pop("event_type")

        fixed_micros = d.pop("fixed_micros")

        grouping_field_1 = d.pop("grouping_field_1")

        grouping_field_10 = d.pop("grouping_field_10")

        grouping_field_2 = d.pop("grouping_field_2")

        grouping_field_3 = d.pop("grouping_field_3")

        grouping_field_4 = d.pop("grouping_field_4")

        grouping_field_5 = d.pop("grouping_field_5")

        grouping_field_6 = d.pop("grouping_field_6")

        grouping_field_7 = d.pop("grouping_field_7")

        grouping_field_8 = d.pop("grouping_field_8")

        grouping_field_9 = d.pop("grouping_field_9")

        id = d.pop("id")

        lineage_id = d.pop("lineage_id")

        measurement_key = d.pop("measurement_key")

        provider = d.pop("provider")

        rate_per_unit_micros = d.pop("rate_per_unit_micros")

        rate_structure = RateOutRateStructure(d.pop("rate_structure"))




        subtask_type = d.pop("subtask_type")

        task_type = d.pop("task_type")

        unit_quantity = d.pop("unit_quantity")

        valid_from = d.pop("valid_from")

        def _parse_valid_to(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        valid_to = _parse_valid_to(d.pop("valid_to", UNSET))


        rate_out = cls(
            book_id=book_id,
            currency=currency,
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
            id=id,
            lineage_id=lineage_id,
            measurement_key=measurement_key,
            provider=provider,
            rate_per_unit_micros=rate_per_unit_micros,
            rate_structure=rate_structure,
            subtask_type=subtask_type,
            task_type=task_type,
            unit_quantity=unit_quantity,
            valid_from=valid_from,
            valid_to=valid_to,
        )


        rate_out.additional_properties = d
        return rate_out

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
