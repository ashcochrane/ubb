from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.integration_blueprint_verification_environment import IntegrationBlueprintVerificationEnvironment
  from ..models.integration_blueprint_verification_record import IntegrationBlueprintVerificationRecord
  from ..models.integration_blueprint_verification_refusal import IntegrationBlueprintVerificationRefusal
  from ..models.integration_blueprint_verification_unit import IntegrationBlueprintVerificationUnit





T = TypeVar("T", bound="IntegrationBlueprintVerification")



@_attrs_define
class IntegrationBlueprintVerification:
    """ What verifying a stored Blueprint found.

    `verified` is a statement about the WHOLE Blueprint, and about recording
    and costing. It is true only when every Event Type and every Subtask kind
    the Blueprint selected was exercised, no call of the run was refused, and
    every recording is `complete`. It does not say a customer price resolved:
    each acknowledgement's `pricing_status` says that, and `verified` does not
    read it.

    A run may exercise less than the Blueprint selected. It then lists what it
    left out in `unexercised_event_types` and `unexercised_subtask_types`, and
    `verified` is false. A gap fails it without failing the request: the
    acknowledgement that shows the gap is in `records`.

        Attributes:
            configuration_fingerprint (str):
            environment (IntegrationBlueprintVerificationEnvironment): Where the verification ran, and what it supplied that
                the stored
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
            records (list[IntegrationBlueprintVerificationRecord]):
            subtasks (list[IntegrationBlueprintVerificationUnit]):
            task (IntegrationBlueprintVerificationUnit): One unit of work the verification started, as its start and its
                close
                answered. Either is null where the run stopped before it.
            unexercised_event_types (list[str]):
            unexercised_subtask_types (list[str]):
            verified (bool):
            refusal (IntegrationBlueprintVerificationRefusal | None | Unset):
     """

    configuration_fingerprint: str
    environment: IntegrationBlueprintVerificationEnvironment
    records: list[IntegrationBlueprintVerificationRecord]
    subtasks: list[IntegrationBlueprintVerificationUnit]
    task: IntegrationBlueprintVerificationUnit
    unexercised_event_types: list[str]
    unexercised_subtask_types: list[str]
    verified: bool
    refusal: IntegrationBlueprintVerificationRefusal | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_blueprint_verification_environment import IntegrationBlueprintVerificationEnvironment
        from ..models.integration_blueprint_verification_record import IntegrationBlueprintVerificationRecord
        from ..models.integration_blueprint_verification_refusal import IntegrationBlueprintVerificationRefusal
        from ..models.integration_blueprint_verification_unit import IntegrationBlueprintVerificationUnit
        configuration_fingerprint = self.configuration_fingerprint

        environment = self.environment.to_dict()

        records = []
        for records_item_data in self.records:
            records_item = records_item_data.to_dict()
            records.append(records_item)



        subtasks = []
        for subtasks_item_data in self.subtasks:
            subtasks_item = subtasks_item_data.to_dict()
            subtasks.append(subtasks_item)



        task = self.task.to_dict()

        unexercised_event_types = self.unexercised_event_types



        unexercised_subtask_types = self.unexercised_subtask_types



        verified = self.verified

        refusal: dict[str, Any] | None | Unset
        if isinstance(self.refusal, Unset):
            refusal = UNSET
        elif isinstance(self.refusal, IntegrationBlueprintVerificationRefusal):
            refusal = self.refusal.to_dict()
        else:
            refusal = self.refusal


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "configuration_fingerprint": configuration_fingerprint,
            "environment": environment,
            "records": records,
            "subtasks": subtasks,
            "task": task,
            "unexercised_event_types": unexercised_event_types,
            "unexercised_subtask_types": unexercised_subtask_types,
            "verified": verified,
        })
        if refusal is not UNSET:
            field_dict["refusal"] = refusal

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_blueprint_verification_environment import IntegrationBlueprintVerificationEnvironment
        from ..models.integration_blueprint_verification_record import IntegrationBlueprintVerificationRecord
        from ..models.integration_blueprint_verification_refusal import IntegrationBlueprintVerificationRefusal
        from ..models.integration_blueprint_verification_unit import IntegrationBlueprintVerificationUnit
        d = dict(src_dict)
        configuration_fingerprint = d.pop("configuration_fingerprint")

        environment = IntegrationBlueprintVerificationEnvironment.from_dict(d.pop("environment"))




        records = []
        _records = d.pop("records")
        for records_item_data in (_records):
            records_item = IntegrationBlueprintVerificationRecord.from_dict(records_item_data)



            records.append(records_item)


        subtasks = []
        _subtasks = d.pop("subtasks")
        for subtasks_item_data in (_subtasks):
            subtasks_item = IntegrationBlueprintVerificationUnit.from_dict(subtasks_item_data)



            subtasks.append(subtasks_item)


        task = IntegrationBlueprintVerificationUnit.from_dict(d.pop("task"))




        unexercised_event_types = cast(list[str], d.pop("unexercised_event_types"))


        unexercised_subtask_types = cast(list[str], d.pop("unexercised_subtask_types"))


        verified = d.pop("verified")

        def _parse_refusal(data: object) -> IntegrationBlueprintVerificationRefusal | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                refusal_type_0 = IntegrationBlueprintVerificationRefusal.from_dict(data)



                return refusal_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IntegrationBlueprintVerificationRefusal | None | Unset, data)

        refusal = _parse_refusal(d.pop("refusal", UNSET))


        integration_blueprint_verification = cls(
            configuration_fingerprint=configuration_fingerprint,
            environment=environment,
            records=records,
            subtasks=subtasks,
            task=task,
            unexercised_event_types=unexercised_event_types,
            unexercised_subtask_types=unexercised_subtask_types,
            verified=verified,
            refusal=refusal,
        )


        integration_blueprint_verification.additional_properties = d
        return integration_blueprint_verification

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
