from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.book_change_in_pricing_method_type_0 import BookChangeInPricingMethodType0
from ..models.book_change_in_rate_structure_type_0 import BookChangeInRateStructureType0
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.book_change_in_grouping_fields import BookChangeInGroupingFields





T = TypeVar("T", bound="BookChangeIn")



@_attrs_define
class BookChangeIn:
    """ One change in a publish: what to do, and to which rule.

    `kind` is `add`, `reprice` or `retire` — the three surfaces a book used to
    have, arriving as three kinds of one act. It is a plain string and the
    service refuses anything else, which is how the book's own discriminators
    are already handled on this surface: these three name the shape of one
    request body, they are stored on no column and returned in no response, and
    a `Literal` here would publish an enumeration the vocabulary registry does
    not own.

    The rule is identified by the quantity it prices plus its selectors —
    `provider`, `event_type`, `task_type`, `subtask_type` and the tenant's own
    declared grouping fields. An omitted selector means the rule leaves it
    unpinned, which is what an unpinned selector means everywhere on this
    surface, so a change body names only what the rule pins.

    The three terms, the method and the arithmetic shape are nullable because a
    reprice states only what moves: anything unstated is carried over from the
    rule being superseded. An `add` takes the model's own defaults for what it
    leaves out, and a `retire` states none of them at all — it opens no rule.

    `rate_structure` says which arithmetic the rule runs: an amount per unit of
    quantity, or a component that applies once regardless of quantity. It is a
    different fact from `pricing_method`, which says how the price is DERIVED,
    and a change may move either without the other.

        Attributes:
            kind (str):
            measurement_key (str):
            event_type (str | Unset):  Default: ''.
            fixed_micros (int | None | Unset):
            grouping_fields (BookChangeInGroupingFields | Unset):
            pricing_method (BookChangeInPricingMethodType0 | None | Unset):
            provider (str | Unset):  Default: ''.
            rate_per_unit_micros (int | None | Unset):
            rate_structure (BookChangeInRateStructureType0 | None | Unset):
            subtask_type (str | Unset):  Default: ''.
            task_type (str | Unset):  Default: ''.
            unit_quantity (int | None | Unset):
     """

    kind: str
    measurement_key: str
    event_type: str | Unset = ''
    fixed_micros: int | None | Unset = UNSET
    grouping_fields: BookChangeInGroupingFields | Unset = UNSET
    pricing_method: BookChangeInPricingMethodType0 | None | Unset = UNSET
    provider: str | Unset = ''
    rate_per_unit_micros: int | None | Unset = UNSET
    rate_structure: BookChangeInRateStructureType0 | None | Unset = UNSET
    subtask_type: str | Unset = ''
    task_type: str | Unset = ''
    unit_quantity: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.book_change_in_grouping_fields import BookChangeInGroupingFields
        kind = self.kind

        measurement_key = self.measurement_key

        event_type = self.event_type

        fixed_micros: int | None | Unset
        if isinstance(self.fixed_micros, Unset):
            fixed_micros = UNSET
        else:
            fixed_micros = self.fixed_micros

        grouping_fields: dict[str, Any] | Unset = UNSET
        if not isinstance(self.grouping_fields, Unset):
            grouping_fields = self.grouping_fields.to_dict()

        pricing_method: None | str | Unset
        if isinstance(self.pricing_method, Unset):
            pricing_method = UNSET
        elif isinstance(self.pricing_method, BookChangeInPricingMethodType0):
            pricing_method = self.pricing_method.value
        else:
            pricing_method = self.pricing_method

        provider = self.provider

        rate_per_unit_micros: int | None | Unset
        if isinstance(self.rate_per_unit_micros, Unset):
            rate_per_unit_micros = UNSET
        else:
            rate_per_unit_micros = self.rate_per_unit_micros

        rate_structure: None | str | Unset
        if isinstance(self.rate_structure, Unset):
            rate_structure = UNSET
        elif isinstance(self.rate_structure, BookChangeInRateStructureType0):
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
            "kind": kind,
            "measurement_key": measurement_key,
        })
        if event_type is not UNSET:
            field_dict["event_type"] = event_type
        if fixed_micros is not UNSET:
            field_dict["fixed_micros"] = fixed_micros
        if grouping_fields is not UNSET:
            field_dict["grouping_fields"] = grouping_fields
        if pricing_method is not UNSET:
            field_dict["pricing_method"] = pricing_method
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
        from ..models.book_change_in_grouping_fields import BookChangeInGroupingFields
        d = dict(src_dict)
        kind = d.pop("kind")

        measurement_key = d.pop("measurement_key")

        event_type = d.pop("event_type", UNSET)

        def _parse_fixed_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fixed_micros = _parse_fixed_micros(d.pop("fixed_micros", UNSET))


        _grouping_fields = d.pop("grouping_fields", UNSET)
        grouping_fields: BookChangeInGroupingFields | Unset
        if isinstance(_grouping_fields,  Unset):
            grouping_fields = UNSET
        else:
            grouping_fields = BookChangeInGroupingFields.from_dict(_grouping_fields)




        def _parse_pricing_method(data: object) -> BookChangeInPricingMethodType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                pricing_method_type_0 = BookChangeInPricingMethodType0(data)



                return pricing_method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BookChangeInPricingMethodType0 | None | Unset, data)

        pricing_method = _parse_pricing_method(d.pop("pricing_method", UNSET))


        provider = d.pop("provider", UNSET)

        def _parse_rate_per_unit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rate_per_unit_micros = _parse_rate_per_unit_micros(d.pop("rate_per_unit_micros", UNSET))


        def _parse_rate_structure(data: object) -> BookChangeInRateStructureType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                rate_structure_type_0 = BookChangeInRateStructureType0(data)



                return rate_structure_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BookChangeInRateStructureType0 | None | Unset, data)

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


        book_change_in = cls(
            kind=kind,
            measurement_key=measurement_key,
            event_type=event_type,
            fixed_micros=fixed_micros,
            grouping_fields=grouping_fields,
            pricing_method=pricing_method,
            provider=provider,
            rate_per_unit_micros=rate_per_unit_micros,
            rate_structure=rate_structure,
            subtask_type=subtask_type,
            task_type=task_type,
            unit_quantity=unit_quantity,
        )


        book_change_in.additional_properties = d
        return book_change_in

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
