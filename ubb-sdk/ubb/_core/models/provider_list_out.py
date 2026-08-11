from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.provider_out import ProviderOut





T = TypeVar("T", bound="ProviderListOut")



@_attrs_define
class ProviderListOut:
    """ 
        Attributes:
            providers (list[ProviderOut]):
     """

    providers: list[ProviderOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.provider_out import ProviderOut
        providers = []
        for providers_item_data in self.providers:
            providers_item = providers_item_data.to_dict()
            providers.append(providers_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "providers": providers,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provider_out import ProviderOut
        d = dict(src_dict)
        providers = []
        _providers = d.pop("providers")
        for providers_item_data in (_providers):
            providers_item = ProviderOut.from_dict(providers_item_data)



            providers.append(providers_item)


        provider_list_out = cls(
            providers=providers,
        )


        provider_list_out.additional_properties = d
        return provider_list_out

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
