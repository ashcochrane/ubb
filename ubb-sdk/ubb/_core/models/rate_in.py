from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="RateIn")



@_attrs_define
class RateIn:
    """ A single Rate added under a book. card_type and currency are inherited
    from the book, so they are NOT accepted here (the book owns them).

        Attributes:
            metric_name (str):
            dim1 (str | Unset):  Default: ''.
            dim2 (str | Unset):  Default: ''.
            dim3 (str | Unset):  Default: ''.
            dim4 (str | Unset):  Default: ''.
            dim5 (str | Unset):  Default: ''.
            dim6 (str | Unset):  Default: ''.
            event_type (str | Unset):  Default: ''.
            fixed_micros (int | Unset):  Default: 0.
            pricing_model (str | Unset):  Default: 'per_unit'.
            provider (str | Unset):  Default: ''.
            rate_per_unit_micros (int | Unset):  Default: 0.
            subtask_type (str | Unset):  Default: ''.
            task_type (str | Unset):  Default: ''.
            unit_quantity (int | Unset):  Default: 1000000.
     """

    metric_name: str
    dim1: str | Unset = ''
    dim2: str | Unset = ''
    dim3: str | Unset = ''
    dim4: str | Unset = ''
    dim5: str | Unset = ''
    dim6: str | Unset = ''
    event_type: str | Unset = ''
    fixed_micros: int | Unset = 0
    pricing_model: str | Unset = 'per_unit'
    provider: str | Unset = ''
    rate_per_unit_micros: int | Unset = 0
    subtask_type: str | Unset = ''
    task_type: str | Unset = ''
    unit_quantity: int | Unset = 1000000
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        metric_name = self.metric_name

        dim1 = self.dim1

        dim2 = self.dim2

        dim3 = self.dim3

        dim4 = self.dim4

        dim5 = self.dim5

        dim6 = self.dim6

        event_type = self.event_type

        fixed_micros = self.fixed_micros

        pricing_model = self.pricing_model

        provider = self.provider

        rate_per_unit_micros = self.rate_per_unit_micros

        subtask_type = self.subtask_type

        task_type = self.task_type

        unit_quantity = self.unit_quantity


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "metric_name": metric_name,
        })
        if dim1 is not UNSET:
            field_dict["dim1"] = dim1
        if dim2 is not UNSET:
            field_dict["dim2"] = dim2
        if dim3 is not UNSET:
            field_dict["dim3"] = dim3
        if dim4 is not UNSET:
            field_dict["dim4"] = dim4
        if dim5 is not UNSET:
            field_dict["dim5"] = dim5
        if dim6 is not UNSET:
            field_dict["dim6"] = dim6
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if fixed_micros is not UNSET:
            field_dict["fixed_micros"] = fixed_micros
        if pricing_model is not UNSET:
            field_dict["pricing_model"] = pricing_model
        if provider is not UNSET:
            field_dict["provider"] = provider
        if rate_per_unit_micros is not UNSET:
            field_dict["rate_per_unit_micros"] = rate_per_unit_micros
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
        metric_name = d.pop("metric_name")

        dim1 = d.pop("dim1", UNSET)

        dim2 = d.pop("dim2", UNSET)

        dim3 = d.pop("dim3", UNSET)

        dim4 = d.pop("dim4", UNSET)

        dim5 = d.pop("dim5", UNSET)

        dim6 = d.pop("dim6", UNSET)

        event_type = d.pop("event_type", UNSET)

        fixed_micros = d.pop("fixed_micros", UNSET)

        pricing_model = d.pop("pricing_model", UNSET)

        provider = d.pop("provider", UNSET)

        rate_per_unit_micros = d.pop("rate_per_unit_micros", UNSET)

        subtask_type = d.pop("subtask_type", UNSET)

        task_type = d.pop("task_type", UNSET)

        unit_quantity = d.pop("unit_quantity", UNSET)

        rate_in = cls(
            metric_name=metric_name,
            dim1=dim1,
            dim2=dim2,
            dim3=dim3,
            dim4=dim4,
            dim5=dim5,
            dim6=dim6,
            event_type=event_type,
            fixed_micros=fixed_micros,
            pricing_model=pricing_model,
            provider=provider,
            rate_per_unit_micros=rate_per_unit_micros,
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
