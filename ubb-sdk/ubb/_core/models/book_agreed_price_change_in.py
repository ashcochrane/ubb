from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from typing import Literal, cast






T = TypeVar("T", bound="BookAgreedPriceChangeIn")



@_attrs_define
class BookAgreedPriceChangeIn:
    """ One change to an agreed price in a publish: what one delivered unit of
    a declared kind of work sells for.

    `line` is `agreed_price`. `kind` is `add`, `reprice` or `retire`, the
    same three acts a rate takes, and `task_type` names the kind of work —
    a top-level kind you have declared and not retired, whatever its current
    `pricing_mode`, so the price can be declared before the kind is switched
    to fixed pricing and no start is refused in between. A kind declared only
    as contained work is refused: one agreed price buys a whole unit of work.

    A book holds at most one agreed price in force for one kind of work.
    `agreed_price_micros` is in USD micros and is required on `add` and
    `reprice` and refused on `retire`. Zero is a price; a negative amount is
    refused. The change takes effect at the publish's `effective_at`, like a
    rate change in the same publish.

        Attributes:
            kind (str):
            line (Literal['agreed_price']):
            task_type (str):
            agreed_price_micros (int | None | Unset):
     """

    kind: str
    line: Literal['agreed_price']
    task_type: str
    agreed_price_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        line = self.line

        task_type = self.task_type

        agreed_price_micros: int | None | Unset
        if isinstance(self.agreed_price_micros, Unset):
            agreed_price_micros = UNSET
        else:
            agreed_price_micros = self.agreed_price_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "kind": kind,
            "line": line,
            "task_type": task_type,
        })
        if agreed_price_micros is not UNSET:
            field_dict["agreed_price_micros"] = agreed_price_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = d.pop("kind")

        line = cast(Literal['agreed_price'] , d.pop("line"))
        if line != 'agreed_price':
            raise ValueError(f"line must match const 'agreed_price', got '{line}'")

        task_type = d.pop("task_type")

        def _parse_agreed_price_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        agreed_price_micros = _parse_agreed_price_micros(d.pop("agreed_price_micros", UNSET))


        book_agreed_price_change_in = cls(
            kind=kind,
            line=line,
            task_type=task_type,
            agreed_price_micros=agreed_price_micros,
        )


        book_agreed_price_change_in.additional_properties = d
        return book_agreed_price_change_in

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
