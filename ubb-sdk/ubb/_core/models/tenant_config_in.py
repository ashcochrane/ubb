from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.tenant_config_in_products_type_0_item import TenantConfigInProductsType0Item
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="TenantConfigIn")



@_attrs_define
class TenantConfigIn:
    """ 
        Attributes:
            automatic_tax_enabled (bool | None | Unset):
            billing_mode (None | str | Unset):
            default_currency (None | str | Unset):
            default_task_provider_cost_limit_micros (int | None | Unset):
            enforcement_mode (None | str | Unset):
            live_counter_maintenance_enabled (bool | None | Unset):
            min_balance_micros (int | None | Unset):
            products (list[TenantConfigInProductsType0Item] | None | Unset):
            soft_min_balance_micros (int | None | Unset):
     """

    automatic_tax_enabled: bool | None | Unset = UNSET
    billing_mode: None | str | Unset = UNSET
    default_currency: None | str | Unset = UNSET
    default_task_provider_cost_limit_micros: int | None | Unset = UNSET
    enforcement_mode: None | str | Unset = UNSET
    live_counter_maintenance_enabled: bool | None | Unset = UNSET
    min_balance_micros: int | None | Unset = UNSET
    products: list[TenantConfigInProductsType0Item] | None | Unset = UNSET
    soft_min_balance_micros: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        automatic_tax_enabled: bool | None | Unset
        if isinstance(self.automatic_tax_enabled, Unset):
            automatic_tax_enabled = UNSET
        else:
            automatic_tax_enabled = self.automatic_tax_enabled

        billing_mode: None | str | Unset
        if isinstance(self.billing_mode, Unset):
            billing_mode = UNSET
        else:
            billing_mode = self.billing_mode

        default_currency: None | str | Unset
        if isinstance(self.default_currency, Unset):
            default_currency = UNSET
        else:
            default_currency = self.default_currency

        default_task_provider_cost_limit_micros: int | None | Unset
        if isinstance(self.default_task_provider_cost_limit_micros, Unset):
            default_task_provider_cost_limit_micros = UNSET
        else:
            default_task_provider_cost_limit_micros = self.default_task_provider_cost_limit_micros

        enforcement_mode: None | str | Unset
        if isinstance(self.enforcement_mode, Unset):
            enforcement_mode = UNSET
        else:
            enforcement_mode = self.enforcement_mode

        live_counter_maintenance_enabled: bool | None | Unset
        if isinstance(self.live_counter_maintenance_enabled, Unset):
            live_counter_maintenance_enabled = UNSET
        else:
            live_counter_maintenance_enabled = self.live_counter_maintenance_enabled

        min_balance_micros: int | None | Unset
        if isinstance(self.min_balance_micros, Unset):
            min_balance_micros = UNSET
        else:
            min_balance_micros = self.min_balance_micros

        products: list[str] | None | Unset
        if isinstance(self.products, Unset):
            products = UNSET
        elif isinstance(self.products, list):
            products = []
            for products_type_0_item_data in self.products:
                products_type_0_item = products_type_0_item_data.value
                products.append(products_type_0_item)


        else:
            products = self.products

        soft_min_balance_micros: int | None | Unset
        if isinstance(self.soft_min_balance_micros, Unset):
            soft_min_balance_micros = UNSET
        else:
            soft_min_balance_micros = self.soft_min_balance_micros


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if automatic_tax_enabled is not UNSET:
            field_dict["automatic_tax_enabled"] = automatic_tax_enabled
        if billing_mode is not UNSET:
            field_dict["billing_mode"] = billing_mode
        if default_currency is not UNSET:
            field_dict["default_currency"] = default_currency
        if default_task_provider_cost_limit_micros is not UNSET:
            field_dict["default_task_provider_cost_limit_micros"] = default_task_provider_cost_limit_micros
        if enforcement_mode is not UNSET:
            field_dict["enforcement_mode"] = enforcement_mode
        if live_counter_maintenance_enabled is not UNSET:
            field_dict["live_counter_maintenance_enabled"] = live_counter_maintenance_enabled
        if min_balance_micros is not UNSET:
            field_dict["min_balance_micros"] = min_balance_micros
        if products is not UNSET:
            field_dict["products"] = products
        if soft_min_balance_micros is not UNSET:
            field_dict["soft_min_balance_micros"] = soft_min_balance_micros

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_automatic_tax_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        automatic_tax_enabled = _parse_automatic_tax_enabled(d.pop("automatic_tax_enabled", UNSET))


        def _parse_billing_mode(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        billing_mode = _parse_billing_mode(d.pop("billing_mode", UNSET))


        def _parse_default_currency(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        default_currency = _parse_default_currency(d.pop("default_currency", UNSET))


        def _parse_default_task_provider_cost_limit_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        default_task_provider_cost_limit_micros = _parse_default_task_provider_cost_limit_micros(d.pop("default_task_provider_cost_limit_micros", UNSET))


        def _parse_enforcement_mode(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        enforcement_mode = _parse_enforcement_mode(d.pop("enforcement_mode", UNSET))


        def _parse_live_counter_maintenance_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        live_counter_maintenance_enabled = _parse_live_counter_maintenance_enabled(d.pop("live_counter_maintenance_enabled", UNSET))


        def _parse_min_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_balance_micros = _parse_min_balance_micros(d.pop("min_balance_micros", UNSET))


        def _parse_products(data: object) -> list[TenantConfigInProductsType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                products_type_0 = []
                _products_type_0 = data
                for products_type_0_item_data in (_products_type_0):
                    products_type_0_item = TenantConfigInProductsType0Item(products_type_0_item_data)



                    products_type_0.append(products_type_0_item)

                return products_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[TenantConfigInProductsType0Item] | None | Unset, data)

        products = _parse_products(d.pop("products", UNSET))


        def _parse_soft_min_balance_micros(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        soft_min_balance_micros = _parse_soft_min_balance_micros(d.pop("soft_min_balance_micros", UNSET))


        tenant_config_in = cls(
            automatic_tax_enabled=automatic_tax_enabled,
            billing_mode=billing_mode,
            default_currency=default_currency,
            default_task_provider_cost_limit_micros=default_task_provider_cost_limit_micros,
            enforcement_mode=enforcement_mode,
            live_counter_maintenance_enabled=live_counter_maintenance_enabled,
            min_balance_micros=min_balance_micros,
            products=products,
            soft_min_balance_micros=soft_min_balance_micros,
        )


        tenant_config_in.additional_properties = d
        return tenant_config_in

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
