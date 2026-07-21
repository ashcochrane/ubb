from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset







T = TypeVar("T", bound="ConfigureAutoTopUpRequest")



@_attrs_define
class ConfigureAutoTopUpRequest:
    """ 
        Attributes:
            is_enabled (bool):
            top_up_amount_micros (int):
            trigger_threshold_micros (int):
     """

    is_enabled: bool
    top_up_amount_micros: int
    trigger_threshold_micros: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        is_enabled = self.is_enabled

        top_up_amount_micros = self.top_up_amount_micros

        trigger_threshold_micros = self.trigger_threshold_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "is_enabled": is_enabled,
            "top_up_amount_micros": top_up_amount_micros,
            "trigger_threshold_micros": trigger_threshold_micros,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        is_enabled = d.pop("is_enabled")

        top_up_amount_micros = d.pop("top_up_amount_micros")

        trigger_threshold_micros = d.pop("trigger_threshold_micros")

        configure_auto_top_up_request = cls(
            is_enabled=is_enabled,
            top_up_amount_micros=top_up_amount_micros,
            trigger_threshold_micros=trigger_threshold_micros,
        )


        configure_auto_top_up_request.additional_properties = d
        return configure_auto_top_up_request

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
