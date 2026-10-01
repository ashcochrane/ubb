from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.integration_blueprint_remediation_request_body_type_0 import IntegrationBlueprintRemediationRequestBodyType0





T = TypeVar("T", bound="IntegrationBlueprintRemediationRequest")



@_attrs_define
class IntegrationBlueprintRemediationRequest:
    """ The API request that fixes a diagnostic, ready to copy.

    UBB never sends it. The route names the object by its key, and `body` is
    the operation's published fields with every value left empty — null for
    an operation that takes no body.

        Attributes:
            method (str):
            operation_id (str):
            route (str):
            body (IntegrationBlueprintRemediationRequestBodyType0 | None | Unset):
     """

    method: str
    operation_id: str
    route: str
    body: IntegrationBlueprintRemediationRequestBodyType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_blueprint_remediation_request_body_type_0 import IntegrationBlueprintRemediationRequestBodyType0
        method = self.method

        operation_id = self.operation_id

        route = self.route

        body: dict[str, Any] | None | Unset
        if isinstance(self.body, Unset):
            body = UNSET
        elif isinstance(self.body, IntegrationBlueprintRemediationRequestBodyType0):
            body = self.body.to_dict()
        else:
            body = self.body


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "method": method,
            "operation_id": operation_id,
            "route": route,
        })
        if body is not UNSET:
            field_dict["body"] = body

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_blueprint_remediation_request_body_type_0 import IntegrationBlueprintRemediationRequestBodyType0
        d = dict(src_dict)
        method = d.pop("method")

        operation_id = d.pop("operation_id")

        route = d.pop("route")

        def _parse_body(data: object) -> IntegrationBlueprintRemediationRequestBodyType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                body_type_0 = IntegrationBlueprintRemediationRequestBodyType0.from_dict(data)



                return body_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IntegrationBlueprintRemediationRequestBodyType0 | None | Unset, data)

        body = _parse_body(d.pop("body", UNSET))


        integration_blueprint_remediation_request = cls(
            method=method,
            operation_id=operation_id,
            route=route,
            body=body,
        )


        integration_blueprint_remediation_request.additional_properties = d
        return integration_blueprint_remediation_request

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
