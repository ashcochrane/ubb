from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TenantConfigOut")



@_attrs_define
class TenantConfigOut:
    """ 
        Attributes:
            automatic_tax_enabled (bool):
            billing_mode (str):
            default_currency (str):
            is_active (bool):
            name (str):
            products (list[str]):
            require_cost_card_coverage (bool):
            stripe_connected_account_id (str):
            arrival_signals_enabled (bool | Unset):  Default: True.
            default_task_floor_snapshot_micros (int | None | Unset):
            default_task_provider_cost_limit_micros (int | None | Unset):
            enforcement_mode (str | Unset):  Default: 'off'.
            min_balance_micros (int | Unset):  Default: 0.
            soft_min_balance_micros (int | None | Unset):
     """

    automatic_tax_enabled: bool
    billing_mode: str
    default_currency: str
    is_active: bool
    name: str
    products: list[str]
    require_cost_card_coverage: bool
    stripe_connected_account_id: str
    arrival_signals_enabled: bool | Unset = True
    default_task_floor_snapshot_micros: int | None | Unset = UNSET
    default_task_provider_cost_limit_micros: int | None | Unset = UNSET
    enforcement_mode: str | Unset = 'off'
    min_balance_micros: int | Unset = 0
    soft_min_balance_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        automatic_tax_enabled = self.automatic_tax_enabled

        billing_mode = self.billing_mode

        default_currency = self.default_currency

        is_active = self.is_active

        name = self.name

        products = self.products



        require_cost_card_coverage = self.require_cost_card_coverage

        stripe_connected_account_id = self.stripe_connected_account_id

        arrival_signals_enabled = self.arrival_signals_enabled

        default_task_floor_snapshot_micros: int | None | Unset
        if isinstance(self.default_task_floor_snapshot_micros, Unset):
            default_task_floor_snapshot_micros = UNSET
        else:
            default_task_floor_snapshot_micros = self.default_task_floor_snapshot_micros

        default_task_provider_cost_limit_micros: int | None | Unset
        if isinstance(self.default_task_provider_cost_limit_micros, Unset):
            default_task_provider_cost_limit_micros = UNSET
        else:
            default_task_provider_cost_limit_micros = self.default_task_provider_cost_limit_micros

        enforcement_mode = self.enforcement_mode

        min_balance_micros = self.min_balance_micros

        soft_min_balance_micros: int | None | Unset
        if isinstance(self.soft_min_balance_micros, Unset):
            soft_min_balance_micros = UNSET
        else:
            soft_min_balance_micros = self.soft_min_balance_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "automatic_tax_enabled": automatic_tax_enabled,
            "billing_mode": billing_mode,
            "default_currency": default_currency,
            "is_active": is_active,
            "name": name,
            "products": products,
            "require_cost_card_coverage": require_cost_card_coverage,
            "stripe_connected_account_id": stripe_connected_account_id,
        })
        if arrival_signals_enabled is not UNSET:
            field_dict["arrival_signals_enabled"] = arrival_signals_enabled
        if default_task_floor_snapshot_micros is not UNSET:
            field_dict["default_task_floor_snapshot_micros"] = default_task_floor_snapshot_micros
        if default_task_provider_cost_limit_micros is not UNSET:
            field_dict["default_task_provider_cost_limit_micros"] = default_task_provider_cost_limit_micros
        if enforcement_mode is not UNSET:
            field_dict["enforcement_mode"] = enforcement_mode
        if min_balance_micros is not UNSET:
            field_dict["min_balance_micros"] = min_balance_micros
        if soft_min_balance_micros is not UNSET:
            field_dict["soft_min_balance_micros"] = soft_min_balance_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        automatic_tax_enabled = d.pop("automatic_tax_enabled")

        billing_mode = d.pop("billing_mode")

        default_currency = d.pop("default_currency")

        is_active = d.pop("is_active")

        name = d.pop("name")

        products = cast(list[str], d.pop("products"))


        require_cost_card_coverage = d.pop("require_cost_card_coverage")

        stripe_connected_account_id = d.pop("stripe_connected_account_id")

        arrival_signals_enabled = d.pop("arrival_signals_enabled", UNSET)

        def _parse_default_task_floor_snapshot_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        default_task_floor_snapshot_micros = _parse_default_task_floor_snapshot_micros(d.pop("default_task_floor_snapshot_micros", UNSET))


        def _parse_default_task_provider_cost_limit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        default_task_provider_cost_limit_micros = _parse_default_task_provider_cost_limit_micros(d.pop("default_task_provider_cost_limit_micros", UNSET))


        enforcement_mode = d.pop("enforcement_mode", UNSET)

        min_balance_micros = d.pop("min_balance_micros", UNSET)

        def _parse_soft_min_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        soft_min_balance_micros = _parse_soft_min_balance_micros(d.pop("soft_min_balance_micros", UNSET))


        tenant_config_out = cls(
            automatic_tax_enabled=automatic_tax_enabled,
            billing_mode=billing_mode,
            default_currency=default_currency,
            is_active=is_active,
            name=name,
            products=products,
            require_cost_card_coverage=require_cost_card_coverage,
            stripe_connected_account_id=stripe_connected_account_id,
            arrival_signals_enabled=arrival_signals_enabled,
            default_task_floor_snapshot_micros=default_task_floor_snapshot_micros,
            default_task_provider_cost_limit_micros=default_task_provider_cost_limit_micros,
            enforcement_mode=enforcement_mode,
            min_balance_micros=min_balance_micros,
            soft_min_balance_micros=soft_min_balance_micros,
        )


        tenant_config_out.additional_properties = d
        return tenant_config_out

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
