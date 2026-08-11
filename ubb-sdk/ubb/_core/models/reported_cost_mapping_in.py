from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.reported_cost_mapping_in_amount_representation import ReportedCostMappingInAmountRepresentation
from ..models.reported_cost_mapping_in_source_kind import ReportedCostMappingInSourceKind
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ReportedCostMappingIn")



@_attrs_define
class ReportedCostMappingIn:
    """ Where a supplier's own cost figure is read from. One per Event Type.

    A sibling of the declared quantities rather than one of them: money with a
    currency does not fit a shape built for a quantity and its unit.

        Attributes:
            amount_representation (ReportedCostMappingInAmountRepresentation):
            source_kind (ReportedCostMappingInSourceKind):
            currency (str | Unset):  Default: ''.
            currency_path (list[str] | Unset):
            source_path (list[str] | Unset):
     """

    amount_representation: ReportedCostMappingInAmountRepresentation
    source_kind: ReportedCostMappingInSourceKind
    currency: str | Unset = ''
    currency_path: list[str] | Unset = UNSET
    source_path: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        amount_representation = self.amount_representation.value

        source_kind = self.source_kind.value

        currency = self.currency

        currency_path: list[str] | Unset = UNSET
        if not isinstance(self.currency_path, Unset):
            currency_path = self.currency_path



        source_path: list[str] | Unset = UNSET
        if not isinstance(self.source_path, Unset):
            source_path = self.source_path




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "amount_representation": amount_representation,
            "source_kind": source_kind,
        })
        if currency is not UNSET:
            field_dict["currency"] = currency
        if currency_path is not UNSET:
            field_dict["currency_path"] = currency_path
        if source_path is not UNSET:
            field_dict["source_path"] = source_path

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        amount_representation = ReportedCostMappingInAmountRepresentation(d.pop("amount_representation"))




        source_kind = ReportedCostMappingInSourceKind(d.pop("source_kind"))




        currency = d.pop("currency", UNSET)

        currency_path = cast(list[str], d.pop("currency_path", UNSET))


        source_path = cast(list[str], d.pop("source_path", UNSET))


        reported_cost_mapping_in = cls(
            amount_representation=amount_representation,
            source_kind=source_kind,
            currency=currency,
            currency_path=currency_path,
            source_path=source_path,
        )


        reported_cost_mapping_in.additional_properties = d
        return reported_cost_mapping_in

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
