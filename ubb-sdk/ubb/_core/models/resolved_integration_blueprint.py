from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.resolved_integration_blueprint_readiness import ResolvedIntegrationBlueprintReadiness
from ..models.resolved_integration_blueprint_target import ResolvedIntegrationBlueprintTarget
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.integration_blueprint_call import IntegrationBlueprintCall
  from ..models.integration_blueprint_diagnostic import IntegrationBlueprintDiagnostic





T = TypeVar("T", bound="ResolvedIntegrationBlueprint")



@_attrs_define
class ResolvedIntegrationBlueprint:
    """ What a tenant's integration code must mean, resolved from what the
    tenant has declared.

    `schema_version` is the shape of this document. `renderer_contract_version`
    is the renderer contract it was resolved for. `sdk_major_version` is set
    for the `python_sdk` target and null otherwise.

    `configuration_fingerprint` identifies the stored snapshot of exactly this
    resolution — `sha256:` and 64 hexadecimal characters — and is null for a
    draft preview. `readiness` is the least ready of `calls`.

        Attributes:
            calls (list[IntegrationBlueprintCall]):
            diagnostics (list[IntegrationBlueprintDiagnostic]):
            readiness (ResolvedIntegrationBlueprintReadiness):
            renderer_contract_version (int):
            schema_version (int):
            target (ResolvedIntegrationBlueprintTarget):
            configuration_fingerprint (None | str | Unset):
            sdk_major_version (int | None | Unset):
     """

    calls: list[IntegrationBlueprintCall]
    diagnostics: list[IntegrationBlueprintDiagnostic]
    readiness: ResolvedIntegrationBlueprintReadiness
    renderer_contract_version: int
    schema_version: int
    target: ResolvedIntegrationBlueprintTarget
    configuration_fingerprint: None | str | Unset = UNSET
    sdk_major_version: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_blueprint_call import IntegrationBlueprintCall
        from ..models.integration_blueprint_diagnostic import IntegrationBlueprintDiagnostic
        calls = []
        for calls_item_data in self.calls:
            calls_item = calls_item_data.to_dict()
            calls.append(calls_item)



        diagnostics = []
        for diagnostics_item_data in self.diagnostics:
            diagnostics_item = diagnostics_item_data.to_dict()
            diagnostics.append(diagnostics_item)



        readiness = self.readiness.value

        renderer_contract_version = self.renderer_contract_version

        schema_version = self.schema_version

        target = self.target.value

        configuration_fingerprint: None | str | Unset
        if isinstance(self.configuration_fingerprint, Unset):
            configuration_fingerprint = UNSET
        else:
            configuration_fingerprint = self.configuration_fingerprint

        sdk_major_version: int | None | Unset
        if isinstance(self.sdk_major_version, Unset):
            sdk_major_version = UNSET
        else:
            sdk_major_version = self.sdk_major_version


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "calls": calls,
            "diagnostics": diagnostics,
            "readiness": readiness,
            "renderer_contract_version": renderer_contract_version,
            "schema_version": schema_version,
            "target": target,
        })
        if configuration_fingerprint is not UNSET:
            field_dict["configuration_fingerprint"] = configuration_fingerprint
        if sdk_major_version is not UNSET:
            field_dict["sdk_major_version"] = sdk_major_version

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_blueprint_call import IntegrationBlueprintCall
        from ..models.integration_blueprint_diagnostic import IntegrationBlueprintDiagnostic
        d = dict(src_dict)
        calls = []
        _calls = d.pop("calls")
        for calls_item_data in (_calls):
            calls_item = IntegrationBlueprintCall.from_dict(calls_item_data)



            calls.append(calls_item)


        diagnostics = []
        _diagnostics = d.pop("diagnostics")
        for diagnostics_item_data in (_diagnostics):
            diagnostics_item = IntegrationBlueprintDiagnostic.from_dict(diagnostics_item_data)



            diagnostics.append(diagnostics_item)


        readiness = ResolvedIntegrationBlueprintReadiness(d.pop("readiness"))




        renderer_contract_version = d.pop("renderer_contract_version")

        schema_version = d.pop("schema_version")

        target = ResolvedIntegrationBlueprintTarget(d.pop("target"))




        def _parse_configuration_fingerprint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        configuration_fingerprint = _parse_configuration_fingerprint(d.pop("configuration_fingerprint", UNSET))


        def _parse_sdk_major_version(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        sdk_major_version = _parse_sdk_major_version(d.pop("sdk_major_version", UNSET))


        resolved_integration_blueprint = cls(
            calls=calls,
            diagnostics=diagnostics,
            readiness=readiness,
            renderer_contract_version=renderer_contract_version,
            schema_version=schema_version,
            target=target,
            configuration_fingerprint=configuration_fingerprint,
            sdk_major_version=sdk_major_version,
        )


        resolved_integration_blueprint.additional_properties = d
        return resolved_integration_blueprint

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
