from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.resolution_run_selector_out import ResolutionRunSelectorOut





T = TypeVar("T", bound="ResolutionRunOut")



@_attrs_define
class ResolutionRunOut:
    """ What one run reached, and what it completed.

    `postings_examined` is how many never-resolved postings the run took up, and
    the three numbers under it account for all of them: a cost settled, a price
    resolved, or nothing — because nothing the tenant has since configured
    resolves that posting at the instant it happened. A posting can appear in
    both of the first two, so they do not sum to the total.

    `more_to_do` says the selector matched more postings than one run takes.
    Send the same body again: everything this run completed has left the set it
    selects from, so the next run continues where this one stopped.

    A run moves no money. It completes what was never resolved and records that
    it did; no invoice, credit note, charge or refund follows from one.

        Attributes:
            actor_display (str):
            actor_id (str):
            actor_kind (str):
            costs_settled (int):
            executed_at (str):
            id (str):
            more_to_do (bool):
            postings_examined (int):
            postings_left_unresolved (int):
            prices_resolved (int):
            selector (ResolutionRunSelectorOut): The three axes, as they were stated — echoed so the record of the act and
                the answer to the request cannot describe the same run differently.
     """

    actor_display: str
    actor_id: str
    actor_kind: str
    costs_settled: int
    executed_at: str
    id: str
    more_to_do: bool
    postings_examined: int
    postings_left_unresolved: int
    prices_resolved: int
    selector: ResolutionRunSelectorOut
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.resolution_run_selector_out import ResolutionRunSelectorOut
        actor_display = self.actor_display

        actor_id = self.actor_id

        actor_kind = self.actor_kind

        costs_settled = self.costs_settled

        executed_at = self.executed_at

        id = self.id

        more_to_do = self.more_to_do

        postings_examined = self.postings_examined

        postings_left_unresolved = self.postings_left_unresolved

        prices_resolved = self.prices_resolved

        selector = self.selector.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "actor_display": actor_display,
            "actor_id": actor_id,
            "actor_kind": actor_kind,
            "costs_settled": costs_settled,
            "executed_at": executed_at,
            "id": id,
            "more_to_do": more_to_do,
            "postings_examined": postings_examined,
            "postings_left_unresolved": postings_left_unresolved,
            "prices_resolved": prices_resolved,
            "selector": selector,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.resolution_run_selector_out import ResolutionRunSelectorOut
        d = dict(src_dict)
        actor_display = d.pop("actor_display")

        actor_id = d.pop("actor_id")

        actor_kind = d.pop("actor_kind")

        costs_settled = d.pop("costs_settled")

        executed_at = d.pop("executed_at")

        id = d.pop("id")

        more_to_do = d.pop("more_to_do")

        postings_examined = d.pop("postings_examined")

        postings_left_unresolved = d.pop("postings_left_unresolved")

        prices_resolved = d.pop("prices_resolved")

        selector = ResolutionRunSelectorOut.from_dict(d.pop("selector"))




        resolution_run_out = cls(
            actor_display=actor_display,
            actor_id=actor_id,
            actor_kind=actor_kind,
            costs_settled=costs_settled,
            executed_at=executed_at,
            id=id,
            more_to_do=more_to_do,
            postings_examined=postings_examined,
            postings_left_unresolved=postings_left_unresolved,
            prices_resolved=prices_resolved,
            selector=selector,
        )


        resolution_run_out.additional_properties = d
        return resolution_run_out

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
