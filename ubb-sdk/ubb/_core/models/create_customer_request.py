from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.create_customer_request_metadata import CreateCustomerRequestMetadata





T = TypeVar("T", bound="CreateCustomerRequest")



@_attrs_define
class CreateCustomerRequest:
    """ 
        Attributes:
            external_id (str):
            account_type (str | Unset):  Default: 'individual'.
            billing_topology (str | Unset):  Default: ''.
            metadata (CreateCustomerRequestMetadata | Unset):
            parent_external_id (str | Unset):  Default: ''.
            stripe_customer_id (str | Unset):  Default: ''.
     """

    external_id: str
    account_type: str | Unset = 'individual'
    billing_topology: str | Unset = ''
    metadata: CreateCustomerRequestMetadata | Unset = UNSET
    parent_external_id: str | Unset = ''
    stripe_customer_id: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.create_customer_request_metadata import CreateCustomerRequestMetadata
        external_id = self.external_id

        account_type = self.account_type

        billing_topology = self.billing_topology

        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        parent_external_id = self.parent_external_id

        stripe_customer_id = self.stripe_customer_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "external_id": external_id,
        })
        if account_type is not UNSET:
            field_dict["account_type"] = account_type
        if billing_topology is not UNSET:
            field_dict["billing_topology"] = billing_topology
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if parent_external_id is not UNSET:
            field_dict["parent_external_id"] = parent_external_id
        if stripe_customer_id is not UNSET:
            field_dict["stripe_customer_id"] = stripe_customer_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_customer_request_metadata import CreateCustomerRequestMetadata
        d = dict(src_dict)
        external_id = d.pop("external_id")

        account_type = d.pop("account_type", UNSET)

        billing_topology = d.pop("billing_topology", UNSET)

        _metadata = d.pop("metadata", UNSET)
        metadata: CreateCustomerRequestMetadata | Unset
        if isinstance(_metadata,  Unset):
            metadata = UNSET
        else:
            metadata = CreateCustomerRequestMetadata.from_dict(_metadata)




        parent_external_id = d.pop("parent_external_id", UNSET)

        stripe_customer_id = d.pop("stripe_customer_id", UNSET)

        create_customer_request = cls(
            external_id=external_id,
            account_type=account_type,
            billing_topology=billing_topology,
            metadata=metadata,
            parent_external_id=parent_external_id,
            stripe_customer_id=stripe_customer_id,
        )


        create_customer_request.additional_properties = d
        return create_customer_request

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
