from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.ready_response_checks import ReadyResponseChecks





T = TypeVar("T", bound="ReadyResponse")



@_attrs_define
class ReadyResponse:
    """ 
        Attributes:
            checks (ReadyResponseChecks):
            status (str):
     """

    checks: ReadyResponseChecks
    status: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.ready_response_checks import ReadyResponseChecks
        checks = self.checks.to_dict()

        status = self.status


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "checks": checks,
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ready_response_checks import ReadyResponseChecks
        d = dict(src_dict)
        checks = ReadyResponseChecks.from_dict(d.pop("checks"))




        status = d.pop("status")

        ready_response = cls(
            checks=checks,
            status=status,
        )


        ready_response.additional_properties = d
        return ready_response

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
