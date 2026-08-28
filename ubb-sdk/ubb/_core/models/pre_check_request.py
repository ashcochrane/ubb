from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID






T = TypeVar("T", bound="PreCheckRequest")



@_attrs_define
class PreCheckRequest:
    """ ADVISORY ONLY — THIS CALL REGISTERS NOTHING (#410).

    It used to, behind a flag, and every field that served the flag has gone
    with it: registering a unit of work is now its own call, `POST
    /api/v1/tasks`, at the root and behind no product gate. A money-shaped
    admission check and the registration of a unit of work were one call
    answering two questions, and a metering-only tenant could not reach the
    second because the first sat behind billing.

        Attributes:
            customer_id (UUID):
            parent_task_id (None | Unset | UUID):
     """

    customer_id: UUID
    parent_task_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        customer_id = str(self.customer_id)

        parent_task_id: None | str | Unset
        if isinstance(self.parent_task_id, Unset):
            parent_task_id = UNSET
        elif isinstance(self.parent_task_id, UUID):
            parent_task_id = str(self.parent_task_id)
        else:
            parent_task_id = self.parent_task_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "customer_id": customer_id,
        })
        if parent_task_id is not UNSET:
            field_dict["parent_task_id"] = parent_task_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        customer_id = UUID(d.pop("customer_id"))




        def _parse_parent_task_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                parent_task_id_type_0 = UUID(data)



                return parent_task_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        parent_task_id = _parse_parent_task_id(d.pop("parent_task_id", UNSET))


        pre_check_request = cls(
            customer_id=customer_id,
            parent_task_id=parent_task_id,
        )


        pre_check_request.additional_properties = d
        return pre_check_request

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
