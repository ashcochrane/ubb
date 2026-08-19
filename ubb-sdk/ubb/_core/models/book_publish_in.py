from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime

if TYPE_CHECKING:
  from ..models.book_change_in import BookChangeIn





T = TypeVar("T", bound="BookPublishIn")



@_attrs_define
class BookPublishIn:
    """ The intended changes, and when they take effect.

    **`effective_at` IS WHAT DATES A CHANGE FORWARD, AND OMITTING IT MEANS
    NOW.** A tenant who has agreed a rise from the first of next month states
    that instant here and stops having to remember: publishing writes the rows
    immediately, carrying the boundary as a value the resolver reads, so
    **nothing runs at the instant itself**. There is no job to be late, which
    matters because a late job would price every event in the gap at the old
    rate and that wrong price would sit permanently on an authoritative record.

    The instant must be timezone-aware (`effective_at_naive`). A change is dated
    forward or not at all, so an instant more than five minutes behind the
    present is refused with `effective_at_in_past` — the allowance is clock
    skew, so that a caller stamping its own "now" is not told its clock is
    wrong. And it must be within the platform's forward horizon of **366 days**;
    beyond it the request is refused with `effective_at_too_far_ahead`.

    Each of the three carries a code of its own so that *"that date is a typo"*
    is distinguishable from *"that date has passed"* and from every other reason
    a body is refused. The horizon is a platform bound and no tenant setting
    moves it.

        Attributes:
            changes (list[BookChangeIn]):
            effective_at (datetime.datetime | None | Unset):
     """

    changes: list[BookChangeIn]
    effective_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.book_change_in import BookChangeIn
        changes = []
        for changes_item_data in self.changes:
            changes_item = changes_item_data.to_dict()
            changes.append(changes_item)



        effective_at: None | str | Unset
        if isinstance(self.effective_at, Unset):
            effective_at = UNSET
        elif isinstance(self.effective_at, datetime.datetime):
            effective_at = self.effective_at.isoformat()
        else:
            effective_at = self.effective_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "changes": changes,
        })
        if effective_at is not UNSET:
            field_dict["effective_at"] = effective_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.book_change_in import BookChangeIn
        d = dict(src_dict)
        changes = []
        _changes = d.pop("changes")
        for changes_item_data in (_changes):
            changes_item = BookChangeIn.from_dict(changes_item_data)



            changes.append(changes_item)


        def _parse_effective_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                effective_at_type_0 = datetime.datetime.fromisoformat(data)



                return effective_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        effective_at = _parse_effective_at(d.pop("effective_at", UNSET))


        book_publish_in = cls(
            changes=changes,
            effective_at=effective_at,
        )


        book_publish_in.additional_properties = d
        return book_publish_in

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
