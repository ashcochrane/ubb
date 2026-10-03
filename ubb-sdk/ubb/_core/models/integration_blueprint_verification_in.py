from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.integration_blueprint_verification_in_grouping_fields import IntegrationBlueprintVerificationInGroupingFields
  from ..models.integration_blueprint_verification_record_in import IntegrationBlueprintVerificationRecordIn





T = TypeVar("T", bound="IntegrationBlueprintVerificationIn")



@_attrs_define
class IntegrationBlueprintVerificationIn:
    """ What one verification records, in order: between 1 and 50 events.

    `grouping_fields` is the sample value for each Grouping Field the
    Blueprint's kinds of work require, keyed as declared — the values a
    tenant's code passes when it starts the work. A required field left out
    is started with `ubb-verification`; a key no selected kind requires is
    refused.

        Attributes:
            records (list[IntegrationBlueprintVerificationRecordIn]):
            grouping_fields (IntegrationBlueprintVerificationInGroupingFields | Unset):
     """

    records: list[IntegrationBlueprintVerificationRecordIn]
    grouping_fields: IntegrationBlueprintVerificationInGroupingFields | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.integration_blueprint_verification_in_grouping_fields import IntegrationBlueprintVerificationInGroupingFields
        from ..models.integration_blueprint_verification_record_in import IntegrationBlueprintVerificationRecordIn
        records = []
        for records_item_data in self.records:
            records_item = records_item_data.to_dict()
            records.append(records_item)



        grouping_fields: dict[str, Any] | Unset = UNSET
        if not isinstance(self.grouping_fields, Unset):
            grouping_fields = self.grouping_fields.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "records": records,
        })
        if grouping_fields is not UNSET:
            field_dict["grouping_fields"] = grouping_fields

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.integration_blueprint_verification_in_grouping_fields import IntegrationBlueprintVerificationInGroupingFields
        from ..models.integration_blueprint_verification_record_in import IntegrationBlueprintVerificationRecordIn
        d = dict(src_dict)
        records = []
        _records = d.pop("records")
        for records_item_data in (_records):
            records_item = IntegrationBlueprintVerificationRecordIn.from_dict(records_item_data)



            records.append(records_item)


        _grouping_fields = d.pop("grouping_fields", UNSET)
        grouping_fields: IntegrationBlueprintVerificationInGroupingFields | Unset
        if isinstance(_grouping_fields,  Unset):
            grouping_fields = UNSET
        else:
            grouping_fields = IntegrationBlueprintVerificationInGroupingFields.from_dict(_grouping_fields)




        integration_blueprint_verification_in = cls(
            records=records,
            grouping_fields=grouping_fields,
        )


        integration_blueprint_verification_in.additional_properties = d
        return integration_blueprint_verification_in

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
