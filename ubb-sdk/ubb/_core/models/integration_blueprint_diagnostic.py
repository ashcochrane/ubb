from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.integration_blueprint_diagnostic_code import IntegrationBlueprintDiagnosticCode
from ..models.integration_blueprint_diagnostic_object_kind import IntegrationBlueprintDiagnosticObjectKind
from ..models.integration_blueprint_diagnostic_severity import IntegrationBlueprintDiagnosticSeverity
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.integration_blueprint_remediation_request import IntegrationBlueprintRemediationRequest





T = TypeVar("T", bound="IntegrationBlueprintDiagnostic")



@_attrs_define
class IntegrationBlueprintDiagnostic:
    """ Something that lowers readiness, or advice that does not.

    Coded and addressed, with no message: `code` says what is true, and
    `object_kind`, `key` and `field` say of which declaration. `key` is null
    where nothing was selected, and is `<event type>:<code>` for a
    Measurement. `remediation_request` is set for an Event Type, a
    Measurement, a reported-cost mapping and a Grouping Field, and null for a
    kind of work — and null for `constant_measurement_not_renderable` and
    `reported_cost_provider_response_not_renderable`, where the declaration is
    valid and complete and nothing in it is the thing to change: this Code
    Builder version cannot yet generate what it declares.

        Attributes:
            code (IntegrationBlueprintDiagnosticCode):
            object_kind (IntegrationBlueprintDiagnosticObjectKind):
            severity (IntegrationBlueprintDiagnosticSeverity):
            field (None | str | Unset):
            key (None | str | Unset):
            remediation_request (IntegrationBlueprintRemediationRequest | None | Unset):
     """

    code: IntegrationBlueprintDiagnosticCode
    object_kind: IntegrationBlueprintDiagnosticObjectKind
    severity: IntegrationBlueprintDiagnosticSeverity
    field: None | str | Unset = UNSET
    key: None | str | Unset = UNSET
    remediation_request: IntegrationBlueprintRemediationRequest | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_blueprint_remediation_request import IntegrationBlueprintRemediationRequest
        code = self.code.value

        object_kind = self.object_kind.value

        severity = self.severity.value

        field: None | str | Unset
        if isinstance(self.field, Unset):
            field = UNSET
        else:
            field = self.field

        key: None | str | Unset
        if isinstance(self.key, Unset):
            key = UNSET
        else:
            key = self.key

        remediation_request: dict[str, Any] | None | Unset
        if isinstance(self.remediation_request, Unset):
            remediation_request = UNSET
        elif isinstance(self.remediation_request, IntegrationBlueprintRemediationRequest):
            remediation_request = self.remediation_request.to_dict()
        else:
            remediation_request = self.remediation_request


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "code": code,
            "object_kind": object_kind,
            "severity": severity,
        })
        if field is not UNSET:
            field_dict["field"] = field
        if key is not UNSET:
            field_dict["key"] = key
        if remediation_request is not UNSET:
            field_dict["remediation_request"] = remediation_request

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_blueprint_remediation_request import IntegrationBlueprintRemediationRequest
        d = dict(src_dict)
        code = IntegrationBlueprintDiagnosticCode(d.pop("code"))




        object_kind = IntegrationBlueprintDiagnosticObjectKind(d.pop("object_kind"))




        severity = IntegrationBlueprintDiagnosticSeverity(d.pop("severity"))




        def _parse_field(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        field = _parse_field(d.pop("field", UNSET))


        def _parse_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        key = _parse_key(d.pop("key", UNSET))


        def _parse_remediation_request(data: object) -> IntegrationBlueprintRemediationRequest | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                remediation_request_type_0 = IntegrationBlueprintRemediationRequest.from_dict(data)



                return remediation_request_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IntegrationBlueprintRemediationRequest | None | Unset, data)

        remediation_request = _parse_remediation_request(d.pop("remediation_request", UNSET))


        integration_blueprint_diagnostic = cls(
            code=code,
            object_kind=object_kind,
            severity=severity,
            field=field,
            key=key,
            remediation_request=remediation_request,
        )


        integration_blueprint_diagnostic.additional_properties = d
        return integration_blueprint_diagnostic

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
