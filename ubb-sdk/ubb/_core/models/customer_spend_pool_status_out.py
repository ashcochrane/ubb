from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.customer_spend_pool_status_out_enforce_mode import CustomerSpendPoolStatusOutEnforceMode
from typing import cast






T = TypeVar("T", bound="CustomerSpendPoolStatusOut")



@_attrs_define
class CustomerSpendPoolStatusOut:
    """ Where a customer's known period charges stand against the pool that
    applies to them — their own row, else the tenant default; no row is no
    pool (`cap_micros` 0, every assessed figure null). The basis is the
    durable pair: `known_period_charges_micros` is the resolved period
    charges and a LOWER BOUND wherever `unresolved_posting_count` is not
    zero, and every figure beside it is computed over that known figure —
    the percentage a floor and the headroom a ceiling until the count is
    zero. `highest_threshold_reached` is the largest of the pool's
    `alert_levels` (a percent of `cap_micros`) the known figure has reached;
    `blocking_occurred` is the start gate's own compare — true only under a
    blocking pool whose stop line the known figure is at or over. The pool
    is blind to a fixed price until delivery; the wallet reservation sees it
    at start.

        Attributes:
            blocking_occurred (bool):
            cap_micros (int):
            enforce_mode (CustomerSpendPoolStatusOutEnforceMode):
            highest_threshold_reached (int | None):
            known_period_charges_micros (int):
            period (str):
            remaining_micros (int | None):
            unresolved_posting_count (int):
            used_percentage (int | None):
     """

    blocking_occurred: bool
    cap_micros: int
    enforce_mode: CustomerSpendPoolStatusOutEnforceMode
    highest_threshold_reached: int | None
    known_period_charges_micros: int
    period: str
    remaining_micros: int | None
    unresolved_posting_count: int
    used_percentage: int | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        blocking_occurred = self.blocking_occurred

        cap_micros = self.cap_micros

        enforce_mode = self.enforce_mode.value

        highest_threshold_reached: int | None
        highest_threshold_reached = self.highest_threshold_reached

        known_period_charges_micros = self.known_period_charges_micros

        period = self.period

        remaining_micros: int | None
        remaining_micros = self.remaining_micros

        unresolved_posting_count = self.unresolved_posting_count

        used_percentage: int | None
        used_percentage = self.used_percentage


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "blocking_occurred": blocking_occurred,
            "cap_micros": cap_micros,
            "enforce_mode": enforce_mode,
            "highest_threshold_reached": highest_threshold_reached,
            "known_period_charges_micros": known_period_charges_micros,
            "period": period,
            "remaining_micros": remaining_micros,
            "unresolved_posting_count": unresolved_posting_count,
            "used_percentage": used_percentage,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        blocking_occurred = d.pop("blocking_occurred")

        cap_micros = d.pop("cap_micros")

        enforce_mode = CustomerSpendPoolStatusOutEnforceMode(d.pop("enforce_mode"))




        def _parse_highest_threshold_reached(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        highest_threshold_reached = _parse_highest_threshold_reached(d.pop("highest_threshold_reached"))


        known_period_charges_micros = d.pop("known_period_charges_micros")

        period = d.pop("period")

        def _parse_remaining_micros(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        remaining_micros = _parse_remaining_micros(d.pop("remaining_micros"))


        unresolved_posting_count = d.pop("unresolved_posting_count")

        def _parse_used_percentage(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        used_percentage = _parse_used_percentage(d.pop("used_percentage"))


        customer_spend_pool_status_out = cls(
            blocking_occurred=blocking_occurred,
            cap_micros=cap_micros,
            enforce_mode=enforce_mode,
            highest_threshold_reached=highest_threshold_reached,
            known_period_charges_micros=known_period_charges_micros,
            period=period,
            remaining_micros=remaining_micros,
            unresolved_posting_count=unresolved_posting_count,
            used_percentage=used_percentage,
        )


        customer_spend_pool_status_out.additional_properties = d
        return customer_spend_pool_status_out

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
