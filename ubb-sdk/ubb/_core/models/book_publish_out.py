from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.book_change_diff_out import BookChangeDiffOut





T = TypeVar("T", bound="BookPublishOut")



@_attrs_define
class BookPublishOut:
    """ A change to a book: an intention while it is a draft, a decision once
    published.

    ⚠ `declaration_status` is deliberately UNMARKED, on the same footing as
    `EventTypeOut.declaration_status`: the concept declares no `openapi`
    consumer in the registry, and the applier refuses a marker for a concept
    that contributes nothing. A field is marked by the ticket that declares its
    concept's contract consumer, never by one passing nearby. The FIELD is still
    final under ADR-0007 §3 — gaining an `enum` later is additive, and its
    values are already the registry's.

        Attributes:
            actor_display (str):
            actor_id (str):
            actor_kind (str):
            book_id (str):
            closed_rule_ids (list[str]):
            declaration_status (str):
            effective_at (str):
            id (str):
            opened_rule_ids (list[str]):
            diff (list[BookChangeDiffOut] | None | Unset):
            diff_unavailable_reason (None | str | Unset):
            published_at (None | str | Unset):
     """

    actor_display: str
    actor_id: str
    actor_kind: str
    book_id: str
    closed_rule_ids: list[str]
    declaration_status: str
    effective_at: str
    id: str
    opened_rule_ids: list[str]
    diff: list[BookChangeDiffOut] | None | Unset = UNSET
    diff_unavailable_reason: None | str | Unset = UNSET
    published_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.book_change_diff_out import BookChangeDiffOut
        actor_display = self.actor_display

        actor_id = self.actor_id

        actor_kind = self.actor_kind

        book_id = self.book_id

        closed_rule_ids = self.closed_rule_ids



        declaration_status = self.declaration_status

        effective_at = self.effective_at

        id = self.id

        opened_rule_ids = self.opened_rule_ids



        diff: list[dict[str, Any]] | None | Unset
        if isinstance(self.diff, Unset):
            diff = UNSET
        elif isinstance(self.diff, list):
            diff = []
            for diff_type_0_item_data in self.diff:
                diff_type_0_item = diff_type_0_item_data.to_dict()
                diff.append(diff_type_0_item)


        else:
            diff = self.diff

        diff_unavailable_reason: None | str | Unset
        if isinstance(self.diff_unavailable_reason, Unset):
            diff_unavailable_reason = UNSET
        else:
            diff_unavailable_reason = self.diff_unavailable_reason

        published_at: None | str | Unset
        if isinstance(self.published_at, Unset):
            published_at = UNSET
        else:
            published_at = self.published_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "actor_display": actor_display,
            "actor_id": actor_id,
            "actor_kind": actor_kind,
            "book_id": book_id,
            "closed_rule_ids": closed_rule_ids,
            "declaration_status": declaration_status,
            "effective_at": effective_at,
            "id": id,
            "opened_rule_ids": opened_rule_ids,
        })
        if diff is not UNSET:
            field_dict["diff"] = diff
        if diff_unavailable_reason is not UNSET:
            field_dict["diff_unavailable_reason"] = diff_unavailable_reason
        if published_at is not UNSET:
            field_dict["published_at"] = published_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.book_change_diff_out import BookChangeDiffOut
        d = dict(src_dict)
        actor_display = d.pop("actor_display")

        actor_id = d.pop("actor_id")

        actor_kind = d.pop("actor_kind")

        book_id = d.pop("book_id")

        closed_rule_ids = cast(list[str], d.pop("closed_rule_ids"))


        declaration_status = d.pop("declaration_status")

        effective_at = d.pop("effective_at")

        id = d.pop("id")

        opened_rule_ids = cast(list[str], d.pop("opened_rule_ids"))


        def _parse_diff(data: object) -> list[BookChangeDiffOut] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                diff_type_0 = []
                _diff_type_0 = data
                for diff_type_0_item_data in (_diff_type_0):
                    diff_type_0_item = BookChangeDiffOut.from_dict(diff_type_0_item_data)



                    diff_type_0.append(diff_type_0_item)

                return diff_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[BookChangeDiffOut] | None | Unset, data)

        diff = _parse_diff(d.pop("diff", UNSET))


        def _parse_diff_unavailable_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        diff_unavailable_reason = _parse_diff_unavailable_reason(d.pop("diff_unavailable_reason", UNSET))


        def _parse_published_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        published_at = _parse_published_at(d.pop("published_at", UNSET))


        book_publish_out = cls(
            actor_display=actor_display,
            actor_id=actor_id,
            actor_kind=actor_kind,
            book_id=book_id,
            closed_rule_ids=closed_rule_ids,
            declaration_status=declaration_status,
            effective_at=effective_at,
            id=id,
            opened_rule_ids=opened_rule_ids,
            diff=diff,
            diff_unavailable_reason=diff_unavailable_reason,
            published_at=published_at,
        )


        book_publish_out.additional_properties = d
        return book_publish_out

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
