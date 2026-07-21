from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ProblemOut")



@_attrs_define
class ProblemOut:
    """ RFC 9457 problem+json, for ``response=`` documentation of error
    statuses. Extension members (e.g. ``balance_micros``) are open-world and
    deliberately unmodeled.

        Attributes:
            code (str):
            status (int):
            title (str):
            type_ (str):
            detail (None | str | Unset):
     """

    code: str
    status: int
    title: str
    type_: str
    detail: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        code = self.code

        status = self.status

        title = self.title

        type_ = self.type_

        detail: None | str | Unset
        if isinstance(self.detail, Unset):
            detail = UNSET
        else:
            detail = self.detail


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "code": code,
            "status": status,
            "title": title,
            "type": type_,
        })
        if detail is not UNSET:
            field_dict["detail"] = detail

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = d.pop("code")

        status = d.pop("status")

        title = d.pop("title")

        type_ = d.pop("type")

        def _parse_detail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        detail = _parse_detail(d.pop("detail", UNSET))


        problem_out = cls(
            code=code,
            status=status,
            title=title,
            type_=type_,
            detail=detail,
        )


        problem_out.additional_properties = d
        return problem_out

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
