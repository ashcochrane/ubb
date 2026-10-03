from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.problem_out import ProblemOut





T = TypeVar("T", bound="IntegrationBlueprintVerificationRefusal")



@_attrs_define
class IntegrationBlueprintVerificationRefusal:
    """ A call of the run that was refused, which is where the run stopped.

        Attributes:
            operation_id (str):
            problem (ProblemOut): RFC 9457 problem+json, for ``response=`` documentation of error
                statuses. Extension members (e.g. ``balance_micros``) are open-world and
                deliberately unmodeled.
     """

    operation_id: str
    problem: ProblemOut
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.problem_out import ProblemOut
        operation_id = self.operation_id

        problem = self.problem.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "operation_id": operation_id,
            "problem": problem,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.problem_out import ProblemOut
        d = dict(src_dict)
        operation_id = d.pop("operation_id")

        problem = ProblemOut.from_dict(d.pop("problem"))




        integration_blueprint_verification_refusal = cls(
            operation_id=operation_id,
            problem=problem,
        )


        integration_blueprint_verification_refusal.additional_properties = d
        return integration_blueprint_verification_refusal

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
