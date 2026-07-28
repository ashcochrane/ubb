from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.plan_out import PlanOut





T = TypeVar("T", bound="PlanListOut")



@_attrs_define
class PlanListOut:
    """ 
        Attributes:
            plans (list[PlanOut]):
     """

    plans: list[PlanOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.plan_out import PlanOut
        plans = []
        for plans_item_data in self.plans:
            plans_item = plans_item_data.to_dict()
            plans.append(plans_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "plans": plans,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.plan_out import PlanOut
        d = dict(src_dict)
        plans = []
        _plans = d.pop("plans")
        for plans_item_data in (_plans):
            plans_item = PlanOut.from_dict(plans_item_data)



            plans.append(plans_item)


        plan_list_out = cls(
            plans=plans,
        )


        plan_list_out.additional_properties = d
        return plan_list_out

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
