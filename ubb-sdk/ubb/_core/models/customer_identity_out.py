from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="CustomerIdentityOut")



@_attrs_define
class CustomerIdentityOut:
    """ Who a customer IS, by the identity UBB assigned them.

    ⚠ **THIS ROUTE EXISTS BECAUSE #501 TOOK AWAY THE ONLY READ THAT ANSWERED
    IT**, and that is worth stating on a slice whose whole subject is removing
    published surface. One customer's margin used to publish `external_id`
    beside its figures, and that was the single place a caller holding UBB's
    identity for a customer could learn the tenant's own word for them. The one
    economic query groups by IDENTITY and publishes no external id — rightly: a
    tenant's own vocabulary is not a measure, and a report is not a directory.
    So the capability was never the report's, and it is here, on the mount that
    owns customers.

    It matters beyond a page title: the subscription lifecycle is keyed on the
    external id (`/subscriptions/customers/{external_id}/...`) while every
    metering and billing read is keyed on the UUID, so a surface holding one and
    needing the other has nowhere else to turn.

    `account_type` and `parent_external_id` travel with it because a seat's
    bill is its business's, and a caller that had to ask a second question to
    find that out would be one round trip from rendering a seat as if it paid
    its own way.

        Attributes:
            account_type (str):
            external_id (str):
            id (str):
            status (str):
            parent_external_id (str | Unset):  Default: ''.
     """

    account_type: str
    external_id: str
    id: str
    status: str
    parent_external_id: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        account_type = self.account_type

        external_id = self.external_id

        id = self.id

        status = self.status

        parent_external_id = self.parent_external_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "account_type": account_type,
            "external_id": external_id,
            "id": id,
            "status": status,
        })
        if parent_external_id is not UNSET:
            field_dict["parent_external_id"] = parent_external_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        account_type = d.pop("account_type")

        external_id = d.pop("external_id")

        id = d.pop("id")

        status = d.pop("status")

        parent_external_id = d.pop("parent_external_id", UNSET)

        customer_identity_out = cls(
            account_type=account_type,
            external_id=external_id,
            id=id,
            status=status,
            parent_external_id=parent_external_id,
        )


        customer_identity_out.additional_properties = d
        return customer_identity_out

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
