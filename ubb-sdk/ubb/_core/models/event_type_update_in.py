from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.event_type_update_in_costing_method_type_0 import EventTypeUpdateInCostingMethodType0
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="EventTypeUpdateIn")



@_attrs_define
class EventTypeUpdateIn:
    """ Every field optional: an absent field is untouched, not cleared.

    The two satellites detach on an EMPTY STRING rather than on a null, which
    is the one place this shape has to be explicit: "no supplier" is a state a
    tenant reaches deliberately, and a null that meant "leave alone" would
    leave them no way to say it.

    **The key is absent on purpose.** It is the name a tenant's own recorded
    events arrive under, so renaming one would silently re-point every posting
    made against it — the same objection that keeps supplier cost resolution on
    the Provider's identity rather than on its handle, arriving at the opposite
    answer because here the handle IS the identity. Withdraw and re-declare, or
    map the old name through the quarantine that already exists for a name UBB
    does not recognise.

        Attributes:
            category_key (None | str | Unset):
            costing_method (EventTypeUpdateInCostingMethodType0 | None | Unset):
            provider_key (None | str | Unset):
            source_shape_id (None | str | Unset):
            source_shape_label (None | str | Unset):
     """

    category_key: None | str | Unset = UNSET
    costing_method: EventTypeUpdateInCostingMethodType0 | None | Unset = UNSET
    provider_key: None | str | Unset = UNSET
    source_shape_id: None | str | Unset = UNSET
    source_shape_label: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        category_key: None | str | Unset
        if isinstance(self.category_key, Unset):
            category_key = UNSET
        else:
            category_key = self.category_key

        costing_method: None | str | Unset
        if isinstance(self.costing_method, Unset):
            costing_method = UNSET
        elif isinstance(self.costing_method, EventTypeUpdateInCostingMethodType0):
            costing_method = self.costing_method.value
        else:
            costing_method = self.costing_method

        provider_key: None | str | Unset
        if isinstance(self.provider_key, Unset):
            provider_key = UNSET
        else:
            provider_key = self.provider_key

        source_shape_id: None | str | Unset
        if isinstance(self.source_shape_id, Unset):
            source_shape_id = UNSET
        else:
            source_shape_id = self.source_shape_id

        source_shape_label: None | str | Unset
        if isinstance(self.source_shape_label, Unset):
            source_shape_label = UNSET
        else:
            source_shape_label = self.source_shape_label


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if category_key is not UNSET:
            field_dict["category_key"] = category_key
        if costing_method is not UNSET:
            field_dict["costing_method"] = costing_method
        if provider_key is not UNSET:
            field_dict["provider_key"] = provider_key
        if source_shape_id is not UNSET:
            field_dict["source_shape_id"] = source_shape_id
        if source_shape_label is not UNSET:
            field_dict["source_shape_label"] = source_shape_label

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_category_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        category_key = _parse_category_key(d.pop("category_key", UNSET))


        def _parse_costing_method(data: object) -> EventTypeUpdateInCostingMethodType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                costing_method_type_0 = EventTypeUpdateInCostingMethodType0(data)



                return costing_method_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(EventTypeUpdateInCostingMethodType0 | None | Unset, data)

        costing_method = _parse_costing_method(d.pop("costing_method", UNSET))


        def _parse_provider_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_key = _parse_provider_key(d.pop("provider_key", UNSET))


        def _parse_source_shape_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source_shape_id = _parse_source_shape_id(d.pop("source_shape_id", UNSET))


        def _parse_source_shape_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source_shape_label = _parse_source_shape_label(d.pop("source_shape_label", UNSET))


        event_type_update_in = cls(
            category_key=category_key,
            costing_method=costing_method,
            provider_key=provider_key,
            source_shape_id=source_shape_id,
            source_shape_label=source_shape_label,
        )


        event_type_update_in.additional_properties = d
        return event_type_update_in

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
