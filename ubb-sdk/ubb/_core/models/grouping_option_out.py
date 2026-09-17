from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.grouping_option_out_kind import GroupingOptionOutKind
from ..models.grouping_option_out_rollup_type_0 import GroupingOptionOutRollupType0
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.unsupported_measure_out import UnsupportedMeasureOut





T = TypeVar("T", bound="GroupingOptionOut")



@_attrs_define
class GroupingOptionOut:
    """ One axis this tenant may group by.

    Every field's reason is at `apps/metering/queries.py::grouping_options`,
    which computes the row; two are worth repeating at the wire because they are
    what a reader of the CONTRACT will otherwise misread.

    ``label`` is empty on most rows and that is a rule, not a gap: it carries
    the TENANT's own word, and never UBB's for its own axes. The registry owns
    identity and the surface that renders an axis owns its expression (ADR-0008
    §4), so a client supplies its own wording for the axes UBB reserves and for
    the rollups, in whatever language it presents. What UBB must not do is
    derive English from its own token and publish it here as though somebody
    had chosen it.

    ``max_cardinality`` is the cap the tenant declared, null where UBB owns the
    axis. It is published because §7 makes cardinality one of the three things a
    request is validated against — but nothing refuses on it HERE; the surfaces
    that can count the rows a request would produce decide with it.

        Attributes:
            key (str):
            kind (GroupingOptionOutKind):
            label (str):
            source_grain (str): The grain this axis's value is constant at: 'event', 'task' or 'subtask' for a declared
                field — the scope it was declared with — and 'measurement' for an axis that groups the quantities beneath an
                event rather than the event itself.
            supported_surfaces (list[str]): Where this axis may be used: 'analytics' for the economic query, 'invoice_lines'
                for the grouping a tenant's invoice lines are built on. An axis resolving at the measurement grain is analytics-
                only, because an invoice line is money and UBB holds no money at that grain.
            unsupported_measures (list[UnsupportedMeasureOut]):
            max_cardinality (int | None | Unset):
            rollup (GroupingOptionOutRollupType0 | None | Unset):
     """

    key: str
    kind: GroupingOptionOutKind
    label: str
    source_grain: str
    supported_surfaces: list[str]
    unsupported_measures: list[UnsupportedMeasureOut]
    max_cardinality: int | None | Unset = UNSET
    rollup: GroupingOptionOutRollupType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.unsupported_measure_out import UnsupportedMeasureOut
        key = self.key

        kind = self.kind.value

        label = self.label

        source_grain = self.source_grain

        supported_surfaces = self.supported_surfaces



        unsupported_measures = []
        for unsupported_measures_item_data in self.unsupported_measures:
            unsupported_measures_item = unsupported_measures_item_data.to_dict()
            unsupported_measures.append(unsupported_measures_item)



        max_cardinality: int | None | Unset
        if isinstance(self.max_cardinality, Unset):
            max_cardinality = UNSET
        else:
            max_cardinality = self.max_cardinality

        rollup: None | str | Unset
        if isinstance(self.rollup, Unset):
            rollup = UNSET
        elif isinstance(self.rollup, GroupingOptionOutRollupType0):
            rollup = self.rollup.value
        else:
            rollup = self.rollup


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "key": key,
            "kind": kind,
            "label": label,
            "source_grain": source_grain,
            "supported_surfaces": supported_surfaces,
            "unsupported_measures": unsupported_measures,
        })
        if max_cardinality is not UNSET:
            field_dict["max_cardinality"] = max_cardinality
        if rollup is not UNSET:
            field_dict["rollup"] = rollup

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.unsupported_measure_out import UnsupportedMeasureOut
        d = dict(src_dict)
        key = d.pop("key")

        kind = GroupingOptionOutKind(d.pop("kind"))




        label = d.pop("label")

        source_grain = d.pop("source_grain")

        supported_surfaces = cast(list[str], d.pop("supported_surfaces"))


        unsupported_measures = []
        _unsupported_measures = d.pop("unsupported_measures")
        for unsupported_measures_item_data in (_unsupported_measures):
            unsupported_measures_item = UnsupportedMeasureOut.from_dict(unsupported_measures_item_data)



            unsupported_measures.append(unsupported_measures_item)


        def _parse_max_cardinality(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_cardinality = _parse_max_cardinality(d.pop("max_cardinality", UNSET))


        def _parse_rollup(data: object) -> GroupingOptionOutRollupType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                rollup_type_0 = GroupingOptionOutRollupType0(data)



                return rollup_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GroupingOptionOutRollupType0 | None | Unset, data)

        rollup = _parse_rollup(d.pop("rollup", UNSET))


        grouping_option_out = cls(
            key=key,
            kind=kind,
            label=label,
            source_grain=source_grain,
            supported_surfaces=supported_surfaces,
            unsupported_measures=unsupported_measures,
            max_cardinality=max_cardinality,
            rollup=rollup,
        )


        grouping_option_out.additional_properties = d
        return grouping_option_out

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
