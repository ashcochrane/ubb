from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.wallet_policy_episode_row_control_family import WalletPolicyEpisodeRowControlFamily
from ..types import UNSET, Unset
from typing import cast
from uuid import UUID
import datetime

if TYPE_CHECKING:
  from ..models.itemised_events_out import ItemisedEventsOut





T = TypeVar("T", bound="WalletPolicyEpisodeRow")



@_attrs_define
class WalletPolicyEpisodeRow:
    """ A wallet policy's episode. A hard-floor episode stopped the customer:
    the floor, the balance at crossing (as the suspension announced it, null
    where none was), the open and close, and the events itemised into it. A
    soft-floor row (`soft_floor` true) is a marker with no events, no stop
    word and no control: the wind-down line stops nothing. `floor_micros` is
    the hard floor as its control row carries it now; the soft floor's is
    the figure the crossing announced.

        Attributes:
            control_family (WalletPolicyEpisodeRowControlFamily):
            customer_id (UUID):
            episode_seq (int):
            itemised (ItemisedEventsOut): The events an episode itemises and their totals in both denominations
                — each total adding what is resolved and counting what is not, so a row
                can never read complete while its own events read partial.
            opened_at (datetime.datetime):
            soft_floor (bool):
            balance_at_crossing_micros (int | None | Unset):
            closed_at (datetime.datetime | None | Unset):
            control_id (None | str | Unset):
            floor_micros (int | None | Unset):
            reason_code (None | str | Unset):
     """

    control_family: WalletPolicyEpisodeRowControlFamily
    customer_id: UUID
    episode_seq: int
    itemised: ItemisedEventsOut
    opened_at: datetime.datetime
    soft_floor: bool
    balance_at_crossing_micros: int | None | Unset = UNSET
    closed_at: datetime.datetime | None | Unset = UNSET
    control_id: None | str | Unset = UNSET
    floor_micros: int | None | Unset = UNSET
    reason_code: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.itemised_events_out import ItemisedEventsOut
        control_family = self.control_family.value

        customer_id = str(self.customer_id)

        episode_seq = self.episode_seq

        itemised = self.itemised.to_dict()

        opened_at = self.opened_at.isoformat()

        soft_floor = self.soft_floor

        balance_at_crossing_micros: int | None | Unset
        if isinstance(self.balance_at_crossing_micros, Unset):
            balance_at_crossing_micros = UNSET
        else:
            balance_at_crossing_micros = self.balance_at_crossing_micros

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

        floor_micros: int | None | Unset
        if isinstance(self.floor_micros, Unset):
            floor_micros = UNSET
        else:
            floor_micros = self.floor_micros

        reason_code: None | str | Unset
        if isinstance(self.reason_code, Unset):
            reason_code = UNSET
        else:
            reason_code = self.reason_code


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "control_family": control_family,
            "customer_id": customer_id,
            "episode_seq": episode_seq,
            "itemised": itemised,
            "opened_at": opened_at,
            "soft_floor": soft_floor,
        })
        if balance_at_crossing_micros is not UNSET:
            field_dict["balance_at_crossing_micros"] = balance_at_crossing_micros
        if closed_at is not UNSET:
            field_dict["closed_at"] = closed_at
        if control_id is not UNSET:
            field_dict["control_id"] = control_id
        if floor_micros is not UNSET:
            field_dict["floor_micros"] = floor_micros
        if reason_code is not UNSET:
            field_dict["reason_code"] = reason_code

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.itemised_events_out import ItemisedEventsOut
        d = dict(src_dict)
        control_family = WalletPolicyEpisodeRowControlFamily(d.pop("control_family"))




        customer_id = UUID(d.pop("customer_id"))




        episode_seq = d.pop("episode_seq")

        itemised = ItemisedEventsOut.from_dict(d.pop("itemised"))




        opened_at = datetime.datetime.fromisoformat(d.pop("opened_at"))




        soft_floor = d.pop("soft_floor")

        def _parse_balance_at_crossing_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        balance_at_crossing_micros = _parse_balance_at_crossing_micros(d.pop("balance_at_crossing_micros", UNSET))


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


        def _parse_floor_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        floor_micros = _parse_floor_micros(d.pop("floor_micros", UNSET))


        def _parse_reason_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason_code = _parse_reason_code(d.pop("reason_code", UNSET))


        wallet_policy_episode_row = cls(
            control_family=control_family,
            customer_id=customer_id,
            episode_seq=episode_seq,
            itemised=itemised,
            opened_at=opened_at,
            soft_floor=soft_floor,
            balance_at_crossing_micros=balance_at_crossing_micros,
            closed_at=closed_at,
            control_id=control_id,
            floor_micros=floor_micros,
            reason_code=reason_code,
        )


        wallet_policy_episode_row.additional_properties = d
        return wallet_policy_episode_row

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
