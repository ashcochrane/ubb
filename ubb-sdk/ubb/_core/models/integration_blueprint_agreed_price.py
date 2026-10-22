from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="IntegrationBlueprintAgreedPrice")



@_attrs_define
class IntegrationBlueprintAgreedPrice:
    """ What one delivered unit of the selected kind of work sells for where a
    customer has no price of their own or from their Plan: the agreed price
    your default Pricing Book holds, and where it came from.

    `pricing_book_key` is that book, `book_version_from` the version its
    publish made it, and the line is in force from `valid_from` until
    `valid_to` (null while open). Shown, never sent: no call carries it, so
    no generated file holds it.

        Attributes:
            agreed_price_micros (int):
            book_version_from (int):
            pricing_book_key (str):
            task_type (str):
            valid_from (str):
            valid_to (None | str):
     """

    agreed_price_micros: int
    book_version_from: int
    pricing_book_key: str
    task_type: str
    valid_from: str
    valid_to: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        agreed_price_micros = self.agreed_price_micros

        book_version_from = self.book_version_from

        pricing_book_key = self.pricing_book_key

        task_type = self.task_type

        valid_from = self.valid_from

        valid_to: None | str
        valid_to = self.valid_to


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "agreed_price_micros": agreed_price_micros,
            "book_version_from": book_version_from,
            "pricing_book_key": pricing_book_key,
            "task_type": task_type,
            "valid_from": valid_from,
            "valid_to": valid_to,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        agreed_price_micros = d.pop("agreed_price_micros")

        book_version_from = d.pop("book_version_from")

        pricing_book_key = d.pop("pricing_book_key")

        task_type = d.pop("task_type")

        valid_from = d.pop("valid_from")

        def _parse_valid_to(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        valid_to = _parse_valid_to(d.pop("valid_to"))


        integration_blueprint_agreed_price = cls(
            agreed_price_micros=agreed_price_micros,
            book_version_from=book_version_from,
            pricing_book_key=pricing_book_key,
            task_type=task_type,
            valid_from=valid_from,
            valid_to=valid_to,
        )


        integration_blueprint_agreed_price.additional_properties = d
        return integration_blueprint_agreed_price

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
