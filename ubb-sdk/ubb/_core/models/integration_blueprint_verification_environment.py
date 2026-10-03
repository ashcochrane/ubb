from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast
import datetime






T = TypeVar("T", bound="IntegrationBlueprintVerificationEnvironment")



@_attrs_define
class IntegrationBlueprintVerificationEnvironment:
    """ Where the verification ran, and what it supplied that the stored
    configuration does not hold.

    It ran in a tenant made for it from the stored configuration, inside one
    transaction that is rolled back when the run ends: `discarded` is always
    true, and every id in the acknowledgements names a record that no longer
    exists. Nothing it did was delivered — no webhook, no Stripe call — and a
    stop it reached was not acted on.

    `customer_external_id` is the customer it recorded for, made for the run:
    on no plan and with no deal of its own. Who the customer is decides no
    cost — no cost rule names a customer, and the stored configuration holds
    only rules for every customer — so it cannot move what `verified` proves;
    the customer price it is charged is that of a customer with neither.
    `rules_effective_at` is the moment every stored Cost Rate and pricing rule
    took effect: each is in force for the run whatever window it was declared
    with.

        Attributes:
            customer_external_id (str):
            discarded (bool):
            rules_effective_at (datetime.datetime):
     """

    customer_external_id: str
    discarded: bool
    rules_effective_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        customer_external_id = self.customer_external_id

        discarded = self.discarded

        rules_effective_at = self.rules_effective_at.isoformat()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_external_id": customer_external_id,
            "discarded": discarded,
            "rules_effective_at": rules_effective_at,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        customer_external_id = d.pop("customer_external_id")

        discarded = d.pop("discarded")

        rules_effective_at = datetime.datetime.fromisoformat(d.pop("rules_effective_at"))




        integration_blueprint_verification_environment = cls(
            customer_external_id=customer_external_id,
            discarded=discarded,
            rules_effective_at=rules_effective_at,
        )


        integration_blueprint_verification_environment.additional_properties = d
        return integration_blueprint_verification_environment

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
