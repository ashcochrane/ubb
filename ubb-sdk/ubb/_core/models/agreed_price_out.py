from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="AgreedPriceOut")



@_attrs_define
class AgreedPriceOut:
    """ One agreed price in a Pricing Book: what one delivered unit of a
    declared kind of work sells for, in USD micros, from `valid_from` until
    `valid_to`.

    The window is half-open — in force at `valid_from`, gone at `valid_to` —
    and `valid_to` is null while the line is open. A reprice closes a line and
    opens its successor at one instant, and the successor carries the same
    `lineage_id`, so a lineage is the history of one kind of work's price in
    one book.

        Attributes:
            agreed_price_micros (int):
            book_id (str):
            id (str):
            lineage_id (str):
            task_type (str):
            valid_from (str):
            valid_to (None | str):
     """

    agreed_price_micros: int
    book_id: str
    id: str
    lineage_id: str
    task_type: str
    valid_from: str
    valid_to: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        agreed_price_micros = self.agreed_price_micros

        book_id = self.book_id

        id = self.id

        lineage_id = self.lineage_id

        task_type = self.task_type

        valid_from = self.valid_from

        valid_to: None | str
        valid_to = self.valid_to


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "agreed_price_micros": agreed_price_micros,
            "book_id": book_id,
            "id": id,
            "lineage_id": lineage_id,
            "task_type": task_type,
            "valid_from": valid_from,
            "valid_to": valid_to,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        agreed_price_micros = d.pop("agreed_price_micros")

        book_id = d.pop("book_id")

        id = d.pop("id")

        lineage_id = d.pop("lineage_id")

        task_type = d.pop("task_type")

        valid_from = d.pop("valid_from")

        def _parse_valid_to(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        valid_to = _parse_valid_to(d.pop("valid_to"))


        agreed_price_out = cls(
            agreed_price_micros=agreed_price_micros,
            book_id=book_id,
            id=id,
            lineage_id=lineage_id,
            task_type=task_type,
            valid_from=valid_from,
            valid_to=valid_to,
        )


        agreed_price_out.additional_properties = d
        return agreed_price_out

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
