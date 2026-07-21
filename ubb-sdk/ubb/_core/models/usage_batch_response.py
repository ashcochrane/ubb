from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.usage_batch_response_results_item import UsageBatchResponseResultsItem





T = TypeVar("T", bound="UsageBatchResponse")



@_attrs_define
class UsageBatchResponse:
    """ 
        Attributes:
            accepted (int):
            rejected (int):
            results (list[UsageBatchResponseResultsItem]):
     """

    accepted: int
    rejected: int
    results: list[UsageBatchResponseResultsItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.usage_batch_response_results_item import UsageBatchResponseResultsItem
        accepted = self.accepted

        rejected = self.rejected

        results = []
        for results_item_data in self.results:
            results_item = results_item_data.to_dict()
            results.append(results_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "accepted": accepted,
            "rejected": rejected,
            "results": results,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.usage_batch_response_results_item import UsageBatchResponseResultsItem
        d = dict(src_dict)
        accepted = d.pop("accepted")

        rejected = d.pop("rejected")

        results = []
        _results = d.pop("results")
        for results_item_data in (_results):
            results_item = UsageBatchResponseResultsItem.from_dict(results_item_data)



            results.append(results_item)


        usage_batch_response = cls(
            accepted=accepted,
            rejected=rejected,
            results=results,
        )


        usage_batch_response.additional_properties = d
        return usage_batch_response

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
