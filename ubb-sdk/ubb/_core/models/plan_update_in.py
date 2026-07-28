from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="PlanUpdateIn")



@_attrs_define
class PlanUpdateIn:
    """ 
        Attributes:
            access_fee_micros (int | None | Unset):
            fixed_uplift_micros (int | None | Unset):
            markup_percentage_micros (int | None | Unset):
            migrate_existing (bool | Unset):  Default: False.
            name (None | str | Unset):
            per_seat_micros (int | None | Unset):
     """

    access_fee_micros: int | None | Unset = UNSET
    fixed_uplift_micros: int | None | Unset = UNSET
    markup_percentage_micros: int | None | Unset = UNSET
    migrate_existing: bool | Unset = False
    name: None | str | Unset = UNSET
    per_seat_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        access_fee_micros: int | None | Unset
        if isinstance(self.access_fee_micros, Unset):
            access_fee_micros = UNSET
        else:
            access_fee_micros = self.access_fee_micros

        fixed_uplift_micros: int | None | Unset
        if isinstance(self.fixed_uplift_micros, Unset):
            fixed_uplift_micros = UNSET
        else:
            fixed_uplift_micros = self.fixed_uplift_micros

        markup_percentage_micros: int | None | Unset
        if isinstance(self.markup_percentage_micros, Unset):
            markup_percentage_micros = UNSET
        else:
            markup_percentage_micros = self.markup_percentage_micros

        migrate_existing = self.migrate_existing

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        per_seat_micros: int | None | Unset
        if isinstance(self.per_seat_micros, Unset):
            per_seat_micros = UNSET
        else:
            per_seat_micros = self.per_seat_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if access_fee_micros is not UNSET:
            field_dict["access_fee_micros"] = access_fee_micros
        if fixed_uplift_micros is not UNSET:
            field_dict["fixed_uplift_micros"] = fixed_uplift_micros
        if markup_percentage_micros is not UNSET:
            field_dict["markup_percentage_micros"] = markup_percentage_micros
        if migrate_existing is not UNSET:
            field_dict["migrate_existing"] = migrate_existing
        if name is not UNSET:
            field_dict["name"] = name
        if per_seat_micros is not UNSET:
            field_dict["per_seat_micros"] = per_seat_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_access_fee_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        access_fee_micros = _parse_access_fee_micros(d.pop("access_fee_micros", UNSET))


        def _parse_fixed_uplift_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fixed_uplift_micros = _parse_fixed_uplift_micros(d.pop("fixed_uplift_micros", UNSET))


        def _parse_markup_percentage_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        markup_percentage_micros = _parse_markup_percentage_micros(d.pop("markup_percentage_micros", UNSET))


        migrate_existing = d.pop("migrate_existing", UNSET)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))


        def _parse_per_seat_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        per_seat_micros = _parse_per_seat_micros(d.pop("per_seat_micros", UNSET))


        plan_update_in = cls(
            access_fee_micros=access_fee_micros,
            fixed_uplift_micros=fixed_uplift_micros,
            markup_percentage_micros=markup_percentage_micros,
            migrate_existing=migrate_existing,
            name=name,
            per_seat_micros=per_seat_micros,
        )


        plan_update_in.additional_properties = d
        return plan_update_in

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
