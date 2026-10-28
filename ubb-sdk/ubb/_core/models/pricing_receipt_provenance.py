from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.pricing_receipt_provenance_markup import PricingReceiptProvenanceMarkup





T = TypeVar("T", bound="PricingReceiptProvenance")



@_attrs_define
class PricingReceiptProvenance:
    """ Cross-reference ids and nothing else (`receipts._validate_provenance`
    refuses a figure here). Absent keys stay absent: a usage event names the
    rules it read, a Charge names its agreed price line, and a completion names
    the Resolution Run or the held name that completed it (#363, #568).

        Attributes:
            agreed_price_line_id (None | str | Unset):
            book_version (None | str | Unset):
            cost_rate_ids (list[str] | None | Unset):
            held_name_id (None | str | Unset):
            markup (None | PricingReceiptProvenanceMarkup | Unset):
            price_rate_ids (list[str] | None | Unset):
            resolution_run_id (None | str | Unset):
     """

    agreed_price_line_id: None | str | Unset = UNSET
    book_version: None | str | Unset = UNSET
    cost_rate_ids: list[str] | None | Unset = UNSET
    held_name_id: None | str | Unset = UNSET
    markup: None | PricingReceiptProvenanceMarkup | Unset = UNSET
    price_rate_ids: list[str] | None | Unset = UNSET
    resolution_run_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pricing_receipt_provenance_markup import PricingReceiptProvenanceMarkup
        agreed_price_line_id: None | str | Unset
        if isinstance(self.agreed_price_line_id, Unset):
            agreed_price_line_id = UNSET
        else:
            agreed_price_line_id = self.agreed_price_line_id

        book_version: None | str | Unset
        if isinstance(self.book_version, Unset):
            book_version = UNSET
        else:
            book_version = self.book_version

        cost_rate_ids: list[str] | None | Unset
        if isinstance(self.cost_rate_ids, Unset):
            cost_rate_ids = UNSET
        elif isinstance(self.cost_rate_ids, list):
            cost_rate_ids = self.cost_rate_ids


        else:
            cost_rate_ids = self.cost_rate_ids

        held_name_id: None | str | Unset
        if isinstance(self.held_name_id, Unset):
            held_name_id = UNSET
        else:
            held_name_id = self.held_name_id

        markup: dict[str, Any] | None | Unset
        if isinstance(self.markup, Unset):
            markup = UNSET
        elif isinstance(self.markup, PricingReceiptProvenanceMarkup):
            markup = self.markup.to_dict()
        else:
            markup = self.markup

        price_rate_ids: list[str] | None | Unset
        if isinstance(self.price_rate_ids, Unset):
            price_rate_ids = UNSET
        elif isinstance(self.price_rate_ids, list):
            price_rate_ids = self.price_rate_ids


        else:
            price_rate_ids = self.price_rate_ids

        resolution_run_id: None | str | Unset
        if isinstance(self.resolution_run_id, Unset):
            resolution_run_id = UNSET
        else:
            resolution_run_id = self.resolution_run_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if agreed_price_line_id is not UNSET:
            field_dict["agreed_price_line_id"] = agreed_price_line_id
        if book_version is not UNSET:
            field_dict["book_version"] = book_version
        if cost_rate_ids is not UNSET:
            field_dict["cost_rate_ids"] = cost_rate_ids
        if held_name_id is not UNSET:
            field_dict["held_name_id"] = held_name_id
        if markup is not UNSET:
            field_dict["markup"] = markup
        if price_rate_ids is not UNSET:
            field_dict["price_rate_ids"] = price_rate_ids
        if resolution_run_id is not UNSET:
            field_dict["resolution_run_id"] = resolution_run_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pricing_receipt_provenance_markup import PricingReceiptProvenanceMarkup
        d = dict(src_dict)
        def _parse_agreed_price_line_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        agreed_price_line_id = _parse_agreed_price_line_id(d.pop("agreed_price_line_id", UNSET))


        def _parse_book_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        book_version = _parse_book_version(d.pop("book_version", UNSET))


        def _parse_cost_rate_ids(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                cost_rate_ids_type_0 = cast(list[str], data)

                return cost_rate_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        cost_rate_ids = _parse_cost_rate_ids(d.pop("cost_rate_ids", UNSET))


        def _parse_held_name_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        held_name_id = _parse_held_name_id(d.pop("held_name_id", UNSET))


        def _parse_markup(data: object) -> None | PricingReceiptProvenanceMarkup | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                markup_type_0 = PricingReceiptProvenanceMarkup.from_dict(data)



                return markup_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PricingReceiptProvenanceMarkup | Unset, data)

        markup = _parse_markup(d.pop("markup", UNSET))


        def _parse_price_rate_ids(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                price_rate_ids_type_0 = cast(list[str], data)

                return price_rate_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        price_rate_ids = _parse_price_rate_ids(d.pop("price_rate_ids", UNSET))


        def _parse_resolution_run_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolution_run_id = _parse_resolution_run_id(d.pop("resolution_run_id", UNSET))


        pricing_receipt_provenance = cls(
            agreed_price_line_id=agreed_price_line_id,
            book_version=book_version,
            cost_rate_ids=cost_rate_ids,
            held_name_id=held_name_id,
            markup=markup,
            price_rate_ids=price_rate_ids,
            resolution_run_id=resolution_run_id,
        )


        pricing_receipt_provenance.additional_properties = d
        return pricing_receipt_provenance

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
