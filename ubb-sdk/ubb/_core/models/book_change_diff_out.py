from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.book_change_diff_out_grouping_fields import BookChangeDiffOutGroupingFields
  from ..models.rule_terms_out import RuleTermsOut





T = TypeVar("T", bound="BookChangeDiffOut")



@_attrs_define
class BookChangeDiffOut:
    """ One row of the diff: which rule, and what happens to it.

    `before` is the rule as it will stand at the publish's effective instant and
    is null where the change adds one; `after` is the rule the publish opens and
    is null where the change retires one. Neither is null on a reprice, which is
    what makes the row readable as a change rather than as an outcome.

        Attributes:
            event_type (str):
            kind (str):
            measurement_key (str):
            provider (str):
            subtask_type (str):
            task_type (str):
            after (None | RuleTermsOut | Unset):
            before (None | RuleTermsOut | Unset):
            grouping_fields (BookChangeDiffOutGroupingFields | Unset):
     """

    event_type: str
    kind: str
    measurement_key: str
    provider: str
    subtask_type: str
    task_type: str
    after: None | RuleTermsOut | Unset = UNSET
    before: None | RuleTermsOut | Unset = UNSET
    grouping_fields: BookChangeDiffOutGroupingFields | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.book_change_diff_out_grouping_fields import BookChangeDiffOutGroupingFields
        from ..models.rule_terms_out import RuleTermsOut
        event_type = self.event_type

        kind = self.kind

        measurement_key = self.measurement_key

        provider = self.provider

        subtask_type = self.subtask_type

        task_type = self.task_type

        after: dict[str, Any] | None | Unset
        if isinstance(self.after, Unset):
            after = UNSET
        elif isinstance(self.after, RuleTermsOut):
            after = self.after.to_dict()
        else:
            after = self.after

        before: dict[str, Any] | None | Unset
        if isinstance(self.before, Unset):
            before = UNSET
        elif isinstance(self.before, RuleTermsOut):
            before = self.before.to_dict()
        else:
            before = self.before

        grouping_fields: dict[str, Any] | Unset = UNSET
        if not isinstance(self.grouping_fields, Unset):
            grouping_fields = self.grouping_fields.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event_type": event_type,
            "kind": kind,
            "measurement_key": measurement_key,
            "provider": provider,
            "subtask_type": subtask_type,
            "task_type": task_type,
        })
        if after is not UNSET:
            field_dict["after"] = after
        if before is not UNSET:
            field_dict["before"] = before
        if grouping_fields is not UNSET:
            field_dict["grouping_fields"] = grouping_fields

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.book_change_diff_out_grouping_fields import BookChangeDiffOutGroupingFields
        from ..models.rule_terms_out import RuleTermsOut
        d = dict(src_dict)
        event_type = d.pop("event_type")

        kind = d.pop("kind")

        measurement_key = d.pop("measurement_key")

        provider = d.pop("provider")

        subtask_type = d.pop("subtask_type")

        task_type = d.pop("task_type")

        def _parse_after(data: object) -> None | RuleTermsOut | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                after_type_0 = RuleTermsOut.from_dict(data)



                return after_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuleTermsOut | Unset, data)

        after = _parse_after(d.pop("after", UNSET))


        def _parse_before(data: object) -> None | RuleTermsOut | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                before_type_0 = RuleTermsOut.from_dict(data)



                return before_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuleTermsOut | Unset, data)

        before = _parse_before(d.pop("before", UNSET))


        _grouping_fields = d.pop("grouping_fields", UNSET)
        grouping_fields: BookChangeDiffOutGroupingFields | Unset
        if isinstance(_grouping_fields,  Unset):
            grouping_fields = UNSET
        else:
            grouping_fields = BookChangeDiffOutGroupingFields.from_dict(_grouping_fields)




        book_change_diff_out = cls(
            event_type=event_type,
            kind=kind,
            measurement_key=measurement_key,
            provider=provider,
            subtask_type=subtask_type,
            task_type=task_type,
            after=after,
            before=before,
            grouping_fields=grouping_fields,
        )


        book_change_diff_out.additional_properties = d
        return book_change_diff_out

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
