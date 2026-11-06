from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.top_up_accepted_response_status import TopUpAcceptedResponseStatus






T = TypeVar("T", bound="TopUpAcceptedResponse")



@_attrs_define
class TopUpAcceptedResponse:
    """ The 202 answer of both top-up routes (the tenant's and `/me`'s) when
    the tenant has no Stripe connector to open a checkout for: the request
    was recorded and handed to the tenant to settle out of band
    (`top_up.requested`). A replay of the same `idempotency_key` answers this
    again without a second event. `status` is the registry's closed
    `top_up_request_status`; today it carries its one value.

        Attributes:
            message (str):
            status (TopUpAcceptedResponseStatus): The one value a 202 carries: the top-up request was recorded and handed to
                the tenant; no checkout was opened.
     """

    message: str
    status: TopUpAcceptedResponseStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        message = self.message

        status = self.status.value


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "message": message,
            "status": status,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        status = TopUpAcceptedResponseStatus(d.pop("status"))




        top_up_accepted_response = cls(
            message=message,
            status=status,
        )


        top_up_accepted_response.additional_properties = d
        return top_up_accepted_response

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
