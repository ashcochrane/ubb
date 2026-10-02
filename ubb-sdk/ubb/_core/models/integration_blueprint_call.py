from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.integration_blueprint_call_readiness import IntegrationBlueprintCallReadiness
from typing import cast

if TYPE_CHECKING:
  from ..models.integration_blueprint_argument import IntegrationBlueprintArgument





T = TypeVar("T", bound="IntegrationBlueprintCall")



@_attrs_define
class IntegrationBlueprintCall:
    """ One generated call site: a real v1 operation and the tokens it takes.

        Attributes:
            arguments (list[IntegrationBlueprintArgument]):
            operation_id (str):
            readiness (IntegrationBlueprintCallReadiness):
     """

    arguments: list[IntegrationBlueprintArgument]
    operation_id: str
    readiness: IntegrationBlueprintCallReadiness
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_blueprint_argument import IntegrationBlueprintArgument
        arguments = []
        for arguments_item_data in self.arguments:
            arguments_item = arguments_item_data.to_dict()
            arguments.append(arguments_item)



        operation_id = self.operation_id

        readiness = self.readiness.value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "arguments": arguments,
            "operation_id": operation_id,
            "readiness": readiness,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_blueprint_argument import IntegrationBlueprintArgument
        d = dict(src_dict)
        arguments = []
        _arguments = d.pop("arguments")
        for arguments_item_data in (_arguments):
            arguments_item = IntegrationBlueprintArgument.from_dict(arguments_item_data)



            arguments.append(arguments_item)


        operation_id = d.pop("operation_id")

        readiness = IntegrationBlueprintCallReadiness(d.pop("readiness"))




        integration_blueprint_call = cls(
            arguments=arguments,
            operation_id=operation_id,
            readiness=readiness,
        )


        integration_blueprint_call.additional_properties = d
        return integration_blueprint_call

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
