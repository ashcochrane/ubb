from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.integration_blueprint_argument_binding_class import IntegrationBlueprintArgumentBindingClass
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.integration_blueprint_provenance import IntegrationBlueprintProvenance





T = TypeVar("T", bound="IntegrationBlueprintArgument")



@_attrs_define
class IntegrationBlueprintArgument:
    """ One token of a call, and where its value comes from.

    `name` says where the token sits, as one to three segments joined by
    dots. `<field>` is a field of the operation's request, or the credential
    `api_key`; for a field holding an object of declared keys
    (`grouping_fields`, `measurements`) it is one key of that object, carried
    as the literal. `<field>.<key>` is the value under a declared key.
    `<field>.<element>` and `<field>.<key>.<element>` are declared facts
    about that value — `task_type.pricing_mode`,
    `measurements.<key>.source_path`. A dot or a percent sign inside a
    declared key is percent-encoded in a name, so a name always splits on its
    dots.

    Exactly one of `value`, `parameter_name` and `environment_variable` is
    set, by `binding_class` — except a `platform_known` token with
    `configured` false, which has no value yet.

        Attributes:
            binding_class (IntegrationBlueprintArgumentBindingClass):
            configured (bool):
            name (str):
            environment_variable (None | str | Unset):
            parameter_name (None | str | Unset):
            provenance (IntegrationBlueprintProvenance | None | Unset):
            value (Any | None | Unset):
     """

    binding_class: IntegrationBlueprintArgumentBindingClass
    configured: bool
    name: str
    environment_variable: None | str | Unset = UNSET
    parameter_name: None | str | Unset = UNSET
    provenance: IntegrationBlueprintProvenance | None | Unset = UNSET
    value: Any | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_blueprint_provenance import IntegrationBlueprintProvenance
        binding_class = self.binding_class.value

        configured = self.configured

        name = self.name

        environment_variable: None | str | Unset
        if isinstance(self.environment_variable, Unset):
            environment_variable = UNSET
        else:
            environment_variable = self.environment_variable

        parameter_name: None | str | Unset
        if isinstance(self.parameter_name, Unset):
            parameter_name = UNSET
        else:
            parameter_name = self.parameter_name

        provenance: dict[str, Any] | None | Unset
        if isinstance(self.provenance, Unset):
            provenance = UNSET
        elif isinstance(self.provenance, IntegrationBlueprintProvenance):
            provenance = self.provenance.to_dict()
        else:
            provenance = self.provenance

        value: Any | None | Unset
        if isinstance(self.value, Unset):
            value = UNSET
        else:
            value = self.value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "binding_class": binding_class,
            "configured": configured,
            "name": name,
        })
        if environment_variable is not UNSET:
            field_dict["environment_variable"] = environment_variable
        if parameter_name is not UNSET:
            field_dict["parameter_name"] = parameter_name
        if provenance is not UNSET:
            field_dict["provenance"] = provenance
        if value is not UNSET:
            field_dict["value"] = value

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_blueprint_provenance import IntegrationBlueprintProvenance
        d = dict(src_dict)
        binding_class = IntegrationBlueprintArgumentBindingClass(d.pop("binding_class"))




        configured = d.pop("configured")

        name = d.pop("name")

        def _parse_environment_variable(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        environment_variable = _parse_environment_variable(d.pop("environment_variable", UNSET))


        def _parse_parameter_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parameter_name = _parse_parameter_name(d.pop("parameter_name", UNSET))


        def _parse_provenance(data: object) -> IntegrationBlueprintProvenance | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                provenance_type_0 = IntegrationBlueprintProvenance.from_dict(data)



                return provenance_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IntegrationBlueprintProvenance | None | Unset, data)

        provenance = _parse_provenance(d.pop("provenance", UNSET))


        def _parse_value(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        value = _parse_value(d.pop("value", UNSET))


        integration_blueprint_argument = cls(
            binding_class=binding_class,
            configured=configured,
            name=name,
            environment_variable=environment_variable,
            parameter_name=parameter_name,
            provenance=provenance,
            value=value,
        )


        integration_blueprint_argument.additional_properties = d
        return integration_blueprint_argument

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
