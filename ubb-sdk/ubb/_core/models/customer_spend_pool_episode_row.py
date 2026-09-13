from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.customer_spend_pool_episode_row_control_family import CustomerSpendPoolEpisodeRowControlFamily
from ..types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime

if TYPE_CHECKING:
  from ..models.itemised_events_out import ItemisedEventsOut





T = TypeVar("T", bound="CustomerSpendPoolEpisodeRow")



@_attrs_define
class CustomerSpendPoolEpisodeRow:
    """ A customer spend pool's stop: the customer the pool is declared on,
    the period, the pool amount, THE CHARGE THAT CROSSED IT AND THAT CHARGE'S
    POSTING — never an arbitrary event — the period spend after it as a pair,
    and the outcome: how much active work the stop swept. Starts were
    refused from `opened_at` until `closed_at` (null while the episode is
    still open). `cap_micros` is the pool row as it stands now, null where
    the row is gone. `crossing_marked` says how the charge was found: true
    where the recording route marked the tipping event as it landed, false
    where the drawdown was replayed up to the opening instant against the
    pool's stop line as it stands now — a pool moved since can shift which
    posting the replay names, so a replayed answer is read with that in
    mind; `crossing_*` are null where nothing UBB holds can name the charge
    — never a guess.

        Attributes:
            control_family (CustomerSpendPoolEpisodeRowControlFamily):
            crossing_marked (bool):
            customer_id (UUID):
            episode_seq (int):
            itemised (ItemisedEventsOut): The events an episode itemises and their totals in both denominations
                — each total adding what is resolved and counting what is not, so a row
                can never read complete while its own events read partial.
            opened_at (datetime.datetime):
            period (str):
            reason_code (str):
            spent_after_micros (int):
            unpriced_after_count (int):
            work_stopped_count (int):
            cap_micros (int | None | Unset):
            closed_at (datetime.datetime | None | Unset):
            control_id (None | str | Unset):
            crossing_charge_id (None | Unset | UUID):
            crossing_posting_id (None | Unset | UUID):
     """

    control_family: CustomerSpendPoolEpisodeRowControlFamily
    crossing_marked: bool
    customer_id: UUID
    episode_seq: int
    itemised: ItemisedEventsOut
    opened_at: datetime.datetime
    period: str
    reason_code: str
    spent_after_micros: int
    unpriced_after_count: int
    work_stopped_count: int
    cap_micros: int | None | Unset = UNSET
    closed_at: datetime.datetime | None | Unset = UNSET
    control_id: None | str | Unset = UNSET
    crossing_charge_id: None | Unset | UUID = UNSET
    crossing_posting_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.itemised_events_out import ItemisedEventsOut
        control_family = self.control_family.value

        crossing_marked = self.crossing_marked

        customer_id = str(self.customer_id)

        episode_seq = self.episode_seq

        itemised = self.itemised.to_dict()

        opened_at = self.opened_at.isoformat()

        period = self.period

        reason_code = self.reason_code

        spent_after_micros = self.spent_after_micros

        unpriced_after_count = self.unpriced_after_count

        work_stopped_count = self.work_stopped_count

        cap_micros: int | None | Unset
        if isinstance(self.cap_micros, Unset):
            cap_micros = UNSET
        else:
            cap_micros = self.cap_micros

        closed_at: None | str | Unset
        if isinstance(self.closed_at, Unset):
            closed_at = UNSET
        elif isinstance(self.closed_at, datetime.datetime):
            closed_at = self.closed_at.isoformat()
        else:
            closed_at = self.closed_at

        control_id: None | str | Unset
        if isinstance(self.control_id, Unset):
            control_id = UNSET
        else:
            control_id = self.control_id

        crossing_charge_id: None | str | Unset
        if isinstance(self.crossing_charge_id, Unset):
            crossing_charge_id = UNSET
        elif isinstance(self.crossing_charge_id, UUID):
            crossing_charge_id = str(self.crossing_charge_id)
        else:
            crossing_charge_id = self.crossing_charge_id

        crossing_posting_id: None | str | Unset
        if isinstance(self.crossing_posting_id, Unset):
            crossing_posting_id = UNSET
        elif isinstance(self.crossing_posting_id, UUID):
            crossing_posting_id = str(self.crossing_posting_id)
        else:
            crossing_posting_id = self.crossing_posting_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "control_family": control_family,
            "crossing_marked": crossing_marked,
            "customer_id": customer_id,
            "episode_seq": episode_seq,
            "itemised": itemised,
            "opened_at": opened_at,
            "period": period,
            "reason_code": reason_code,
            "spent_after_micros": spent_after_micros,
            "unpriced_after_count": unpriced_after_count,
            "work_stopped_count": work_stopped_count,
        })
        if cap_micros is not UNSET:
            field_dict["cap_micros"] = cap_micros
        if closed_at is not UNSET:
            field_dict["closed_at"] = closed_at
        if control_id is not UNSET:
            field_dict["control_id"] = control_id
        if crossing_charge_id is not UNSET:
            field_dict["crossing_charge_id"] = crossing_charge_id
        if crossing_posting_id is not UNSET:
            field_dict["crossing_posting_id"] = crossing_posting_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.itemised_events_out import ItemisedEventsOut
        d = dict(src_dict)
        control_family = CustomerSpendPoolEpisodeRowControlFamily(d.pop("control_family"))




        crossing_marked = d.pop("crossing_marked")

        customer_id = UUID(d.pop("customer_id"))




        episode_seq = d.pop("episode_seq")

        itemised = ItemisedEventsOut.from_dict(d.pop("itemised"))




        opened_at = datetime.datetime.fromisoformat(d.pop("opened_at"))




        period = d.pop("period")

        reason_code = d.pop("reason_code")

        spent_after_micros = d.pop("spent_after_micros")

        unpriced_after_count = d.pop("unpriced_after_count")

        work_stopped_count = d.pop("work_stopped_count")

        def _parse_cap_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cap_micros = _parse_cap_micros(d.pop("cap_micros", UNSET))


        def _parse_closed_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                closed_at_type_0 = datetime.datetime.fromisoformat(data)



                return closed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        closed_at = _parse_closed_at(d.pop("closed_at", UNSET))


        def _parse_control_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        control_id = _parse_control_id(d.pop("control_id", UNSET))


        def _parse_crossing_charge_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                crossing_charge_id_type_0 = UUID(data)



                return crossing_charge_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        crossing_charge_id = _parse_crossing_charge_id(d.pop("crossing_charge_id", UNSET))


        def _parse_crossing_posting_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                crossing_posting_id_type_0 = UUID(data)



                return crossing_posting_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        crossing_posting_id = _parse_crossing_posting_id(d.pop("crossing_posting_id", UNSET))


        customer_spend_pool_episode_row = cls(
            control_family=control_family,
            crossing_marked=crossing_marked,
            customer_id=customer_id,
            episode_seq=episode_seq,
            itemised=itemised,
            opened_at=opened_at,
            period=period,
            reason_code=reason_code,
            spent_after_micros=spent_after_micros,
            unpriced_after_count=unpriced_after_count,
            work_stopped_count=work_stopped_count,
            cap_micros=cap_micros,
            closed_at=closed_at,
            control_id=control_id,
            crossing_charge_id=crossing_charge_id,
            crossing_posting_id=crossing_posting_id,
        )


        customer_spend_pool_episode_row.additional_properties = d
        return customer_spend_pool_episode_row

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
