from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.reported_cost_mapping_out_amount_representation import ReportedCostMappingOutAmountRepresentation
from ..models.reported_cost_mapping_out_source_kind import ReportedCostMappingOutSourceKind
from typing import cast






T = TypeVar("T", bound="ReportedCostMappingOut")



@_attrs_define
class ReportedCostMappingOut:
    """ 
        Attributes:
            advisories (list[str]):
            amount_representation (ReportedCostMappingOutAmountRepresentation):
            currency (str):
            currency_path (list[str]):
            required_runtime_parameters (list[str]):
            source_kind (ReportedCostMappingOutSourceKind):
            source_path (list[str]):
     """

    advisories: list[str]
    amount_representation: ReportedCostMappingOutAmountRepresentation
    currency: str
    currency_path: list[str]
    required_runtime_parameters: list[str]
    source_kind: ReportedCostMappingOutSourceKind
    source_path: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        advisories = self.advisories



        amount_representation = self.amount_representation.value

        currency = self.currency

        currency_path = self.currency_path



        required_runtime_parameters = self.required_runtime_parameters



        source_kind = self.source_kind.value

        source_path = self.source_path




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "advisories": advisories,
            "amount_representation": amount_representation,
            "currency": currency,
            "currency_path": currency_path,
            "required_runtime_parameters": required_runtime_parameters,
            "source_kind": source_kind,
            "source_path": source_path,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        advisories = cast(list[str], d.pop("advisories"))


        amount_representation = ReportedCostMappingOutAmountRepresentation(d.pop("amount_representation"))




        currency = d.pop("currency")

        currency_path = cast(list[str], d.pop("currency_path"))


        required_runtime_parameters = cast(list[str], d.pop("required_runtime_parameters"))


        source_kind = ReportedCostMappingOutSourceKind(d.pop("source_kind"))




        source_path = cast(list[str], d.pop("source_path"))


        reported_cost_mapping_out = cls(
            advisories=advisories,
            amount_representation=amount_representation,
            currency=currency,
            currency_path=currency_path,
            required_runtime_parameters=required_runtime_parameters,
            source_kind=source_kind,
            source_path=source_path,
        )


        reported_cost_mapping_out.additional_properties = d
        return reported_cost_mapping_out

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
