from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime






T = TypeVar("T", bound="ResolutionRunIn")



@_attrs_define
class ResolutionRunIn:
    """ Which postings this run should reach: a date range, a customer, an
    Event Type — in any combination, and any of them may be omitted.

    An omitted axis is unpinned rather than empty: a body naming nothing at all
    reaches every posting of this tenant that was never resolved. The date range
    is over the posting's own effective instant and is half-open — `[from, to)`
    — so running one month and then the next repairs each posting exactly once.

    A run reaches only postings whose status says they were never resolved, and
    that is a property of how the set is built rather than of what you send:
    there is no field here that could widen it to a posting already carrying a
    cost or a price, and none that could reach one whose charge was waived.

    Any other field is refused (`validation_error`). A run takes no condition of
    its own.

        Attributes:
            selected_customer_id (None | Unset | UUID):
            selected_event_type (str | Unset):  Default: ''.
            selected_from (datetime.datetime | None | Unset):
            selected_to (datetime.datetime | None | Unset):
     """

    selected_customer_id: None | Unset | UUID = UNSET
    selected_event_type: str | Unset = ''
    selected_from: datetime.datetime | None | Unset = UNSET
    selected_to: datetime.datetime | None | Unset = UNSET





    def to_dict(self) -> dict[str, Any]:
        selected_customer_id: None | str | Unset
        if isinstance(self.selected_customer_id, Unset):
            selected_customer_id = UNSET
        elif isinstance(self.selected_customer_id, UUID):
            selected_customer_id = str(self.selected_customer_id)
        else:
            selected_customer_id = self.selected_customer_id

        selected_event_type = self.selected_event_type

        selected_from: None | str | Unset
        if isinstance(self.selected_from, Unset):
            selected_from = UNSET
        elif isinstance(self.selected_from, datetime.datetime):
            selected_from = self.selected_from.isoformat()
        else:
            selected_from = self.selected_from

        selected_to: None | str | Unset
        if isinstance(self.selected_to, Unset):
            selected_to = UNSET
        elif isinstance(self.selected_to, datetime.datetime):
            selected_to = self.selected_to.isoformat()
        else:
            selected_to = self.selected_to


        field_dict: dict[str, Any] = {}

        field_dict.update({
        })
        if selected_customer_id is not UNSET:
            field_dict["selected_customer_id"] = selected_customer_id
        if selected_event_type is not UNSET:
            field_dict["selected_event_type"] = selected_event_type
        if selected_from is not UNSET:
            field_dict["selected_from"] = selected_from
        if selected_to is not UNSET:
            field_dict["selected_to"] = selected_to

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_selected_customer_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                selected_customer_id_type_0 = UUID(data)



                return selected_customer_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        selected_customer_id = _parse_selected_customer_id(d.pop("selected_customer_id", UNSET))


        selected_event_type = d.pop("selected_event_type", UNSET)

        def _parse_selected_from(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                selected_from_type_0 = datetime.datetime.fromisoformat(data)



                return selected_from_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        selected_from = _parse_selected_from(d.pop("selected_from", UNSET))


        def _parse_selected_to(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                selected_to_type_0 = datetime.datetime.fromisoformat(data)



                return selected_to_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        selected_to = _parse_selected_to(d.pop("selected_to", UNSET))


        resolution_run_in = cls(
            selected_customer_id=selected_customer_id,
            selected_event_type=selected_event_type,
            selected_from=selected_from,
            selected_to=selected_to,
        )

        return resolution_run_in

