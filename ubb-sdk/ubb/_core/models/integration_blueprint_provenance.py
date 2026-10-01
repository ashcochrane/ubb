from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.integration_blueprint_provenance_object_kind import IntegrationBlueprintProvenanceObjectKind
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="IntegrationBlueprintProvenance")



@_attrs_define
class IntegrationBlueprintProvenance:
    """ Which declaration a value was read from.

        Attributes:
            key (str):
            object_kind (IntegrationBlueprintProvenanceObjectKind):
            published_at (None | str | Unset):
            published_revision (int | None | Unset):
     """

    key: str
    object_kind: IntegrationBlueprintProvenanceObjectKind
    published_at: None | str | Unset = UNSET
    published_revision: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        key = self.key

        object_kind = self.object_kind.value

        published_at: None | str | Unset
        if isinstance(self.published_at, Unset):
            published_at = UNSET
        else:
            published_at = self.published_at

        published_revision: int | None | Unset
        if isinstance(self.published_revision, Unset):
            published_revision = UNSET
        else:
            published_revision = self.published_revision


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
            "object_kind": object_kind,
        })
        if published_at is not UNSET:
            field_dict["published_at"] = published_at
        if published_revision is not UNSET:
            field_dict["published_revision"] = published_revision

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        object_kind = IntegrationBlueprintProvenanceObjectKind(d.pop("object_kind"))




        def _parse_published_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        published_at = _parse_published_at(d.pop("published_at", UNSET))


        def _parse_published_revision(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        published_revision = _parse_published_revision(d.pop("published_revision", UNSET))


        integration_blueprint_provenance = cls(
            key=key,
            object_kind=object_kind,
            published_at=published_at,
            published_revision=published_revision,
        )


        integration_blueprint_provenance.additional_properties = d
        return integration_blueprint_provenance

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
