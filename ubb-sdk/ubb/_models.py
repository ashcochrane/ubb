"""Turn a wire response into a generated DTO — the shell's return-type contract.

The wrap (issue #84) abolishes hand-typed DTOs: product-client methods parse
their response through the generated ``ubb._core`` models instead. The generator
represents an absent optional field with its ``UNSET`` sentinel; the pre-wrap
dataclasses used ``None``. ``from_wire`` normalizes ``UNSET`` -> ``None`` on the
returned model so a caller reading ``result.stop_reason is None`` keeps working —
consumer call-sites keep their exact shape, only the type changes (decision #65).

Normalization is depth-1 (the top-level model's own fields). Nested object
models keep their ``UNSET``; they are dict-like (``model["key"]``) and rarely
introspected for absence.
"""

from __future__ import annotations

from typing import TypeVar

from attrs import fields as _attrs_fields

from ubb._core.types import Unset

T = TypeVar("T")


def _normalize_unset(obj: T) -> T:
    for f in _attrs_fields(type(obj)):
        if isinstance(getattr(obj, f.name), Unset):
            setattr(obj, f.name, None)
    return obj


def from_wire(model_cls: type[T], data: dict) -> T:
    """Parse ``data`` into a generated model, UNSET-normalized (see module doc)."""
    return _normalize_unset(model_cls.from_dict(data))


def list_from_wire(model_cls: type[T], rows: list[dict]) -> list[T]:
    """``from_wire`` over a list of rows (e.g. a page of items)."""
    return [from_wire(model_cls, row) for row in rows]
