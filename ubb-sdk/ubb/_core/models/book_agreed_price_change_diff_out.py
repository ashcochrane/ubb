from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast
from typing import Literal, cast

if TYPE_CHECKING:
  from ..models.agreed_price_terms_out import AgreedPriceTermsOut





T = TypeVar("T", bound="BookAgreedPriceChangeDiffOut")



@_attrs_define
class BookAgreedPriceChangeDiffOut:
    """ One row of the diff for an agreed price: which kind of work, and what
    happens to its price.

    `line` is `agreed_price`. `before` is the agreed price in force at the
    publish's effective instant and is null where the change adds one;
    `after` is the one the publish opens and is null where the change retires
    one.

        Attributes:
            after (AgreedPriceTermsOut | None):
            before (AgreedPriceTermsOut | None):
            kind (str):
            line (Literal['agreed_price']):
            task_type (str):
     """

    after: AgreedPriceTermsOut | None
    before: AgreedPriceTermsOut | None
    kind: str
    line: Literal['agreed_price']
    task_type: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.agreed_price_terms_out import AgreedPriceTermsOut
        after: dict[str, Any] | None
        if isinstance(self.after, AgreedPriceTermsOut):
            after = self.after.to_dict()
        else:
            after = self.after

        before: dict[str, Any] | None
        if isinstance(self.before, AgreedPriceTermsOut):
            before = self.before.to_dict()
        else:
            before = self.before

        kind = self.kind

        line = self.line

        task_type = self.task_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "after": after,
            "before": before,
            "kind": kind,
            "line": line,
            "task_type": task_type,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agreed_price_terms_out import AgreedPriceTermsOut
        d = dict(src_dict)
        def _parse_after(data: object) -> AgreedPriceTermsOut | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                after_type_0 = AgreedPriceTermsOut.from_dict(data)



                return after_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgreedPriceTermsOut | None, data)

        after = _parse_after(d.pop("after"))


        def _parse_before(data: object) -> AgreedPriceTermsOut | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                before_type_0 = AgreedPriceTermsOut.from_dict(data)



                return before_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgreedPriceTermsOut | None, data)

        before = _parse_before(d.pop("before"))


        kind = d.pop("kind")

        line = cast(Literal['agreed_price'] , d.pop("line"))
        if line != 'agreed_price':
            raise ValueError(f"line must match const 'agreed_price', got '{line}'")

        task_type = d.pop("task_type")

        book_agreed_price_change_diff_out = cls(
            after=after,
            before=before,
            kind=kind,
            line=line,
            task_type=task_type,
        )


        book_agreed_price_change_diff_out.additional_properties = d
        return book_agreed_price_change_diff_out

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
